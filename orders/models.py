from datetime import timedelta
from django.db import models, transaction
import uuid
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.core.mail import send_mail, EmailMessage
from django.utils.crypto import get_random_string
from django.utils import timezone  # for timezone.now()

# Add the SequenceNumber model at the top
class SequenceNumber(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., "PettyCashRequest-2025"
    last_number = models.PositiveIntegerField(default=0)

    def get_next_number(self):
        with transaction.atomic():
            # Lock the row to prevent race conditions
            sequence = SequenceNumber.objects.select_for_update().get(name=self.name)
            sequence.last_number += 1
            sequence.save()
            return sequence.last_number

    def __str__(self):
        return f"{self.name}: {self.last_number}"

class ExchangeRate(models.Model):
    currency = models.CharField(max_length=10, unique=True)
    rate_to_usd = models.DecimalField(max_digits=10, decimal_places=4)

    def __str__(self):
        return f"{self.currency}: {self.rate_to_usd}"

    class Meta:
        db_table = 'orders_exchangerate'  # Map to the existing table

class Approver(models.Model):
    role = models.CharField(max_length=50, unique=True)  # e.g., "Finance Manager"
    email = models.EmailField(max_length=255)
    is_available = models.BooleanField(default=True)
    fallback_approver = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name="fallbacks")

    def __str__(self):
        return f"{self.role} - {self.email}"

class ApprovalThreshold(models.Model):
    department = models.CharField(max_length=50)  # e.g., "HR and Administration"
    min_amount_zmw = models.DecimalField(max_digits=10, decimal_places=2)  # Threshold amount in ZMW
    max_amount_zmw = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Upper bound, null for no limit
    approvers = models.ManyToManyField(Approver, related_name="thresholds")

    class Meta:
        unique_together = ('department', 'min_amount_zmw')  # Ensure unique thresholds per department

    def __str__(self):
        return f"{self.department} - {self.min_amount_zmw} ZMW - {[approver.role for approver in self.approvers.all()]}"

class PurchaseOrder(models.Model):
    purchase_order_number = models.CharField(max_length=20, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=255, default="Not Specified")
    status = models.CharField(
        max_length=20,
        choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")],
        default="Pending"
    )
    include_vat = models.BooleanField(default=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    DEPARTMENT_CHOICES = [
        ('HR and Administration', 'HR and Administration'),
        ('IT', 'IT'),
        ('Client Care', 'Client Care'),
        ('Accounts', 'Accounts'),
        ('Business Development', 'Business Development')
    ]
    department = models.CharField(
        max_length=50,
        choices=DEPARTMENT_CHOICES,
        default='HR and Administration'
    )

    def get_currency(self):
        return self.items.first().currency if self.items.exists() else 'ZMW'

    def total_amount_in_zmw(self):
        currency = self.get_currency()
        try:
            rate_to_usd = ExchangeRate.objects.get(currency=currency).rate_to_usd
            zmw_rate_to_usd = ExchangeRate.objects.get(currency='ZMW').rate_to_usd
            amount_in_usd = self.total_amount * rate_to_usd
            amount_in_zmw = amount_in_usd / zmw_rate_to_usd
            return amount_in_zmw.quantize(Decimal('0.01'))
        except ExchangeRate.DoesNotExist as e:
            raise ValidationError(f"Exchange rate not found: {str(e)}")

    def save(self, *args, **kwargs):
        is_new = self.pk is None  # True if this is a new object
        if is_new and not self.purchase_order_number:
            # Default to current year
            year = timezone.now().year
            if self.created_at:
                year = self.created_at.year
            # Include the year in the sequence name for yearly reset
            sequence_name = f"PurchaseOrder-{year}"
            # Get or create the sequence for this year
            sequence, created = SequenceNumber.objects.get_or_create(name=sequence_name, defaults={"last_number": 0})
            # Get the next number in the sequence
            next_number = sequence.get_next_number()
            # Format the number as PO-YYYY-XXXXXXXX (e.g., PO-2025-00000001)
            self.purchase_order_number = f"PO-{year}-{next_number:08d}"
        elif not is_new and not self.purchase_order_number:
            raise ValueError("purchase_order_number is empty for an existing PurchaseOrder. This should not happen!")
        elif not is_new and self.purchase_order_number != PurchaseOrder.objects.get(pk=self.pk).purchase_order_number:
            raise ValueError("Cannot change purchase_order_number after it has been set!")

        super().save(*args, **kwargs)

    def update_approval_status(self):
        approvals = self.approvals.all()
        if not approvals:
            self.status = "Pending"
        elif any(approval.approved is False for approval in approvals):
            self.status = "Rejected"
        elif all(approval.approved is True for approval in approvals):
            self.status = "Approved"
        else:
            self.status = "Pending"
        self.save()
        return self.status

    def calculate_totals(self):
        self.subtotal = sum(item.amount for item in self.items.all())
        self.vat = self.subtotal * Decimal('0.16') if self.include_vat else Decimal('0')
        self.total_amount = self.subtotal + self.vat
        self.save()

    def __str__(self):
        return f"{self.purchase_order_number} - {self.status}"

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item_no = models.PositiveIntegerField()
    description = models.TextField()
    quantity = models.PositiveIntegerField(default=1)
    CURRENCY_CHOICES = [
        ('ZMW', 'ZMW'),
        ('USD', 'USD'),
        ('EUR', 'EUR'),
        ('ZAR', 'ZAR'), #set to rand
    ]
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='ZMW')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def clean(self):
        if self.unit_price is None:
            raise ValidationError({"unit_price": "Unit price is required."})
        if self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price must be a positive number."})
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        self.purchase_order.calculate_totals()

    def __str__(self):
        return f"Item {self.item_no} - {self.description} (Qty: {self.quantity})"

class PettyCashRequest(models.Model):
    petty_cash_number = models.CharField(max_length=20, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    client = models.CharField(max_length=255)
    matter_id = models.CharField(max_length=50)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")],
        default="Pending"
    )
    is_legal = models.BooleanField(default=False, help_text="Is this a legal petty cash request?")
    selected_approver_email = models.EmailField(max_length=255, blank=True, null=True, help_text="Email of the selected approver")
    LEGAL_DEPARTMENT_CHOICES = [
        ('DRPP', 'DRPP'),
        ('B&F', 'B&F'),
        ('CA', 'CA'),
        ('ERI', 'ERI'),
    ]
    department = models.CharField(
        max_length=50,
        choices=LEGAL_DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text="Department for legal petty cash requests"
    )

    non_legal_approver_email = models.EmailField(max_length=255, blank=True, null=True, help_text="Email of the selected approver for non-legal requests")

    def save(self, *args, **kwargs):
        # Check if this is a new object (being created) or an existing one (being updated)
        is_new = self.pk is None  # True if this is a new object, False if it already exists

        # Only set petty_cash_number if this is a new object AND it doesn't already have a number
        if is_new and not self.petty_cash_number:
            # Default to current year
            year = timezone.now().year
            # Override with created_at or date if available
            if self.created_at:
                year = self.created_at.year
            elif self.date:
                year = self.date.year
            # Include the year in the sequence name for yearly reset
            sequence_name = f"PettyCashRequest-{year}"
            # Get or create the sequence for this year
            sequence, created = SequenceNumber.objects.get_or_create(name=sequence_name, defaults={"last_number": 0})
            # Get the next number in the sequence
            next_number = sequence.get_next_number()
            # Format the number as PVC-YYYY-XXXXXX (e.g., PVC-2025-000001)
            self.petty_cash_number = f"PVC-{year}-{next_number:06d}"
        elif not is_new and not self.petty_cash_number:
        # If this is an existing object but petty_cash_number is empty, something is wrong
            raise ValueError("petty_cash_number is empty for an existing PettyCashRequest. This should not happen!")
        elif not is_new and self.petty_cash_number != PettyCashRequest.objects.get(pk=self.pk).petty_cash_number:
        # If someone tries to change the petty_cash_number after it's set, stop them
            raise ValueError("Cannot change petty_cash_number after it has been set!")

        # Save the object to the database
        super().save(*args, **kwargs)

class Quotation(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='quotations')
    file = models.FileField(upload_to='quotations/%Y/%m/%d/', verbose_name="Quotation File")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quotation for {self.purchase_order.purchase_order_number} - {self.file.name.split('/')[-1]}"

class SignatoryApproval(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="approvals")
    petty_cash_request = models.ForeignKey(PettyCashRequest, null=True, blank=True, on_delete=models.CASCADE, related_name="approvals")
    approver = models.ForeignKey(Approver, null=True, blank=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=50, choices=[
        ("Finance Manager", "Finance Manager"),
        ("General Manager", "General Manager"),
        ("Managing Partner", "Managing Partner"),
        ("Department Approver", "Department Approver")
    ], default="Finance Manager")
    approved = models.BooleanField(null=True, blank=True)
    approval_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    signed_by_name = models.CharField(max_length=100, blank=True, null=True, help_text="Name of the approver who signed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_email_sent = models.DateTimeField(null=True, blank=True)
    availability_timeout = models.DurationField(default=timedelta(hours=24))
    on_behalf_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name="delegated_approvals")

    def save(self, *args, **kwargs):
        if not self.approval_token:
            self.approval_token = get_random_string(64)
        super().save(*args, **kwargs)

    def get_recipient_email(self):
        if self.approver:
            return self.approver.email
        email_mapping = {
            "Senior Accountant": "abfr2x@gmail.com",
            "Finance Manager": "mandaabraham7@gmail.com",
            "General Manager": "abrahammanda.ac@gmail.com",
            "Managing Partner": "amanda@corpus.co.zm",
            "Senior Partner": "abfr2x@gmail.com",
        }
        return email_mapping.get(self.role, "amanda@corpus.co.zm")

    def send_approval_email(self):
        self.last_email_sent = timezone.now()
        self.save()
        approve_url = f"http://127.0.0.1:8080/approve/{self.approval_token}/"
        deny_url = f"http://127.0.0.1:8080/deny/{self.approval_token}/"

        if self.purchase_order:
            po = self.purchase_order
            currency = po.items.first().currency if po.items.exists() else 'ZMW'
            formatted_total = f"{currency} {po.total_amount:,.2f}"
            formatted_vat = f"{currency} {po.vat:,.2f}" if po.include_vat else "Not applicable"
            items_details = "".join(
                f"<tr><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item.item_no}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item.description}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item.quantity}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{currency} {item.unit_price:,.2f}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{currency} {item.amount:,.2f}</td></tr>"
                for item in po.items.all()
            )

            approver_html_content = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Purchase Order Approval Request</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                    a {{ color: #007bff; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    .button {{ background-color: #4CAF50; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; border-radius: 5px;}}
                    .deny-button {{background-color: #f44336;}}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Purchase Order Approval Request</h2>
                                        <p><strong>Destination:</strong> {po.destination}</p>
                                        <p><strong>PO Number:</strong> {po.purchase_order_number}</p>
                                        <p><strong>Date:</strong> {po.created_at.strftime('%Y-%m-%d %H:%M')}</p>

                                        <h3>Items Details</h3>
                                        <table>
                                            <thead>
                                                <tr><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Item No.</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Description</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Qty</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Unit Price</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Amount</th></tr>
                                            </thead>
                                            <tbody>
                                                {items_details}
                                            </tbody>
                                        </table>

                                        <h3>Financial Summary</h3>
                                        <p><strong>Subtotal:</strong> {currency} {po.subtotal:,.2f}</p>
                                        <p><strong>VAT (16%):</strong> {formatted_vat}</p>
                                        <p><strong>Total Amount:</strong> {formatted_total}</p>

                                        <h3>Requested By</h3>
                                        <p><strong>Requester:</strong> {po.requester.username}</p>

                                        <h3>Approval Required</h3>
                                        <p><strong>Your role:</strong> {self.role}</p>
                                        <p><strong>Action required by:</strong> {(po.created_at + timedelta(days=3)).strftime('%Y-%m-%d')}</p>

                                        <p><a href="{approve_url}" class="button">Approve</a> <a href="{deny_url}" class="button deny-button">Deny</a></p>

                                        <p>Attached: {po.quotations.count()} quotation(s)</p>

                                        <p>This is an automated message. Please do not reply directly to this email.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

            quotation_html_content = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Purchase Order Quotations</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Purchase Order Quotations - {po.purchase_order_number}</h2>
                                        <p><strong>Destination:</strong> {po.destination}</p>
                                        <p><strong>PO Number:</strong> {po.purchase_order_number}</p>
                                        <p><strong>Date:</strong> {po.created_at.strftime('%Y-%m-%d %H:%M')}</p>

                                        <h3>Items Details</h3>
                                        <table>
                                            <thead>
                                                <tr><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Item No.</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Description</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Qty</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Unit Price</th><th style='padding: 8px; border-bottom: 1px solid #ddd;'>Amount</th></tr>
                                            </thead>
                                            <tbody>
                                                {items_details}
                                            </tbody>
                                        </table>

                                        <h3>Financial Summary</h3>
                                        <p><strong>Subtotal:</strong> {currency} {po.subtotal:,.2f}</p>
                                        <p><strong>VAT (16%):</strong> {formatted_vat}</p>
                                        <p><strong>Total Amount:</strong> {formatted_total}</p>

                                        <h3>Requested By</h3>
                                        <p><strong>Requester:</strong> {po.requester.username}</p>

                                        <p>Attached: {po.quotations.count()} quotation(s)</p>

                                        <p>This is an automated message. Please do not reply directly to this email.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """
            subject = f"Purchase Order Approval Request - {po.purchase_order_number}"

            approver_email = EmailMessage(
                subject=subject,
                body=approver_html_content,
                from_email="amanda@corpus.co.zm",
                to=[self.get_recipient_email()],
            )
            approver_email.content_subtype = "html"

            quotation_email = EmailMessage(
                subject=f"Purchase Order Quotations - {po.purchase_order_number}",
                body=quotation_html_content,
                from_email="amanda@corpus.co.zm",
                to=["abraham96manda@gmail.com"],
            )
            quotation_email.content_subtype = "html"

            for quotation in po.quotations.all():
                try:
                    with quotation.file.open('rb') as f:
                        file_name = quotation.file.name.split('/')[-1]
                        approver_email.attach(file_name, f.read(), 'application/octet-stream')
                        quotation_email.attach(file_name, f.read(), 'application/octet-stream')
                except Exception as e:
                    print(f"Failed to attach quotation {quotation.file.name}: {e}")

            approver_email.send(fail_silently=False)
            quotation_email.send(fail_silently=False)

        elif self.petty_cash_request:
            pc = self.petty_cash_request
            html_content_with_links = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Petty Cash Approval Request</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                    a {{ color: #007bff; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    .button {{ background-color: #4CAF50; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; border-radius: 5px;}}
                    .deny-button {{background-color: #f44336;}}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Petty Cash Approval Request</h2>
                                        <p><strong>Number:</strong> {pc.petty_cash_number}</p>
                                        <p><strong>Date:</strong> {pc.date.strftime('%Y-%m-%d')}</p>
                                        <p><strong>Client:</strong> {pc.client}</p>
                                        <p><strong>Matter ID:</strong> {pc.matter_id}</p>
                                        <p><strong>Description:</strong> {pc.description}</p>
                                        <p><strong>Amount:</strong> ZMW {pc.amount:,.2f}</p>

                                        <h3>Requested By</h3>
                                        <p><strong>Requester:</strong> {pc.requester.username}</p>

                                        <p><a href="{approve_url}" class="button">Approve</a> <a href="{deny_url}" class="button deny-button">Deny</a></p>

                                        <p>This is an automated message. Please do not reply directly to this email.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """
            html_content_no_links = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Petty Cash Approval Request</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Petty Cash Approval Request</h2>
                                        <p><strong>Number:</strong> {pc.petty_cash_number}</p>
                                        <p><strong>Date:</strong> {pc.date.strftime('%Y-%m-%d')}</p>
                                        <p><strong>Client:</strong> {pc.client}</p>
                                        <p><strong>Matter ID:</strong> {pc.matter_id}</p>
                                        <p><strong>Description:</strong> {pc.description}</p>
                                        <p><strong>Amount:</strong> ZMW {pc.amount:,.2f}</p>

                                        <h3>Requested By</h3>
                                        <p><strong>Requester:</strong> {pc.requester.username}</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

            subject = f"Petty Cash Approval Request - {pc.petty_cash_number}"
            recipient_email = pc.selected_approver_email if pc.is_legal and pc.selected_approver_email else self.get_recipient_email()

            send_mail(
                subject=subject,
                message=html_content_with_links,
                from_email="amanda@corpus.co.zm",
                recipient_list=[recipient_email],
                fail_silently=False,
                html_message=html_content_with_links,
            )
            send_mail(
                subject=subject,
                message=html_content_no_links,
                from_email="amanda@corpus.co.zm",
                recipient_list=["abraham96manda@gmail.com"],
                fail_silently=False,
                html_message=html_content_no_links,
            )

    def send_final_decision_email(self, decision):
        decision = decision.lower()
        recipients = set()
        finance_team_email = "abraham96manda@gmail.com"

        if self.purchase_order:
            po = self.purchase_order
            # Add requester
            if po.requester and hasattr(po.requester, 'email'):
                recipients.add(po.requester.email)
            # Add the approver who made this decision (self)
            recipients.add(self.get_recipient_email())
            # Add finance team
            recipients.add(finance_team_email)

            subject = f"Purchase Order {decision.title()} - {po.purchase_order_number}"
            currency = po.items.first().currency if po.items.exists() else 'ZMW'
            decision_details = [
                f"{approval.role}: {'Approved' if approval.approved else 'Denied'} by {approval.signed_by_name or 'Unknown'} at {approval.updated_at.strftime('%Y-%m-%d %H:%M') if approval.updated_at else 'N/A'}"
                for approval in po.approvals.all() if approval.approved is not None
            ]
            decision_history = "\n".join(decision_details) if decision_details else "No decision history available"
            email_body = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Purchase Order {decision.title()}</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Purchase Order {decision.title()}</h2>
                                        <p><strong>PO Number:</strong> {po.purchase_order_number}</p>
                                        <p><strong>Requester:</strong> {po.requester.username if po.requester else 'N/A'}</p>
                                        <p><strong>Destination:</strong> {po.destination}</p>
                                        <p><strong>Total Amount:</strong> {currency} {po.total_amount:,.2f}</p>

                                        <h3>Decision History</h3>
                                        <p>{decision_history}</p>

                                        <h3>Next Steps</h3>
                                        <p>{"The requester will proceed with the order." if decision == "approved" else "Please contact the requester for alternatives."}</p>

                                        <p>This is an automated notification. Please do not reply directly.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

        elif self.petty_cash_request:
            pc = self.petty_cash_request
            # Add requester
            if pc.requester and hasattr(pc.requester, 'email'):
                recipients.add(pc.requester.email)
            # Add the selected approver (legal or non-legal)
            if pc.is_legal and pc.selected_approver_email:
                recipients.add(pc.selected_approver_email)
            elif not pc.is_legal and pc.non_legal_approver_email:
                recipients.add(pc.non_legal_approver_email)
            # Add finance team
            recipients.add(finance_team_email)

            subject = f"Petty Cash {decision.title()} - {pc.petty_cash_number}"
            decision_details = [
                f"{approval.role}: {'Approved' if approval.approved else 'Denied'} by {approval.signed_by_name or 'Unknown'} at {approval.updated_at.strftime('%Y-%m-%d %H:%M') if approval.updated_at else 'N/A'}"
                for approval in pc.approvals.all() if approval.approved is not None
            ]
            decision_history = "\n".join(decision_details) if decision_details else "No decision history available"
            email_body = f"""
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
                <title>Petty Cash {decision.title()}</title>
                <style type="text/css">
                    body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                </style>
            </head>
            <body style="background-color: #f4f4f4; padding: 20px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td align="center">
                            <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                                <tr>
                                    <td>
                                        <h2 style="color: #333;">Petty Cash {decision.title()}</h2>
                                        <p><strong>Number:</strong> {pc.petty_cash_number}</p>
                                        <p><strong>Requester:</strong> {pc.requester.username if pc.requester else 'N/A'}</p>
                                        <p><strong>Amount:</strong> ZMW {pc.amount:,.2f}</p>
                                        <p><strong>Client:</strong> {pc.client}</p>
                                        <p><strong>Matter ID:</strong> {pc.matter_id}</p>

                                        <h3>Decision History</h3>
                                        <p>{decision_history}</p>

                                        <h3>Next Steps</h3>
                                        <p>{"The requester will proceed with the request." if decision == "approved" else "Please contact the requester for alternatives."}</p>

                                        <p>This is an automated notification. Please do not reply directly.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """

        if recipients:
            send_mail(
                subject=subject,
                message=email_body,
                from_email="amanda@corpus.co.zm",
                recipient_list=list(recipients),
                fail_silently=False,
                html_message=email_body,
            )

    def __str__(self):
        if self.purchase_order:
            return f"{self.role} approval for {self.purchase_order.purchase_order_number}"
        elif self.petty_cash_request:
            return f"{self.role} approval for {self.petty_cash_request.petty_cash_number}"
        return f"{self.role} approval"
    






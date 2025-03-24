from django.db import models
import uuid
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal

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
    include_vat = models.BooleanField(default=True)  # VAT toggle
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0 )
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0 )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if not self.purchase_order_number:
            self.purchase_order_number = f'PO-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate subtotal, VAT (if enabled), and total amount."""
        self.subtotal = sum(item.amount for item in self.items.all())
        self.vat = self.subtotal * Decimal('0.16') if self.include_vat else Decimal('0')  # Use Decimal for 0.16
        self.total_amount = self.subtotal + self.vat
        self.save()

    def __str__(self):
        return f"{self.purchase_order_number} - {self.status}"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item_no = models.PositiveIntegerField()
    description = models.TextField()
    quantity = models.PositiveIntegerField(default=1)
    currency = models.CharField(max_length=10, default='ZMW')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def clean(self):
        """Validate unit_price and quantity."""
        if self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price must be a positive number."})
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})

    def save(self, *args, **kwargs):
        """Calculate the amount and save the item."""
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        self.purchase_order.calculate_totals()  # Update the PO's subtotal, VAT, and total

    def __str__(self):
        return f"Item {self.item_no} - {self.description} (Qty: {self.quantity})"
    
class Signatory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=50, choices=[('Level1', 'Level 1'), ('Level2', 'Level 2')])
    email = models.EmailField()

    def __str__(self):
        return f"{self.user.username} - {self.role}"
    
class SignatoryApproval(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="approvals")
    signatory = models.ForeignKey(Signatory, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, 
        choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")], 
        default="Pending"
    )

    def __str__(self):
        return f"{self.signatory.user.username} - {self.purchase_order.purchase_order_number} - {self.status}"

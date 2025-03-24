from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import PurchaseOrder, PurchaseOrderItem, Signatory, SignatoryApproval
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.contrib.auth.models import User
from orders.models import Signatory, PurchaseOrder
from orders.forms import PurchaseOrderForm, PurchaseOrderItemFormSet
import uuid
from django.http import HttpResponseForbidden

@login_required
def create_purchase_order(request):
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)

        if po_form.is_valid() and item_formset.is_valid():
            try:
                # Save the PurchaseOrder first
                purchase_order = po_form.save(commit=False)
                purchase_order.requester = request.user
                purchase_order.status = 'Pending'
                purchase_order.save()

                # Save items
                items = item_formset.save(commit=False)
                for item in items:
                    item.purchase_order = purchase_order
                    item.save()

                purchase_order.calculate_totals()
                total_amount = purchase_order.total_amount

                # Get required signatories
                financeManager = Signatory.objects.get(email='abrahammanda.ac@gmail.com')
                generalManager = Signatory.objects.get(email='mandaabraham7@gmail.com')
                seniorPartner = Signatory.objects.get(email='amanda@corpus.co.zm')

                # Determine signatories based on amount
                if total_amount <= 5000:
                    signatories = [financeManager]
                elif 5000 < total_amount <= 58000:
                    signatories = [financeManager, generalManager]
                else:
                    signatories = [financeManager, generalManager, seniorPartner]

                # Create approvals and send emails
                for signatory in signatories:
                    token = str(uuid.uuid4())
                    approval = SignatoryApproval.objects.create(
                        purchase_order=purchase_order,
                        signatory=signatory,
                        approval_token=token
                    )
                    
                    # Generate unique URLs for each approver
                    approve_url = request.build_absolute_uri(
                        reverse('approve_po', args=[token]))
                    deny_url = request.build_absolute_uri(
                        reverse('deny_po', args=[token]))
                    
                    # Send email
                    subject = f"Approval Required: PO-{purchase_order.purchase_order_number}"
                    context = {
                        'approve_url': approve_url,
                        'deny_url': deny_url,
                        'purchase_order': purchase_order,
                        'signatory': signatory
                    }
                    html_message = render_to_string('emails/approval_email.html', context)
                    plain_message = strip_tags(html_message)
                    send_mail(
                        subject,
                        plain_message,
                        'amanda@corpus.co.zm',
                        [signatory.email],
                        html_message=html_message,
                        fail_silently=False
                    )

                messages.success(request, 'Purchase order submitted for approval!')
                return redirect('create_purchase_order')

            except Signatory.DoesNotExist:
                messages.error(request, 'Required signatories not found. Please contact admin.')
                return redirect('create_purchase_order')
            except Exception as e:
                messages.error(request, f'Error creating purchase order: {str(e)}')
                return redirect('create_purchase_order')
    else:
        po_form = PurchaseOrderForm()
        item_formset = PurchaseOrderItemFormSet()

    return render(request, "orders/create_po.html", {
        "po_form": po_form,
        "item_formset": item_formset
    })

def approve_po(request, token):
    try:
        approval = SignatoryApproval.objects.get(approval_token=token)
        approval.status = "Approved"
        approval.save()

        # Check if all signatories approved
        purchase_order = approval.purchase_order
        required_signatories = SignatoryApproval.objects.filter(purchase_order=purchase_order)
        all_approved = all(sign.status == 'Approved' for sign in required_signatories)

        # Identify master signatory
        master_signatory = None
        if 5000 < purchase_order.total_amount <= 58000:
            master_signatory = Signatory.objects.get(email='mandaabraham7@gmail.com')
        elif purchase_order.total_amount > 58000:
            master_signatory = Signatory.objects.get(email='amanda@corpus.co.zm')

        master_approved = required_signatories.filter(signatory=master_signatory, status='Approved').exists()

        if all_approved and master_approved:
            purchase_order.status = 'Approved'
            purchase_order.save()

        return HttpResponse("Approval successful. Thank you!", content_type="text/plain")

    except SignatoryApproval.DoesNotExist:
        return HttpResponseForbidden("Invalid or expired approval link.")


def deny_po(request, token):
    try:
        approval = SignatoryApproval.objects.get(approval_token=token)
        approval.status = "Rejected"
        approval.save()

        purchase_order = approval.purchase_order
        purchase_order.status = "Rejected"
        purchase_order.save()

        return HttpResponse("Purchase order has been rejected.", content_type="text/plain")

    except SignatoryApproval.DoesNotExist:
        return HttpResponseForbidden("Invalid or expired rejection link.")
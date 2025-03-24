from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import PurchaseOrder, PurchaseOrderItem, Signatory, SignatoryApproval
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import strip_tags
from django.template.loader import render_to_string
import uuid
from django.http import HttpResponse

@login_required
def create_purchase_order(request):
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)

        if po_form.is_valid() and item_formset.is_valid():
            try:
                # Save PurchaseOrder
                purchase_order = po_form.save(commit=False)
                purchase_order.requester = request.user
                purchase_order.status = 'Pending'
                purchase_order.save()

                # Save Items
                for item in item_formset.save(commit=False):
                    item.purchase_order = purchase_order
                    item.save()

                purchase_order.calculate_totals()
                
                # Get signatories based on amount
                signatories = []
                if purchase_order.total_amount <= 5000:
                    signatories.append(Signatory.objects.get(email='abrahammanda.ac@gmail.com'))
                elif 5000 < purchase_order.total_amount <= 58000:
                    signatories.extend([
                        Signatory.objects.get(email='abrahammanda.ac@gmail.com'),
                        Signatory.objects.get(email='mandaabraham7@gmail.com')
                    ])
                else:
                    signatories.extend([
                        Signatory.objects.get(email='abrahammanda.ac@gmail.com'),
                        Signatory.objects.get(email='mandaabraham7@gmail.com'),
                        Signatory.objects.get(email='amanda@corpus.co.zm')
                    ])

                # Create approvals
                for signatory in signatories:
                    token = str(uuid.uuid4())
                    SignatoryApproval.objects.create(
                        purchase_order=purchase_order,
                        signatory=signatory,
                        approval_token=token
                    )
                    
                    # Send email
                    approve_url = request.build_absolute_uri(
                        reverse('approve_po', args=[token]))
                    deny_url = request.build_absolute_uri(
                        reverse('deny_po', args=[token]))
                    
                    send_mail(
                        f"PO Approval: {purchase_order.purchase_order_number}",
                        f"Please review this purchase order: {approve_url}",
                        'amanda@corpus.co.zm',
                        [signatory.email],
                        fail_silently=False
                    )

                messages.success(request, 'Purchase order submitted!')
                return redirect('create_purchase_order')

            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        po_form = PurchaseOrderForm()
        item_formset = PurchaseOrderItemFormSet()

    return render(request, "orders/create_po.html", {
        "po_form": po_form,
        "item_formset": item_formset
    })

def approve_po(request, token):
    approval = get_object_or_404(SignatoryApproval, approval_token=token)
    approval.status = "Approved"
    approval.save()
    return HttpResponse("Approved successfully")

def deny_po(request, token):
    approval = get_object_or_404(SignatoryApproval, approval_token=token)
    approval.status = "Rejected"
    approval.save()
    approval.purchase_order.status = "Rejected"
    approval.purchase_order.save()
    return HttpResponse("Rejected successfully")
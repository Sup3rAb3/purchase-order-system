from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from django.contrib import messages
from .models import PurchaseOrder, PurchaseOrderItem, Signatory
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import strip_tags
from django.template.loader import render_to_string


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.contrib.auth.models import User
from orders.models import Signatory, PurchaseOrder
from orders.forms import PurchaseOrderForm, PurchaseOrderItemFormSet

@login_required
def create_purchase_order(request):
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)

        if po_form.is_valid() and item_formset.is_valid():
            # Save the PurchaseOrder first
            purchase_order = po_form.save(commit=False)
            purchase_order.requester = request.user  # Set requester
            purchase_order.status = 'Pending'  # Set initial status
            purchase_order.save()

            # Save the PurchaseOrderItem instances
            items = item_formset.save(commit=False)
            for item in items:
                item.purchase_order = purchase_order
                item.save()

            # Calculate the total amount
            purchase_order.calculate_totals()
            total_amount = purchase_order.total_amount

            # Retrieve predefined signatories
            financeManager = Signatory.objects.get(user__username='financeManager')
            generalManager = Signatory.objects.get(user__username='generalManager')
            seniorPartner = Signatory.objects.get(user__username='seniorPartner')

            # Determine the signatories based on the total amount
            signatories = []
            if total_amount <= 5000:
                signatories = [financeManager]
            elif 5000 < total_amount <= 58000:
                signatories = [financeManager, generalManager]
            else:
                signatories = [financeManager, generalManager, seniorPartner]

            # Create SignatoryApproval records
            for signatory in signatories:
                SignatoryApproval.objects.create(purchase_order=purchase_order, signatory=signatory, status="Pending")

            # Send emails to signatories
            for signatory in signatories:
                subject = f"Purchase Order Approval Required: {purchase_order.purchase_order_number}"
                context = {
                    'purchase_order': purchase_order,
                    'signatory': signatory,
                    'approve_url': request.build_absolute_uri(reverse('approve_purchase_order', args=[purchase_order.id])),
                    'deny_url': request.build_absolute_uri(reverse('deny_purchase_order', args=[purchase_order.id])),
                }
                html_message = render_to_string('emails/approval_email.html', context)
                plain_message = strip_tags(html_message)
                send_mail(subject, plain_message, 'amanda@corpus.co.zm', [signatory.email], html_message=html_message)

            messages.success(request, 'Your purchase order has been successfully submitted!')
            return redirect('create_purchase_order')

    else:
        po_form = PurchaseOrderForm()
        item_formset = PurchaseOrderItemFormSet()

    return render(request, "orders/create_po.html", {"po_form": po_form, "item_formset": item_formset})



@login_required
def approve_purchase_order(request, po_id):
    purchase_order = get_object_or_404(PurchaseOrder, id=po_id)
    purchase_order.status = 'Approved'
    purchase_order.save()
    messages.success(request, 'Purchase order has been approved.')
    return redirect('create_purchase_order')

@login_required
def deny_purchase_order(request, po_id):
    purchase_order = get_object_or_404(PurchaseOrder, id=po_id)
    purchase_order.status = 'Rejected'
    purchase_order.save()
    messages.success(request, 'Purchase order has been denied.')
    return redirect('create_purchase_order')
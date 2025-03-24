from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import PurchaseOrder, PurchaseOrderItem
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import strip_tags
from django.template.loader import render_to_string


@login_required
def create_purchase_order(request):
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)

        if po_form.is_valid() and item_formset.is_valid():
            # Save the PurchaseOrder first
            purchase_order = po_form.save(commit=False)
            purchase_order.requester = request.user # Set the requester to the currently logged-in user
            purchase_order.status = 'Pending' # Set initial status
            purchase_order.save()

            # Save the PurchaseOrderItem instances
            items = item_formset.save(commit=False)
            for item in items:
                item.purchase_order = purchase_order  # Assign the PurchaseOrder to each item
                item.save()

            # Calculate the total amount
            purchase_order.calculate_totals()

            # Determine the signatories based on the total amount
            if purchase_order.total_amount < 50000:
                signatories = Signatory.objects.filter(role='Level1')[:2]  # Two Level 1 signatories
            else:
                signatories = Signatory.objects.filter(role='Level2')[:3]  # Three Level 2 signatories

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
            # Print form errors for debugging
            print("PO Form Errors:", po_form.errors)
            print("Item Formset Errors:", item_formset.errors)  # for debugging, remove in production
    else:
        po_form = PurchaseOrderForm()
        item_formset = PurchaseOrderItemFormSet()

    return render(request, "orders/create_po.html", {"po_form": po_form, "item_formset": item_formset})
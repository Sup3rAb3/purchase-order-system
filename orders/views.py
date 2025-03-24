from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import PurchaseOrder, PurchaseOrderItem
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet

@login_required
def create_purchase_order(request):
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)

        if po_form.is_valid() and item_formset.is_valid():
            # Save the PurchaseOrder first
            purchase_order = po_form.save(commit=False)
            purchase_order.status = 'Pending'  # Set initial status
            purchase_order.save()

            # Save the PurchaseOrderItem instances
            items = item_formset.save(commit=False)
            for item in items:
                item.purchase_order = purchase_order  # Assign the PurchaseOrder to each item
                item.save()

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
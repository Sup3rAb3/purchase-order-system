from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['destination', 'include_vat']

# Create an inline formset for PurchaseOrderItem
PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    fields=('item_no', 'description', 'quantity', 'currency', 'unit_price'),
    extra=1,
    can_delete=True
)

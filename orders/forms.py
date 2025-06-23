from django import forms
from .models import Quotation
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import PurchaseOrder, PurchaseOrderItem, PettyCashRequest, ExchangeRate
from decimal import Decimal

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['destination', 'department', 'include_vat']

class PurchaseOrderItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        if not self.forms:  # Handle empty formset
            return
        total_zmw = Decimal('0')
        currency = None
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                quantity = form.cleaned_data.get('quantity', 0)
                unit_price = form.cleaned_data.get('unit_price', 0)
                form_currency = form.cleaned_data.get('currency', 'ZMW')
                amount = quantity * unit_price
                if currency is None:
                    currency = form_currency
                elif currency != form_currency:
                    raise forms.ValidationError("All items must use the same currency.")
                try:
                    rate_to_usd = ExchangeRate.objects.get(currency=form_currency).rate_to_usd
                    zmw_rate_to_usd = ExchangeRate.objects.get(currency='ZMW').rate_to_usd
                    amount_in_usd = amount * rate_to_usd
                    amount_in_zmw = amount_in_usd / zmw_rate_to_usd
                    total_zmw += amount_in_zmw.quantize(Decimal('0.01'))
                except ExchangeRate.DoesNotExist:
                    raise forms.ValidationError(f"Exchange rate for {form_currency} not found.")
        if total_zmw <= 1000:
            raise forms.ValidationError(
                f"Total in ZMW ({total_zmw:,.2f} ZMW) must be greater than 1,000 ZMW. "
                f"Use petty cash for amounts of 1,000 ZMW or less."
            )

PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    fields=('item_no', 'description', 'quantity', 'currency', 'unit_price'),
    extra=1,
    can_delete=True,
    formset=PurchaseOrderItemInlineFormSet
)

class PettyCashForm(forms.ModelForm):
    NON_LEGAL_APPROVERS = [
        ('mandaabraham7@gmail.com', 'Finance Manager'),
        ('abfr2x@gmail.com', 'Senior Accountant'),
    ]

    is_legal = forms.BooleanField(required=False, label="Is this a legal petty cash request?")
    selected_approver_email = forms.ChoiceField(
        choices=[],
        required=False,
        label="Select Approver",
        help_text="Choose an available approver for legal requests."
    )
    department = forms.ChoiceField(
        choices=PettyCashRequest.LEGAL_DEPARTMENT_CHOICES,
        required=False,
        label="Department",
        help_text="Select the department for legal petty cash."
    )
    non_legal_approver_email = forms.ChoiceField(
        choices=NON_LEGAL_APPROVERS,
        required=False,
        label="Select Approver",
        help_text="Choose an available approver for non-legal requests."
    )

    class Meta:
        model = PettyCashRequest
        fields = ['client', 'matter_id', 'description', 'amount', 'is_legal', 'department', 'selected_approver_email', 'non_legal_approver_email']
        widgets = {
            'amount': forms.NumberInput(attrs={'max': 1000, 'min': 0.01}),
        }
        labels = {
            'amount': 'Amount (ZMW)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .views import DEPARTMENT_APPROVERS
        if self.data.get('department') in DEPARTMENT_APPROVERS:
            self.fields['selected_approver_email'].choices = [
                (approver['email'], f"{approver['name']} ({approver['role']})")
                for approver in DEPARTMENT_APPROVERS[self.data['department']]
            ]
        elif self.instance and self.instance.department in DEPARTMENT_APPROVERS:
            self.fields['selected_approver_email'].choices = [
                (approver['email'], f"{approver['name']} ({approver['role']})")
                for approver in DEPARTMENT_APPROVERS[self.instance.department]
            ]
        self.fields['selected_approver_email'].widget.attrs['class'] = 'form-select sleek-select'
        self.fields['department'].widget.attrs['class'] = 'form-select sleek-select'
        self.fields['non_legal_approver_email'].widget.attrs['class'] = 'form-select sleek-select'

QuotationFormSet = inlineformset_factory(
    PurchaseOrder,
    Quotation,
    fields=('file',),
    extra=1,
    can_delete=True,
)
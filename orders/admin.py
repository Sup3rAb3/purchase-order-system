from django.contrib import admin
from .models import PurchaseOrder, PurchaseOrderItem

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0  # No extra empty forms
    readonly_fields = ('item_no', 'description', 'quantity', 'currency', 'unit_price', 'amount')

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('purchase_order_number', 'requester', 'destination', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('purchase_order_number', 'requester__username', 'destination')
    inlines = [PurchaseOrderItemInline]  # Add inline forms for PurchaseOrderItem
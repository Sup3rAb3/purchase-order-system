from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import PurchaseOrder, PurchaseOrderItem, SignatoryApproval, PettyCashRequest

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('purchase_order_number', 'destination', 'requester', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'department')
    search_fields = ('purchase_order_number', 'requester__username', 'destination')

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'item_no', 'description', 'quantity', 'amount')


@admin.register(SignatoryApproval)
class SignatoryApprovalAdmin(admin.ModelAdmin):
    list_display = ('role', 'approved', 'approval_token', 'get_signed_by_name')

    def get_signed_by_name(self, obj):
        return obj.signed_by_name or "Not Signed"
    get_signed_by_name.short_description = "Signed By"

@admin.register(PettyCashRequest)
class PettyCashRequestAdmin(admin.ModelAdmin):
    list_display = ('petty_cash_number', 'requester', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('petty_cash_number', 'requester__username', 'client', 'matter_id')
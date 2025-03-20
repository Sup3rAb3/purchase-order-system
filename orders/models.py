from django.db import models
import uuid # For generating unqiue orders numbers
from django.contrib.auth.models import User

# Create your models here.

class PurchaseOrder(models.Model):
    purchase_order_number = models.CharField(max_length=20, unique= True, editable=False, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")], default="Pending")

    def save(self, *args, **kwargs):
        if not self.purchase_order_number:
            self.purchase_order_number = f'PO-{uuid.uuid4().hex[:8]. upper()}'
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.purchase_order_number}- {self.status}"

class PurchaseOrderItem (models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item_no = models.PositiveIntegerField()
    description = models.TextField()
    quantity = models.PositiveIntegerField(default=1)
    currency = models.CharField(max_length=10, default='ZMW')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Item {self.item_no} - [self.purchase_order.purchase_order_number]"

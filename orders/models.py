from django.db import models

# Create your models here.
class PurchaseOrder (models.Model):
    order_number = models.CharField(max_length=20, unique=True)
    requester = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='ZMW')
    status = models.CharField(max_length=20, choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Declined', 'Declined')
    ], default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PO-{self.order_number} | {self.requester} | {self.amount} {self.currency}"

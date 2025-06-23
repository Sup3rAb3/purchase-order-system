from django.core.management.base import BaseCommand
from orders.models import Approver, ApprovalThreshold, PurchaseOrder
from decimal import Decimal

class Command(BaseCommand):
    help = 'Load initial approval thresholds'

    def handle(self, *args, **kwargs):
        # Clear existing thresholds
        ApprovalThreshold.objects.all().delete()

        # Get approvers
        approvers = {
            role: Approver.objects.get(role=role)
            for role in [
                'Senior Accountant', 'Finance Manager', 'General Manager',
                'Managing Partner', 'Senior Partner'
            ]
        }

        # Define thresholds in ZMW, aligned with USD equivalents (1 USD = 24.4499 ZMW)
        departments = PurchaseOrder.DEPARTMENT_CHOICES
        for dept, _ in departments:
            thresholds = [
                # 1,000 ZMW to 2,000 ZMW
                {
                    'department': dept,
                    'min_amount_zmw': Decimal('1000.00'),
                    'max_amount_zmw': Decimal('2000.00'),
                    'approvers': [approvers['Finance Manager']],
                },
                # 2,000 ZMW to 48,899.80 ZMW (up to 2,000 USD)
                {
                    'department': dept,
                    'min_amount_zmw': Decimal('2000.01'),
                    'max_amount_zmw': Decimal('48899.80'),  # 2,000 USD
                    'approvers': [approvers['Finance Manager'], approvers['General Manager']],
                },
                # 48,899.81 ZMW to 122,249.50 ZMW (2,000 USD to 5,000 USD)
                {
                    'department': dept,
                    'min_amount_zmw': Decimal('48899.81'),
                    'max_amount_zmw': Decimal('122249.50'),  # 5,000 USD
                    'approvers': [
                        approvers['Finance Manager'],
                        approvers['General Manager'],
                        approvers['Managing Partner'],
                    ],
                },
                # Above 122,249.50 ZMW (5,000 USD and above)
                {
                    'department': dept,
                    'min_amount_zmw': Decimal('122249.51'),
                    'max_amount_zmw': None,  # No upper bound
                    'approvers': [
                        approvers['Finance Manager'],
                        approvers['General Manager'],
                        approvers['Managing Partner'],
                        approvers['Senior Partner'],
                    ],
                },
            ]
            for data in thresholds:
                threshold = ApprovalThreshold.objects.create(
                    department=data['department'],
                    min_amount_zmw=data['min_amount_zmw'],
                    max_amount_zmw=data['max_amount_zmw'],
                )
                threshold.approvers.set(data['approvers'])

        self.stdout.write(self.style.SUCCESS('Successfully loaded approval thresholds'))
from django.core.management.base import BaseCommand
from orders.models import Approver

class Command(BaseCommand):
    help = 'Load initial approver data with fallbacks'

    def handle(self, *args, **kwargs):
        # Clear existing data
        Approver.objects.all().delete()

        # Create approvers
        approvers_data = [
            {'role': 'Senior Accountant', 'email': 'abfr2x@gmail.com'},
            {'role': 'Finance Manager', 'email': 'mandaabraham7@gmail.com'},
            {'role': 'General Manager', 'email': 'abrahammanda.ac@gmail.com'},
            {'role': 'Managing Partner', 'email': 'amanda@corpus.co.zm'},
            {'role': 'Senior Partner', 'email': 'chooseyellowgray@gmail.com'},
        ]
        created_approvers = {}
        for data in approvers_data:
            approver, _ = Approver.objects.get_or_create(**data)
            created_approvers[data['role']] = approver

        # Set fallbacks
        fallbacks = [
            {'primary': 'Finance Manager', 'fallback': 'Senior Accountant'},
            {'primary': 'General Manager', 'fallback': 'Finance Manager'},
            {'primary': 'Managing Partner', 'fallback': 'Senior Partner'},
            {'primary': 'Senior Partner', 'fallback': 'Managing Partner'},
        ]
        for data in fallbacks:
            primary = created_approvers[data['primary']]
            primary.fallback_approver = created_approvers[data['fallback']]
            primary.save()

        self.stdout.write(self.style.SUCCESS('Successfully loaded approvers and fallbacks'))
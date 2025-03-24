# management/commands/create_signatories.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from orders.models import Signatory

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Create or get users first
        finance_user, _ = User.objects.get_or_create(
            username='financeManager',
            defaults={'email': 'abrahammanda.ac@gmail.com'}
        )
        general_user, _ = User.objects.get_or_create(
            username='generalManager',
            defaults={'email': 'mandaabraham7@gmail.com'}
        )
        senior_user, _ = User.objects.get_or_create(
            username='seniorPartner',
            defaults={'email': 'amanda@corpus.co.zm'}
        )

        # Create signatories
        Signatory.objects.get_or_create(
            email='abrahammanda.ac@gmail.com',
            defaults={
                'name': 'Finance Manager', 
                'role': 'Level1',
                'user': finance_user
            }
        )
        Signatory.objects.get_or_create(
            email='mandaabraham7@gmail.com',
            defaults={
                'name': 'General Manager', 
                'role': 'Level2',
                'user': general_user
            }
        )
        Signatory.objects.get_or_create(
            email='amanda@corpus.co.zm',
            defaults={
                'name': 'Senior Partner', 
                'role': 'Level2',
                'user': senior_user
            }
        )
        self.stdout.write(self.style.SUCCESS('Successfully created signatories'))
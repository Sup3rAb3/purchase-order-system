from django.core.management.base import BaseCommand
from orders.models import ExchangeRate
from decimal import Decimal

class Command(BaseCommand):
    help = 'Load initial exchange rates (to USD)'

    def handle(self, *args, **kwargs):
        # Clear existing rates
        ExchangeRate.objects.all().delete()

        # Exchange rates (as of May 2025, approximate)
        rates = [
            {'currency': 'USD', 'rate_to_usd': Decimal('1.0000')},
            {'currency': 'ZMW', 'rate_to_usd': Decimal('0.0385')},  # 1 ZMW = 0.0385 USD
            {'currency': 'EUR', 'rate_to_usd': Decimal('1.0600')},  # 1 EUR = 1.06 USD
            {'currency': 'ZAR', 'rate_to_usd': Decimal('0.0560')},  # 1 ZAR = 0.056 USD
        ]
        for data in rates:
            ExchangeRate.objects.create(**data)

        self.stdout.write(self.style.SUCCESS('Successfully loaded exchange rates'))
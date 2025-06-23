import requests
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.conf import settings
from orders.models import ExchangeRate

class Command(BaseCommand):
    help = 'Update exchange rates from the ExchangeRate-API for ZMW, USD, EUR, ZAR'

    def handle(self, *args, **options):
        api_key = settings.EXCHANGE_RATE_API_KEY
        base_currency = 'ZMW'
        url = f'https://v6.exchangerate-api.com/v6/{api_key}/latest/{base_currency}'
        
        # Define the currencies we want to support
        supported_currencies = {'ZMW', 'USD', 'EUR', 'ZAR'}

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get('result') != 'success':
                self.stdout.write(self.style.ERROR('Failed to fetch exchange rates'))
                return

            rates = data.get('conversion_rates', {})
            if not rates:
                self.stdout.write(self.style.WARNING('No rates returned. Keeping existing rates.'))
                return

            # Get the ZMW to USD rate (e.g., 1 ZMW = 0.0385 USD)
            zmw_to_usd = Decimal(str(rates.get('USD', 1)))

            # Update ZMW rate first
            ExchangeRate.objects.update_or_create(
                currency='ZMW',
                defaults={'rate_to_usd': zmw_to_usd},
            )

            # Update only the supported currencies (excluding ZMW since it's already handled)
            for currency in supported_currencies - {'ZMW'}:
                if currency not in rates:
                    self.stdout.write(self.style.WARNING(f'Rate for {currency} not found in API response. Skipping.'))
                    continue

                # API gives: 1 ZMW = rate_to_zmw [currency]
                # So, 1 [currency] = 1/rate_to_zmw ZMW
                # Then, 1 [currency] = (1/rate_to_zmw) * zmw_to_usd USD
                rate_to_zmw = Decimal(str(rates[currency]))
                rate_to_usd = (Decimal('1') / rate_to_zmw) * zmw_to_usd

                ExchangeRate.objects.update_or_create(
                    currency=currency,
                    defaults={'rate_to_usd': rate_to_usd},
                )

            # Delete any ExchangeRate entries for unsupported currencies
            deleted, _ = ExchangeRate.objects.exclude(currency__in=supported_currencies).delete()
            if deleted > 0:
                self.stdout.write(self.style.WARNING(f'Deleted {deleted} unsupported currency entries.'))

            self.stdout.write(self.style.SUCCESS('Successfully updated exchange rates for ZMW, USD, EUR, ZAR'))

        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching exchange rates: {e}'))
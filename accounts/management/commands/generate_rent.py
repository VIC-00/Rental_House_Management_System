import calendar
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Tenant, RentCharge # ⭐ Added RentCharge

class Command(BaseCommand):
    help = 'Generates monthly rent charges for all active tenants'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        # Get the number of days in the current month
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        
        # ⭐ THE FIX: Only fetch tenants whose move-in date is TODAY or in the PAST.
        # If their move-in date is tomorrow (or later), they are completely ignored.
        active_tenants = Tenant.objects.filter(
            status='active',
            move_in_date__lte=today 
        )
        
        count = 0
        for tenant in active_tenants:
            # 1. ⭐ THE SAFETY LOCK: Check if this month has already been charged
            already_charged = RentCharge.objects.filter(
                tenant=tenant, 
                month=today.month, 
                year=today.year
            ).exists()

            if already_charged:
                self.stdout.write(self.style.WARNING(f"Skipping {tenant} - Already charged for {today.strftime('%B %Y')}"))
                continue

            # 2. Determine the Amount to Charge
            amount_to_charge = Decimal('0.00')

            # --- LOGIC A: The First Month (Pro-rated) ---
            if not tenant.initial_rent_charged:
                days_stayed = (days_in_month - tenant.move_in_date.day) + 1
                
                if days_stayed > 0:
                    daily_rate = Decimal(str(tenant.rent_amount)) / Decimal(days_in_month)
                    amount_to_charge = (daily_rate * Decimal(days_stayed)).quantize(Decimal('1.00'))
                    
                    tenant.initial_rent_charged = True
                    self.stdout.write(self.style.SUCCESS(f"Pro-rated: {tenant} - KES {amount_to_charge}"))
            
            # --- LOGIC B: Regular Full Month ---
            else:
                amount_to_charge = Decimal(str(tenant.rent_amount))
                self.stdout.write(f"Full Charge: {tenant} - KES {amount_to_charge}")

            # 3. ⭐ CREATE THE LEDGER RECORD
            RentCharge.objects.create(
                tenant=tenant,
                amount=amount_to_charge,
                month=today.month,
                year=today.year
            )

            # 4. ⭐ RECALCULATE BALANCE
            # This calls the new method that sums up the RentCharge records
            tenant.update_balance()
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Successfully processed {count} rent charges.'))
import calendar
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Tenant, RentCharge

class Command(BaseCommand):
    help = 'Scans the database and updates status to expired for tenants whose leases have ended.'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        
        # Find tenants who are currently 'active' or 'notice_given' but their lease has expired
        expired_tenants = Tenant.objects.filter(
            status__in=['active', 'notice_given'],
            lease_end__lte=today  # __lte = "less than or equal" — catches today's expiries too
        )
        
        if not expired_tenants.exists():
            self.stdout.write(self.style.SUCCESS("All tenant leases are up to date. No expiries found."))
            return

        count = 0
        for tenant in expired_tenants:
            old_status = tenant.status
            lease_end = tenant.lease_end

            # ============================================================
            # ⭐ PRO-RATA MOVE-OUT: Recalculate the final month's charge
            # so the tenant only pays for the days they actually stayed.
            # Mirrors the pro-rata move-in logic in Tenant.save().
            # ============================================================
            days_in_month = calendar.monthrange(lease_end.year, lease_end.month)[1]

            # Billing starts from the 1st of the month, or their move-in date
            # if they moved in during that same month — whichever is later.
            month_start = lease_end.replace(day=1)
            billing_start = max(tenant.move_in_date, month_start)

            # Days they actually occupied the unit this month (inclusive of both ends)
            days_used = (lease_end - billing_start).days + 1

            if days_used > 0:
                daily_rate = Decimal(str(tenant.rent_amount)) / Decimal(days_in_month)
                pro_rata_amount = (daily_rate * Decimal(days_used)).quantize(Decimal('1.00'))

                # Update the existing RentCharge for this month if it exists
                final_charge = RentCharge.objects.filter(
                    tenant=tenant,
                    month=lease_end.month,
                    year=lease_end.year
                ).first()

                if final_charge:
                    old_amount = final_charge.amount
                    final_charge.amount = pro_rata_amount
                    final_charge.save()
                    self.stdout.write(
                        f"  Pro-rata adjustment: {tenant.user.get_full_name()} "
                        f"({days_used}/{days_in_month} days) "
                        f"KES {old_amount} → KES {pro_rata_amount}"
                    )

            # Expire the tenant and seal their final balance
            tenant.status = 'expired'
            tenant.save(update_fields=['status'])
            tenant.update_balance()
            
            self.stdout.write(
                self.style.WARNING(
                    f"Expired: {tenant.user.get_full_name()} (Unit {tenant.unit_number}) "
                    f"shifted from {old_status.upper()} to EXPIRED. Lease ended on {lease_end}."
                )
            )
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f"Successfully processed and closed {count} expired leases."))
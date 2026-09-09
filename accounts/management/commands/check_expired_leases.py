from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Tenant

class Command(BaseCommand):
    help = 'Scans the database and updates status to expired for tenants whose leases have ended.'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        
        # Find tenants who are currently 'active' or 'notice_given' but their lease has expired
        expired_tenants = Tenant.objects.filter(
            status__in=['active', 'notice_given'],
            lease_end__lt=today # __lt means "less than" (before today)
        )
        
        if not expired_tenants.exists():
            self.stdout.write(self.style.SUCCESS("All tenant leases are up to date. No expiries found."))
            return

        count = 0
        for tenant in expired_tenants:
            old_status = tenant.status
            tenant.status = 'expired'
            tenant.save(update_fields=['status'])  # Only UPDATE status — skips full save() override
            
            # Recalculate their ledger one final time to seal their final balance
            tenant.update_balance()
            
            self.stdout.write(
                self.style.WARNING(
                    f"Expired: {tenant.user.get_full_name()} (Unit {tenant.unit_number}) "
                    f"shifted from {old_status.upper()} to EXPIRED. Lease ended on {tenant.lease_end}."
                )
            )
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f"Successfully processed and closed {count} expired leases."))
from django.utils.functional import SimpleLazyObject
from .models import Tenant, CustomUser

def global_tenants(request):
    """
    Provides global data to all templates.
    Matches the name in settings.py: 'accounts.context_processors.global_tenants'
    """
    if request.user.is_authenticated and request.user.role == 'landlord':
        user = request.user

        # SimpleLazyObject defers the DB query until the template actually
        # iterates over it — avoids hitting the DB on pages that don't use it.
        def _get_tenants():
            return Tenant.objects.filter(
                assigned_property__landlord=user
            ).select_related('user', 'assigned_property').only(
                'id', 'unit_number',
                'user__first_name', 'user__last_name',
                'assigned_property__name',
            )

        return {
            'global_tenants': SimpleLazyObject(_get_tenants),
            # A fast .count() — fine to run on every page for the notification badge
            'pending_staff_count': CustomUser.objects.filter(
                role='maintenance',
                is_active=False,
                employer=user
            ).count(),
        }

    # Return empty if not a landlord or not logged in
    return {}
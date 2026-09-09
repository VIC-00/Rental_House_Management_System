from django.contrib import admin, messages as admin_messages
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Property, Tenant, Payment, MaintenanceRequest, Announcement, SentMessage, RentCharge


def approve_landlords(modeladmin, request, queryset):
    """Bulk action: approve selected landlord accounts."""
    landlords = queryset.filter(role='landlord', is_approved=False)
    count = landlords.update(is_approved=True)
    admin_messages.success(request, f"{count} landlord account(s) approved successfully.")

approve_landlords.short_description = "Approve selected landlord accounts"

# ==============================================================================
# --- 1. USER MANAGEMENT ---
# ==============================================================================

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    actions = [approve_landlords]
    
    # Adds custom fields to the edit screen — split into logical sections
    fieldsets = UserAdmin.fieldsets + (
        ('Property Management Info', {'fields': ('role', 'phone_number', 'specialization')}),
        ('Access & Account Flags', {'fields': ('employer', 'must_change_password', 'is_approved')}),
    )
    
    # Ensures these show up on the "Add User" screen
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role', 'phone_number', 'specialization', 'employer', 'must_change_password', 'is_approved')}),
    )
    
    list_display = ['username', 'email', 'role', 'is_approved', 'specialization', 'employer', 'must_change_password', 'is_staff', 'is_active']
    list_filter = ['role', 'is_approved', 'must_change_password', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'phone_number']


# ==============================================================================
# --- 2. PROPERTY & TENANCY ---
# ==============================================================================

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'total_units', 'monthly_revenue', 'landlord')
    search_fields = ('name', 'location')
    list_filter = ('landlord',)

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    # Shows the most important data at a glance
    list_display = ('user', 'assigned_property', 'unit_number', 'rent_amount', 'balance', 'status')
    
    # Filter by building or their current status (Active, Pending, etc.)
    list_filter = ('status', 'assigned_property')
    
    # Search by name or unit
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'unit_number')
    
    # Protect the balance and timestamps from accidental manual edits
    readonly_fields = ('balance', 'created_at', 'landlord_approved_at')


# ==============================================================================
# --- 3. FINANCIALS & OPERATIONS ---
# ==============================================================================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tenant', 'amount', 'method', 'date', 'status')
    list_filter = ('status', 'method', 'date')
    search_fields = ('transaction_id', 'tenant__user__username')
    ordering = ('-date',)

@admin.register(MaintenanceRequest)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('issue', 'tenant', 'assigned_to', 'priority', 'status', 'date_reported')
    list_filter = ('status', 'priority', 'date_reported')
    search_fields = ('issue', 'tenant__user__username', 'description')
    
    # Automatically tracks when the job was resolved
    readonly_fields = ('date_reported', 'updated_at', 'date_resolved')

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'date_posted', 'is_active')
    list_filter = ('is_active',)


# ==============================================================================
# --- 4. COMMUNICATIONS & BILLING AUDIT ---
# ==============================================================================

@admin.register(SentMessage)
class SentMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'sent_at', 'recipient_count', 'delivery_method')
    list_filter = ('delivery_method', 'sent_at')
    search_fields = ('subject', 'sender__username', 'sender__first_name')
    ordering = ('-sent_at',)
    readonly_fields = ('sent_at',)

@admin.register(RentCharge)
class RentChargeAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'amount', 'month', 'year', 'created_at')
    list_filter = ('year', 'month')
    search_fields = ('tenant__user__username', 'tenant__user__first_name', 'tenant__user__last_name')
    ordering = ('-year', '-month')
    readonly_fields = ('created_at',)
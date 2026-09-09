from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.conf import settings
from decimal import Decimal

# Named callables for model field defaults — lambdas can't be serialized by migrations
def get_current_month():
    return timezone.now().month

def get_current_year():
    return timezone.now().year

# ==============================================================================
# --- 1. CORE IDENTITY (User Accounts) ---
# ==============================================================================

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('landlord', 'Landlord'),
        ('tenant', 'Tenant'),
        ('maintenance', 'Maintenance Staff'),
    )
    
    email = models.EmailField(unique=True, null=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tenant')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)

    employer = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='staff_team',
        limit_choices_to={'role': 'landlord'}
    )

    must_change_password = models.BooleanField(default=False)
    is_approved = models.BooleanField(
        default=False,
        help_text="Landlord accounts require admin approval before gaining access."
    )
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

# ==============================================================================
# --- 2. PROPERTY ASSETS ---
# ==============================================================================

class Property(models.Model):
    landlord = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': 'landlord'},
        related_name='owned_properties',
    )
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    total_units = models.IntegerField(default=1)
    monthly_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

    @property
    def vacant_units(self):
        occupied = Tenant.objects.filter(assigned_property=self).count()
        return self.total_units - occupied

# ==============================================================================
# --- 3. TENANCY & FINANCIALS ---
# ==============================================================================


class RentCharge(models.Model):
    # ⭐ THE FIX: Use 'Tenant' as a string to avoid NameError
    tenant = models.ForeignKey(
        'Tenant', 
        on_delete=models.CASCADE,
        related_name='rent_charges' # Good practice to name the relationship
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.IntegerField()
    year = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'month', 'year')

    def __str__(self):
        return f"{self.tenant} - {self.month}/{self.year}"

class Tenant(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('notice_given', 'Notice Given'),
        ('approved', 'Move-out Approved'),
        ('moved_out', 'Moved Out'),
        ('expired', 'Lease Expired'),
    ]

    # --- 👤 Core Identity ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': 'tenant'},
        related_name='tenant_profile'
    )

    # --- 🏠 Residency Details (Strictly Required) ---
    # PROTECT ensures you can't delete a property while it still has active tenants
    assigned_property = models.ForeignKey(
        'Property', 
        on_delete=models.PROTECT,
        help_text="Building where the tenant resides."
    )
    unit_number = models.CharField(
        max_length=10,
        help_text="Specific door/unit number (e.g., A4)."
    ) 
    
    # --- 💰 Financials (Strictly Required) ---
    rent_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Monthly rent amount in KES."
    )
    balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    initial_rent_charged = models.BooleanField(default=False)
    
    # --- 📅 Timeline ---
    move_in_date = models.DateField(default=timezone.now) 
    
    # ⭐ THE ONLY OPTIONAL FIELD
    lease_end = models.DateField(null=True, blank=True)
    
    # --- ⚙️ Operational Status ---
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    
    # --- 🚪 Move-out Workflow ---
    intended_move_out_date = models.DateField(null=True, blank=True)
    move_out_reason = models.TextField(null=True, blank=True)
    
    notice_sent_at = models.DateTimeField(null=True, blank=True)
    landlord_approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name} - {self.assigned_property.name} (Unit {self.unit_number})"

    def update_balance(self):
        """
        Accounting Ledger: Sums all actual RentCharge records, 
        then subtracts Confirmed Payments. (Maintenance removed - handled as Landlord Expense).
        """
        from django.db.models import Sum
        from decimal import Decimal

        # 1. Total Rent Due
        total_rent_data = self.rent_charges.aggregate(
            total=Sum('amount'))['total'] or 0
        total_rent_due = Decimal(str(total_rent_data))

        # 2. Total Paid (Only 'confirmed' payments)
        total_paid_data = self.payment_set.filter(status='confirmed').aggregate(
            total=Sum('amount'))['total'] or 0
        total_paid = Decimal(str(total_paid_data))

        # 3. Final Balance Calculation (Strictly Rent vs Paid)
        self.balance = total_rent_due - total_paid
        
        # Save the result using the recursion safety lock
        self.save(update_fields=['balance'])

    def save(self, *args, **kwargs):
        """
        Overridden Save Method: Focuses strictly on financial ledger integrity.
        Instantly calculates pro-rata rent upon creation or updates it upon edits.
        """
        # 1. SAFETY CHECK: Avoid infinite recursion loop from update_balance()
        if kwargs.get('update_fields') == ['balance']:
            super().save(*args, **kwargs)
            return

        is_creation = self.pk is None
        rent_or_date_changed = False
        old_move_in = None

        if not is_creation:
            # Grab the old records from the DB before saving edit changes
            old_instance = Tenant.objects.get(pk=self.pk)
            if (old_instance.rent_amount != self.rent_amount) or (old_instance.move_in_date != self.move_in_date):
                rent_or_date_changed = True
                old_move_in = old_instance.move_in_date

        # 2. Save primary tenant details to the database first
        super().save(*args, **kwargs)

        import calendar
        from decimal import Decimal

        # ==========================================
        # 📊 CASE A: NEW TENANT LEDGER INITIALIZATION
        # ==========================================
        if is_creation:
            if not self.initial_rent_charged:
                # Calculate remaining days in their move-in month
                days_in_month = calendar.monthrange(self.move_in_date.year, self.move_in_date.month)[1]
                days_stayed = (days_in_month - self.move_in_date.day) + 1
                
                if days_stayed > 0:
                    daily_rate = Decimal(str(self.rent_amount)) / Decimal(days_in_month)
                    amount_to_charge = (daily_rate * Decimal(days_stayed)).quantize(Decimal('1.00'))
                    
                    # Instantly create the opening ledger record
                    RentCharge.objects.create(
                        tenant=self,
                        amount=amount_to_charge,
                        month=self.move_in_date.month,
                        year=self.move_in_date.year
                    )
                    
                    # Lock the initial charge flag so the script doesn't double bill them
                    self.initial_rent_charged = True
                    self.save(update_fields=['initial_rent_charged'])

            # Calculate and cache their starting profile balance right away
            self.update_balance()

        # ==========================================
        # 🔄 CASE B: EDITING AN EXISTING TENANT'S LEDGER
        # ==========================================
        elif rent_or_date_changed:
            days_in_month = calendar.monthrange(self.move_in_date.year, self.move_in_date.month)[1]
            days_stayed = (days_in_month - self.move_in_date.day) + 1

            # Find their original initial month charge
            initial_charge = self.rent_charges.filter(
                month=old_move_in.month,
                year=old_move_in.year
            ).first()

            if initial_charge and days_stayed > 0:
                # Sync the initial pro-rated invoice to the new rate and dates
                daily_rate = Decimal(str(self.rent_amount)) / Decimal(days_in_month)
                initial_charge.amount = (daily_rate * Decimal(days_stayed)).quantize(Decimal('1.00'))
                initial_charge.month = self.move_in_date.month
                initial_charge.year = self.move_in_date.year
                initial_charge.save()

            # Mass update all OTHER monthly charges to the new rent rate
            other_charges = self.rent_charges.all()
            if initial_charge:
                other_charges = other_charges.exclude(pk=initial_charge.pk)
            
            other_charges.update(amount=Decimal(str(self.rent_amount)))

            # Sync calculations across the cached profile row
            self.update_balance()

class Payment(models.Model):
    STATUS_CHOICES = (('confirmed', 'Confirmed'), ('pending', 'Pending'), ('failed', 'Failed'))
    METHOD_CHOICES = (('M-Pesa', 'M-Pesa'), ('Cash', 'Cash'), ('Bank', 'Bank Transfer'))
    
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="M-Pesa Code or Bank Reference")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    
    for_month = models.IntegerField(choices=MONTH_CHOICES, default=get_current_month)
    for_year = models.IntegerField(default=get_current_year)
    
    method = models.CharField(max_length=50, choices=METHOD_CHOICES, default='M-Pesa') 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"{self.tenant.user.username} - {self.get_for_month_display()} {self.for_year}"

# ==============================================================================
# --- 4. OPERATIONS (Maintenance & Comms) ---
# ==============================================================================

class MaintenanceRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),        
        ('assigned', 'Assigned'),      
        ('in_progress', 'In Progress'),
        ('completed', 'Completed')     
    )
    
    PRIORITY_CHOICES = (('high', 'High'), ('medium', 'Medium'), ('low', 'Low'))

    # ⭐ NEW: Intelligence Categories
    CATEGORY_CHOICES = (
        ('plumbing', 'Plumbing'),
        ('electrical', 'Electrical'),
        ('carpentry', 'Carpentry/Furniture'),
        ('appliances', 'Appliances'),
        ('painting', 'Painting/Walls'),
        ('other', 'Other'),
    )
    
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_tasks',
        limit_choices_to={'role': 'maintenance'}
    )

    issue = models.CharField(max_length=200)
    
    # ⭐ NEW: Operational Tracking
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', null=True, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    
    description = models.TextField()
    tech_notes = models.TextField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='low')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    date_reported = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) 
    date_resolved = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.status == 'completed' and not self.date_resolved:
            self.date_resolved = timezone.now()
        elif self.status != 'completed':
            self.date_resolved = None 
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.issue} - Unit {self.tenant.unit_number}"

class SentMessage(models.Model):
    subject = models.CharField(max_length=200)
    content = models.TextField()
    recipient_count = models.IntegerField()
    delivery_method = models.CharField(max_length=50) 
    sent_at = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.subject} (sent {self.sent_at.strftime('%Y-%m-%d')})"

class Announcement(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='announcements'
    )
    # The specific property (kept as optional)
    target_property = models.ForeignKey(
        'Property', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='property_announcements'
    )
    
    # ⭐ THE FIX: Add this explicit broadcast field
    is_broadcast = models.BooleanField(
        default=False, 
        help_text="If checked, this announcement will show for all your properties."
    )
    
    date_posted = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.target_property:
            self.is_broadcast = True
        else:
            self.is_broadcast = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
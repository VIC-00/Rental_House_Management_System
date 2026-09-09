from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from .models import Property, Tenant, Payment, MaintenanceRequest, CustomUser, Announcement
import datetime

# ==============================================================================
# --- 1. IDENTITY & ONBOARDING (Signup & Profile) ---
# ==============================================================================

class UserSignupForm(UserCreationForm):
    # --- 🏢 Tenant Specific Virtual Fields ---
    property_id = forms.ModelChoiceField(
        queryset=Property.objects.all(), 
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Property Name"
    )
    unit_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., A4'})
    )

    # --- 🛠️ Maintenance Specific Virtual Field ---
    target_landlord = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(role='landlord'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Hiring Landlord/Agency"
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # Included 'role' so the view knows what kind of profile to setup
        fields = ("first_name", "last_name", "username", "email", "phone_number")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email')
        
        # Note: 'employer' and 'role' are usually set in the view 
        # based on the POST data, but we process the base user here.
        if commit:
            user.save()
        return user

class UserUpdateForm(forms.ModelForm):
    # Explicitly defining fields ensures they are 'required' by default 
    # and prevents the NOT NULL database error.
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )
    phone_number = forms.CharField(
        required=False, # Keeping this optional as per your model
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +254...'})
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'username', 'email', 'phone_number']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Check if any OTHER user already has this email
        # self.instance.pk is the ID of the person we are currently editing
        if CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already registered to another account.")
        
        return email

class AddStaffForm(forms.ModelForm):
    # --- 👤 Basic Identity ---
    first_name = forms.CharField(
        max_length=30, 
        widget=forms.TextInput(attrs={'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30, 
        widget=forms.TextInput(attrs={'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'tech@example.com'})
    )
    phone_number = forms.CharField(
        max_length=15, 
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 0712345678'})
    )
    
    # --- 🛠️ Professional Details ---
    specialization = forms.CharField(
        max_length=100, 
        required=False, 
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Plumbing, Electrical, General'})
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'specialization']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control',
                'style': 'background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color);'
            })


# ==============================================================================
# --- 2. PROPERTY & TENANCY MANAGEMENT ---
# ==============================================================================

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['name', 'location', 'total_units', 'monthly_revenue', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Property Name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Westlands, Nairobi'}),
            'total_units': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Number of Units'}),
            'monthly_revenue': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'KES'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Brief description...', 'rows': 3}),
        }

    def clean_monthly_revenue(self):
        revenue = self.cleaned_data.get('monthly_revenue')
        if revenue is not None and revenue < 0:
            raise forms.ValidationError("Monthly revenue cannot be negative.")
        return revenue

    def clean_total_units(self):
        units = self.cleaned_data.get('total_units')
        if units is not None and units <= 0:
            raise forms.ValidationError("A property must have at least 1 unit.")
        return units

class AddTenantFullForm(forms.ModelForm):
    # --- 👤 Basic Identity (Strictly Required) ---
    first_name = forms.CharField(
        max_length=30, 
        widget=forms.TextInput(attrs={'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30, 
        widget=forms.TextInput(attrs={'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'tenant@example.com'})
    )
    phone_number = forms.CharField(
        max_length=15, 
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 0712345678'})
    )

    # --- 📅 Move-In (Required for Billing) ---
    move_in_date = forms.DateField(
        initial=timezone.now,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Move-in Date"
    )

    # ⭐ THE ONLY OPTIONAL FIELD
    lease_end = forms.DateField(
        required=False, 
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Lease End"
    )

    class Meta:
        model = Tenant
        fields = ['assigned_property', 'unit_number', 'rent_amount', 'move_in_date', 'lease_end']
        
    def __init__(self, *args, **kwargs):
        # We pop the user to ensure they only see THEIR properties
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # 1. Enforce Requirements
        self.fields['assigned_property'].required = True
        self.fields['unit_number'].required = True
        self.fields['rent_amount'].required = True

        # 2. Filter Properties by Landlord
        if user:
            self.fields['assigned_property'].queryset = Property.objects.filter(
                landlord=user
            ).order_by('name')
            # Rename the empty choice for clarity
            self.fields['assigned_property'].empty_label = "-- Select Property --"

        # 3. Apply CSS Classes & Placeholders
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
                'style': 'background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color);'
            })
            
        self.fields['unit_number'].widget.attrs.update({'placeholder': 'e.g., A4'})
        self.fields['rent_amount'].widget.attrs.update({'placeholder': 'Monthly Rent in KES'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # 1. Look for any existing user with this email
        # (Assuming your user model is 'CustomUser')
        from .models import CustomUser 
        user_search = CustomUser.objects.filter(email=email)
        
        # 2. If we are EDITING an existing tenant, we MUST exclude them 
        # from the search, otherwise they'll flag themselves as a duplicate!
        if self.instance and self.instance.pk:
            user_search = user_search.exclude(pk=self.instance.user.pk)
            
        if user_search.exists():
            raise forms.ValidationError("This email is already registered to another account.")
            
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        assigned_property = cleaned_data.get('assigned_property')
        unit_number = cleaned_data.get('unit_number')
        
        # Pull the dates for timeline verification
        move_in_date = cleaned_data.get('move_in_date')
        lease_end = cleaned_data.get('lease_end')

        # --- 1. Double Occupancy Check (Existing Fix) ---
        if assigned_property and unit_number:
            overlap = Tenant.objects.filter(
                assigned_property=assigned_property,
                unit_number=unit_number,
                status='active'
            ).exclude(pk=self.instance.pk).first()

            if overlap:
                self.add_error('unit_number', 
                    f"Occupied by {overlap.user.get_full_name()}."
                )

        # Timeline Flow Validation ---
        if move_in_date and lease_end:
            if lease_end <= move_in_date:
                self.add_error('lease_end', 
                    "The lease end date cannot be earlier than or equal to the move-in date."
                )

        return cleaned_data

class MoveOutRequestForm(forms.ModelForm):
    class Meta:
        model = Tenant
        # We only want the tenant to fill these two things
        fields = ['intended_move_out_date', 'move_out_reason']
        widgets = {
            'intended_move_out_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date', 
                'style': 'background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary);'
            }),
            'move_out_reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Reason for moving out (e.g., job relocation, end of lease)...',
                'style': 'background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary);'
            }),
        }
        
    def clean_intended_move_out_date(self):
        move_date = self.cleaned_data.get('intended_move_out_date')
        today = timezone.now().date()
        
        # 1. Past Date Check
        if move_date and move_date < today:
            raise forms.ValidationError("The move-out date cannot be in the past.")
        
        # 2. Minimum Notice Check (Optional: e.g., 30 days)
        # notice_period = today + timezone.timedelta(days=30)
        # if move_date and move_date < notice_period:
        #     raise forms.ValidationError("Management requires at least 30 days notice.")
            
        return move_date


# ==============================================================================
# --- 3. FINANCIALS (Payment Tracking) ---
# ==============================================================================

class PaymentForm(forms.ModelForm):
    # for_year choices are built dynamically in __init__ so they always reflect the real current year
    for_year = forms.ChoiceField(
        choices=[],  # populated in __init__
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Payment
        fields = ['tenant', 'amount', 'for_month', 'for_year', 'transaction_id', 'method', 'status']
        widgets = {
            'tenant': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'KES'}),
            'for_month': forms.Select(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Transaction Reference'}),
            'method': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Payment amount must be a positive number greater than zero.")
        return amount

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        # Build year choices fresh so the correct year is always shown
        current_year = datetime.date.today().year
        self.fields['for_year'].choices = [(y, y) for y in range(current_year - 1, current_year + 2)]
        self.fields['for_year'].initial = current_year
        # Tell Django to stop forcing this field to be required by default
        self.fields['transaction_id'].required = False

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('method')
        transaction_id = cleaned_data.get('transaction_id')

        # Rule 1: M-Pesa payments MUST have a Transaction ID
        if method == 'M-Pesa' and not transaction_id:
            self.add_error('transaction_id', "M-Pesa payments must include a valid Transaction ID.")
        
        # Rule 2: Cash payments should NOT have a Transaction ID
        if method == 'Cash' and transaction_id:
            self.add_error('transaction_id', "Cash payments should not have a Transaction ID. Please leave it blank.")

        return cleaned_data
    
    def clean_transaction_id(self):
        tid = self.cleaned_data.get('transaction_id')
        if tid:
            # Clean the ID (convert to uppercase so 'sdr' and 'SDR' match)
            tid = tid.strip().upper()
            
            # Check if this ID already exists in another payment
            # We exclude the current instance in case we are editing an existing payment
            exists = Payment.objects.filter(transaction_id=tid).exclude(pk=self.instance.pk).exists()
            
            if exists:
                raise forms.ValidationError("This Transaction ID has already been used.")
            return tid
        return None

class TenantPaymentForm(forms.ModelForm):
    # for_year choices are built dynamically in __init__ so they always reflect the real current year
    for_year = forms.ChoiceField(
        choices=[],  # populated in __init__
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Payment
        fields = ['amount', 'for_month', 'for_year', 'transaction_id', 'method']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount in KES'}),
            'for_month': forms.Select(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., RGR57TY90'}),
            'method': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'transaction_id': 'M-Pesa Code / Reference ID',
            'for_month': 'Paying for Month',
            'for_year': 'Year'
        }

    def __init__(self, *args, **kwargs):
        super(TenantPaymentForm, self).__init__(*args, **kwargs)
        # Build year choices fresh so the correct year is always shown
        current_year = datetime.date.today().year
        self.fields['for_year'].choices = [(y, y) for y in range(current_year - 1, current_year + 2)]
        self.fields['for_year'].initial = current_year

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('method')
        transaction_id = cleaned_data.get('transaction_id')

        # Rule 1: M-Pesa MUST have a code
        if method == 'M-Pesa' and not transaction_id:
            self.add_error('transaction_id', "Please provide your M-Pesa transaction code.")
        
        # ⭐ THE FIX: Rule 2: Cash MUST NOT have a code
        if method == 'Cash' and transaction_id:
            self.add_error('transaction_id', "Cash payments should not have a Transaction ID. Please leave it blank.")

        return cleaned_data
    
    def clean_transaction_id(self):
        tid = self.cleaned_data.get('transaction_id')
        if tid:
            # Clean the ID (convert to uppercase so 'sdr' and 'SDR' match)
            tid = tid.strip().upper()
            
            # Check if this ID already exists in another payment
            # We exclude the current instance in case we are editing an existing payment
            exists = Payment.objects.filter(transaction_id=tid).exclude(pk=self.instance.pk).exists()
            
            if exists:
                raise forms.ValidationError("This Transaction ID has already been used.")
            return tid
        return None

# ==============================================================================
# --- 4. OPERATIONS (Maintenance & Announcements) ---
# ==============================================================================

class MaintenanceForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['tenant', 'issue', 'category', 'priority', 'status', 'cost', 'description', 'tech_notes']
        widgets = {
            'tenant': forms.Select(attrs={'class': 'form-control'}),
            'issue': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Repair Cost (KES)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'tech_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super(MaintenanceForm, self).__init__(*args, **kwargs)
        # ⭐ Optimization: Make Category optional so it doesn't block the save
        self.fields['category'].required = False

class TenantMaintenanceRequestForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['issue', 'category', 'description', 'priority'] 
        widgets = {
            'issue': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'What is the problem?'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Explain in detail...'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(TenantMaintenanceRequestForm, self).__init__(*args, **kwargs)
        self.fields['category'].required = False

class MaintenanceAssignmentForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['assigned_to', 'category', 'priority'] 
        widgets = {
            'assigned_to': forms.Select(attrs={'class': 'form-control custom-select'}),
            'category': forms.Select(attrs={'class': 'form-control custom-select'}),
            'priority': forms.Select(attrs={'class': 'form-control custom-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(MaintenanceAssignmentForm, self).__init__(*args, **kwargs)
        
        # ⭐ Optimization: Category shouldn't block assignment
        self.fields['category'].required = False
        
        if user:
            self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                role='maintenance', 
                employer=user,
                is_active=True
            ).order_by('first_name')
        else:
            self.fields['assigned_to'].queryset = CustomUser.objects.none()

class MaintenanceTaskUpdateForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        # ⭐ THE FIX: Added 'cost' to fields
        fields = ['status', 'category', 'cost', 'tech_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            # ⭐ THE FIX: Added design widget for cost input
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Total Cost of Materials/Labor (KES)'}),
            'tech_notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Explain what you fixed or if more parts are needed...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(MaintenanceTaskUpdateForm, self).__init__(*args, **kwargs)
        self.fields['category'].required = False
        
        current_choices = self.fields['status'].choices
        self.fields['status'].choices = [
            (code, label) for code, label in current_choices if code != 'pending'
        ]

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        # Added 'target_property' to the fields list
        fields = ['title', 'content', 'target_property']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Subject (e.g., Water Outage)',
                'style': 'background: var(--input-bg); color: var(--text-primary); border-radius: 8px;'
            }),
            'target_property': forms.Select(attrs={
                'class': 'form-control',
                'style': 'background: var(--input-bg); color: var(--text-primary); border-radius: 8px; margin-top: 10px;'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Details for the tenants...',
                'style': 'background: var(--input-bg); color: var(--text-primary); border-radius: 8px; margin-top: 10px;'
            }),
        }

    def __init__(self, *args, **kwargs):
        # 1. Pop the user from kwargs so it doesn't break the base form
        user = kwargs.pop('user', None)
        super(AnnouncementForm, self).__init__(*args, **kwargs)
        
        if user:
            # 2. Filter the dropdown to only show THIS landlord's properties
            self.fields['target_property'].queryset = Property.objects.filter(landlord=user)
            # 3. Rename the empty option (None) to be a "Broadcast" option
            self.fields['target_property'].empty_label = "📢 Broadcast to All My Properties"
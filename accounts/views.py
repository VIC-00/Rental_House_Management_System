import csv
import json
import datetime 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout,update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Sum, Count, Q, Avg, F, ProtectedError
from .models import Property, Tenant, Payment, MaintenanceRequest, CustomUser, SentMessage, Announcement
from .forms import PropertyForm, AddTenantFullForm, UserSignupForm, PaymentForm, MaintenanceForm, TenantMaintenanceRequestForm, AnnouncementForm, MoveOutRequestForm, UserUpdateForm,TenantPaymentForm, MaintenanceTaskUpdateForm, MaintenanceAssignmentForm, AddStaffForm
from django.urls import reverse
from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.db import IntegrityError,transaction
from decimal import Decimal, InvalidOperation


# ==============================================================================
# --- 1. MASTER AUTHENTICATION & PROFILE SETTINGS ---
# ==============================================================================

# --- 1. MASTER AUTHENTICATION (Login & Signup) ---
def login_view(request):
    """
    Handles authentication for Landlords, Tenants, and Maintenance Staff.
    Includes a security gatekeeper for temporary passwords.
    """
    # 1. Redirect already logged-in users to their respective dashboards
    if request.user.is_authenticated:
        if request.user.role == 'tenant':
            return redirect('tenant_dashboard')
        elif request.user.role == 'maintenance':
            return redirect('maintenance_dashboard')
        else:
            return redirect('dashboard')

    if request.method == 'POST':
        # --- CASE A: SIGNUP LOGIC ---
        if 'signup_submit' in request.POST:
            form = UserSignupForm(request.POST)
            if form.is_valid():
                selected_role = request.POST.get('role_selection') 
                
                # 🏠 TENANT SIGNUP
                if selected_role == 'tenant':
                    property_id = request.POST.get('property_id')
                    unit_number = request.POST.get('unit_number')
                    if not property_id or not unit_number:
                        messages.error(request, "Property Name and Unit Number are required for Tenant registration.")
                        return render(request, 'login.html', {
                            'form': form,
                            'properties': Property.objects.all(),
                            'landlords': CustomUser.objects.filter(role='landlord')
                        })
                    
                    user = form.save(commit=False)
                    user.role = 'tenant'
                    user.save()
                    Tenant.objects.create(
                        user=user,
                        assigned_property_id=property_id,
                        unit_number=unit_number,
                        status='pending',
                        rent_amount=0
                    )
                    messages.success(request, "Tenant account created! Please wait for management approval.")
                    return redirect('login')
                
                # 🛠️ MAINTENANCE STAFF SIGNUP
                elif selected_role == 'maintenance':
                    user = form.save(commit=False)
                    user.role = 'maintenance'
                    user.is_active = False  
                    user.specialization = request.POST.get('specialization')
                    
                    # Link to target Landlord for approval
                    target_landlord_id = request.POST.get('target_landlord')
                    if target_landlord_id:
                        user.employer_id = target_landlord_id
                    
                    user.save()
                    messages.success(request, "Staff registration received. Your target landlord will review your application.")
                    return redirect('login')
                
                # 🔑 LANDLORD SIGNUP
                else:
                    user = form.save(commit=False)
                    user.role = 'landlord'
                    user.save()
                    login(request, user)
                    messages.success(request, "Landlord account created successfully!")
                    return redirect('dashboard')
            else:
                for field, errors in form.errors.items():
                    messages.error(request, f"{field.replace('_', ' ').title()}: {errors[0]}")

        # --- CASE B: LOGIN LOGIC ---
        else:
            identifier = request.POST.get('username')
            pass_word = request.POST.get('password')
            
            # Allow login via Username OR Email
            user_obj = CustomUser.objects.filter(Q(username=identifier) | Q(email=identifier)).first()

            if user_obj:
                # Security: Block inactive maintenance staff (not yet approved by landlord)
                if not user_obj.is_active and user_obj.role == 'maintenance':
                    messages.warning(request, "Your staff account is still awaiting approval.")
                    return redirect('login')

                user = authenticate(request, username=user_obj.username, password=pass_word)
                if user is not None:
                    # Security: Block pending tenants
                    if user.role == 'tenant':
                        tenant_profile = Tenant.objects.filter(user=user).first()
                        if tenant_profile and tenant_profile.status == 'pending':
                            messages.warning(request, "Tenant approval pending.")
                            return redirect('login')
                    
                    # ⭐ LOG THE USER IN
                    login(request, user)

                    # 🛡️ THE SECURITY INTERCEPTOR
                    # If the landlord added them manually, they MUST change their phone-number password
                    if user.must_change_password:
                        messages.info(request, "For your security, please update your password before continuing.")
                        return redirect('change_password')

                    # Final Redirects based on Role
                    if user.role == 'tenant': return redirect('tenant_dashboard')
                    elif user.role == 'maintenance': return redirect('maintenance_dashboard')
                    else: return redirect('dashboard')
                else:
                    messages.error(request, "Incorrect password.")
            else:
                messages.error(request, "User account not found.")

    # GET Request: Prepare signup context
    return render(request, 'login.html', {
        'form': UserSignupForm(),
        'properties': Property.objects.all(),
        'landlords': CustomUser.objects.filter(role='landlord')
    })

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def profile_settings(request):
    """
    Handles both profile information updates and secure password changes 
    on a single page for the logged-in user.
    """
    if request.method == 'POST':
        # 1. Handle Profile Info Update (First Name, Email, Phone, etc.)
        if 'update_profile' in request.POST:
            profile_form = UserUpdateForm(request.POST, instance=request.user)
            # Initialize the password form so it's available in the context if validation fails
            password_form = PasswordChangeForm(request.user)
            
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Your profile details have been updated!')
                return redirect('profile_settings')
            else:
                messages.error(request, 'Please correct the profile errors below.')
        
        # 2. Handle Password Change using Django's built-in validation
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            # Initialize the profile form so it's available in the context if validation fails
            profile_form = UserUpdateForm(instance=request.user)
            
            if password_form.is_valid():
                user = password_form.save()
                #  Keeps the user logged in by updating the session hash
                update_session_auth_hash(request, user)
                messages.success(request, 'Your password was successfully updated!')
                return redirect('profile_settings')
            else:
                messages.error(request, 'Password change failed. See errors below.')

    # If GET request, pre-fill forms with current user data
    else:
        profile_form = UserUpdateForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'profile_settings.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'tenant': getattr(request.user, 'tenant_profile', None) # Useful if you need tenant-specific info
    })

@login_required(login_url='login')
def settings_view(request):
    user = request.user
    
    if request.method == 'POST':
        # --- 1. Handle Profile Update ---
        if 'update_profile' in request.POST:
            user.first_name = request.POST.get('first_name')
            user.last_name = request.POST.get('last_name')
            user.username = request.POST.get('username')
            user.email = request.POST.get('email')
            user.phone_number = request.POST.get('phone_number')
            
            if not user.first_name or not user.last_name:
                messages.error(request, "First and Last names are required.")
            else:
                user.save()
                messages.success(request, "Profile updated successfully!")
            return redirect('settings')

        # --- 2. Handle Password Change ---
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            
            if password_form.is_valid():
                # Custom Check: Ensure the new password isn't the same as the old one
                new_password = password_form.cleaned_data.get('new_password1')
                if user.check_password(new_password):
                    messages.error(request, "New password cannot be the same as your old password.")
                else:
                    user = password_form.save()
                    update_session_auth_hash(request, user) # Prevents logout
                    messages.success(request, "Password updated successfully!")
                    return redirect('settings')
            else:
                # If form is invalid (mismatch, too short, etc.), Django adds errors to password_form
                messages.error(request, "Please correct the password errors below.")

    # GET Request
    else:
        password_form = PasswordChangeForm(user)

    return render(request, 'settings.html', {'password_form': password_form})


# ==============================================================================
# --- 2. LANDLORD DASHBOARD & MASTER VIEWS ---
# ==============================================================================

# --- 2. DASHBOARD ---
@login_required(login_url='login') 
def dashboard_view(request):
    if request.user.role != 'landlord':
        return redirect('tenant_dashboard')

    my_properties = Property.objects.filter(landlord=request.user)
    today = timezone.now()
    
    # 1. Move-Out Notice Count
    move_out_notices = Tenant.objects.filter(
        assigned_property__in=my_properties, 
        status='notice_given'
    ).count()

    # 2. Announcement Handling
    if request.method == 'POST' and 'post_announcement' in request.POST:
        announcement_form = AnnouncementForm(request.POST, user=request.user)
        if announcement_form.is_valid():
            announcement = announcement_form.save(commit=False)
            announcement.author = request.user 
            announcement.save()
            messages.success(request, "Announcement broadcasted!")
            return redirect('dashboard')
    else:
        announcement_form = AnnouncementForm(user=request.user)

    # 3. Monthly Financials & Chart Data
    prop_names = []
    prop_revenues = []
    total_monthly_collection = 0

    for prop in my_properties:
        prop_names.append(prop.name)
        
        # ⭐ Updated Logic: Revenue for the CURRENT calendar month
        # This matches the new "Monthly Billing" focus
        revenue = Payment.objects.filter(
            tenant__assigned_property=prop, 
            status='confirmed',
            date__year=today.year,
            date__month=today.month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        prop_revenues.append(float(revenue))
        total_monthly_collection += revenue

    # 4. Maintenance Overview
    maint_requests = MaintenanceRequest.objects.filter(tenant__assigned_property__in=my_properties)
    pending_count = maint_requests.filter(status='pending').count()
    maint_data = [
        pending_count, 
        maint_requests.filter(status='in_progress').count(), 
        maint_requests.filter(status='completed').count()
    ]

    # 5. Activity Tables
    recent_payments = Payment.objects.filter(
        tenant__assigned_property__in=my_properties
    ).select_related('tenant__user', 'tenant__assigned_property').order_by('-date')[:5]

    recent_requests = MaintenanceRequest.objects.filter(
        tenant__assigned_property__in=my_properties
    ).select_related('tenant__user', 'tenant__assigned_property').order_by('-date_reported')[:5]

    # 6. Final Context
    context = {
        'total_properties': my_properties.count(),
        'active_tenants': Tenant.objects.filter(assigned_property__in=my_properties, status='active').count(),
        'move_out_notices': move_out_notices,
        # ⭐ Now shows "Collection for this month" formatted for KES
        'total_rent': f"{int(total_monthly_collection):,}", 
        'pending_maintenance': pending_count,
        'recent_payments': recent_payments,
        'recent_requests': recent_requests,
        'announcement_form': announcement_form,
        'prop_names': prop_names,
        'prop_revenues': prop_revenues,
        'maint_data': maint_data,
    }
    return render(request, 'dashboard.html', context)

# --- 3. PROPERTIES ---
@login_required(login_url='login')
def properties_view(request):
    my_properties = Property.objects.filter(landlord=request.user)
    
    query = request.GET.get('q', '')
    if query:
        properties = my_properties.filter(
            Q(name__icontains=query) | Q(location__icontains=query)
        )
    else:
        properties = my_properties

    total_units = properties.aggregate(Sum('total_units'))['total_units__sum'] or 0
    occupied = Tenant.objects.filter(assigned_property__in=properties).count()
    total_revenue = properties.aggregate(Sum('monthly_revenue'))['monthly_revenue__sum'] or 0
    
    context = {
        'properties': properties,
        'total_properties': properties.count(),
        'occupied_units': occupied,
        'vacant_units': total_units - occupied,
        'total_portfolio_value': f"{total_revenue:,.0f}",
        'query': query,
    }
    return render(request, 'properties.html', context)

# --- 4. TENANTS ---
@login_required(login_url='login')
def tenants_view(request):
    search_query = request.GET.get('q', '')
    property_filter = request.GET.get('property_id', 'all')

    # Base queryset for all tenants linked to this landlord
    all_landlord_tenants = Tenant.objects.filter(
        assigned_property__landlord=request.user
    ).select_related('user', 'assigned_property')

    # 1. NEW SIGNUPS: Filter for those in 'pending' status
    pending_tenants = all_landlord_tenants.filter(status='pending')

    # 2. MAIN DIRECTORY: Filter for those already approved/active
    tenants = all_landlord_tenants.exclude(status='pending')

    # Apply search and property filters to the main list
    if property_filter != 'all':
        tenants = tenants.filter(assigned_property_id=property_filter)
    
    if search_query:
        tenants = tenants.filter(
            Q(user__first_name__icontains=search_query) | 
            Q(user__last_name__icontains=search_query) |
            Q(unit_number__icontains=search_query)
        )

    # --- DYNAMIC COUNTERS (Excess Payment Aware) ---
    
    # Move-out notices don't care about balance
    move_out_notices = tenants.filter(status='notice_given').count()
    
    # THE FIX: Good Standing now includes balances of 0 AND negative (Credits)
    standing_count = tenants.filter(balance__lte=0, status='active').count()
    
    # THE FIX: Overdue is strictly for tenants who OWE money (Balance > 0)
    overdue_count = tenants.filter(balance__gt=0, status='active').count()

    context = {
        'tenants': tenants,
        'pending_tenants': pending_tenants,
        'properties': Property.objects.filter(landlord=request.user),
        'standing_count': standing_count,
        'overdue_count': overdue_count,
        'move_out_notices': move_out_notices,
        'query': search_query,
        'selected_property': property_filter,
    }
    return render(request, 'tenants.html', context)

# --- 5. PAYMENTS ---
@login_required(login_url='login')
def payments_view(request):
    status_filter = request.GET.get('status', 'all')
    # This is the "Time Paid" filter (HTML type="month")
    date_paid_filter = request.GET.get('month', '') 
    # ⭐ This is your new "Billing Period" dropdown
    billing_month_filter = request.GET.get('billing_month')

    # Base queryset
    payments = Payment.objects.filter(
        tenant__assigned_property__landlord=request.user
    ).select_related('tenant__user', 'tenant__assigned_property').order_by('-date')

    # 1. Filter by Status (Confirmed/Pending)
    if status_filter != 'all':
        payments = payments.filter(status=status_filter)
    
    # 2. Filter by "When they paid" (Transaction Date)
    if date_paid_filter:
        try:
            year, month = map(int, date_paid_filter.split('-'))
            payments = payments.filter(date__year=year, date__month=month)
        except ValueError:
            pass

    # 3. ⭐ NEW: Filter by "What they paid for" (Billing Month)
    if billing_month_filter and billing_month_filter != "":
        payments = payments.filter(for_month=billing_month_filter)

    # --- FINANCIAL CALCULATIONS (Keep as is) ---
    expected = Property.objects.filter(landlord=request.user).aggregate(Sum('monthly_revenue'))['monthly_revenue__sum'] or 0
    total_confirmed = payments.filter(status='confirmed').aggregate(Sum('amount'))['amount__sum'] or 0
    total_pending = payments.filter(status='pending').aggregate(Sum('amount'))['amount__sum'] or 0
    
    rate = (total_confirmed / expected * 100) if expected > 0 else 0

    context = {
        'payments': payments,
        'total_collected': f"{total_confirmed:,.0f}",
        'total_pending': f"{total_pending:,.0f}",
        'expected_total': f"{expected:,.0f}",
        'collection_rate': round(rate, 1),
        'selected_status': status_filter,
        'selected_month': date_paid_filter,
    }
    return render(request, 'payments.html', context)

# --- 6. MAINTENANCE ---
@login_required(login_url='login')
def maintenance_view(request):
    # Ensure only landlords can access this view
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    status_filter = request.GET.get('status', 'all')
    
    # 1. Fetch Maintenance Tasks (Filtered by properties owned by THIS landlord)
    requests = MaintenanceRequest.objects.filter(
        tenant__assigned_property__landlord=request.user
    ).select_related(
        'tenant__user', 
        'tenant__assigned_property', 
        'assigned_to'
    ).order_by('-date_reported')

    # Apply status filter if selected
    if status_filter != 'all':
        requests = requests.filter(status=status_filter)

    # --- THE NOTIFICATION FIX ---
    # Only count unapproved maintenance staff who specifically applied to THIS landlord
    pending_staff_count = CustomUser.objects.filter(
        role='maintenance', 
        is_active=False,
        employer=request.user  #  This prevents the "leak" to other landlords
    ).count()

    # 2. Stats Calculations (Filtered to this landlord's tasks)
    open_count = requests.filter(status='pending').count()
    progress_count = requests.filter(status='in_progress').count()
    completed_count = requests.filter(status='completed').count()

    # 3. Calculate Average Resolution Time
    resolved_tasks = requests.filter(status='completed', date_resolved__isnull=False)
    avg_timedelta = resolved_tasks.aggregate(
        avg_time=Avg(F('date_resolved') - F('date_reported'))
    )['avg_time']
    
    if avg_timedelta:
        days = avg_timedelta.days
        avg_display = f"{days} Days" if days > 0 else "Under 24h"
    else:
        avg_display = "---"

    context = {
        'maintenance_requests': requests,
        'open_count': open_count,
        'progress_count': progress_count,
        'completed_count': completed_count,
        'avg_resolution': avg_display,
        'selected_status': status_filter,
        'pending_staff_count': pending_staff_count, # Red badge count
    }
    
    return render(request, 'maintenance.html', context)

from django.db.models import Subquery, OuterRef

@login_required(login_url='login')
def reports_view(request):
    if request.user.role != 'landlord':
        return redirect('tenant_dashboard')

    # 1. Safe Date Parsing (Prevents 500 errors on bad date strings)
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        if not start_date_str or not end_date_str:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        messages.error(request, "Invalid date format provided.")
        return redirect('reports')

    # 2. Optimized Property Data (One Query to Rule Them All)
    # We use Subquery to calculate 'collected' for each property in the main QuerySet
    period_payments = Payment.objects.filter(
        tenant__assigned_property=OuterRef('pk'),
        status='confirmed',
        date__date__range=[start_date, end_date]
    ).values('tenant__assigned_property').annotate(total=Sum('amount')).values('total')

    my_properties = Property.objects.filter(landlord=request.user).annotate(
        actual_collected=Subquery(period_payments)
    )

    prop_data = []
    total_confirmed_period = 0
    
    for p in my_properties:
        collected = p.actual_collected or Decimal('0.00')
        total_confirmed_period += collected
        
        # Calculate Stats
        tenant_count = p.tenant_set.count() # You can also annotate this for more speed!
        efficiency = (collected / p.monthly_revenue * 100) if p.monthly_revenue > 0 else 0
        
        prop_data.append({
            'name': p.name,
            'target': p.monthly_revenue,
            'collected': collected,
            'shortfall': p.monthly_revenue - collected,
            'occupancy': (tenant_count / p.total_units * 100) if p.total_units > 0 else 0,
            'efficiency': round(efficiency, 1),
            'total_units': p.total_units,
            'vacant': p.total_units - tenant_count
        })

    # 3. Maintenance Intelligence (Cast to list for JSON/Chart.js safety)
    maint_stats = list(MaintenanceRequest.objects.filter(
        tenant__assigned_property__landlord=request.user,
        status='completed',
        date_resolved__date__range=[start_date, end_date]
    ).values('category').annotate(
        total_cost=Sum('cost'),
        task_count=Count('id')
    ).order_by('-total_cost'))

    # 4. Global Financial Truths
    all_landlord_tenants = Tenant.objects.filter(assigned_property__landlord=request.user)
    total_arrears = all_landlord_tenants.filter(balance__gt=0).aggregate(Sum('balance'))['balance__sum'] or 0
    total_credits = abs(all_landlord_tenants.filter(balance__lt=0).aggregate(Sum('balance'))['balance__sum'] or 0)

    context = {
        'prop_data': prop_data,
        'total_confirmed': total_confirmed_period,
        'total_arrears': total_arrears,
        'total_credits': total_credits,
        'maint_stats': maint_stats,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'total_units': my_properties.aggregate(Sum('total_units'))['total_units__sum'] or 0,
        'total_occupied': all_landlord_tenants.count(),
        'all_tenants_with_balance': all_landlord_tenants.exclude(balance=0).select_related('user', 'assigned_property').order_by('-balance'),
    }
    
    return render(request, 'reports.html', context)


# ==============================================================================
# --- 3. TENANT PORTAL VIEWS ---
# ==============================================================================

@login_required(login_url='login') 
def tenant_dashboard(request):
    # 1. Password Security Guard
    if request.user.must_change_password:
        messages.info(request, "For your security, please update your password.")
        return redirect('change_password')

    # 2. Role Check
    if request.user.role != 'tenant':
        return redirect('dashboard')
    
    tenant_profile = get_object_or_404(Tenant, user=request.user)

    # 3. Approval Gatekeeper
    if tenant_profile.status == 'pending':
        return render(request, 'tenants/pending_approval.html', {'tenant': tenant_profile})
    
    # --- 4. HANDLE WORKFLOW LOGIC (POST) ---
    if request.method == 'POST':
        # SUBMIT MOVE-OUT NOTICE
        if 'submit_move_out' in request.POST:
            form = MoveOutRequestForm(request.POST, instance=tenant_profile)
            if form.is_valid():
                # ⭐ THE FIX: Save the form tracking dates and reasons directly
                tenant_profile = form.save(commit=False)
                tenant_profile.status = 'notice_given'
                tenant_profile.notice_sent_at = timezone.now()
                tenant_profile.save()
                
                messages.warning(request, "Your move-out request has been sent to management.")
                return redirect('tenant_dashboard')
            else:
                # If form is invalid, send the errors along to the template instead of a silent failure
                messages.error(request, "Please correct the errors in your move-out request form.")

        # CANCEL MOVE-OUT NOTICE
        elif 'cancel_move_out' in request.POST:
            if tenant_profile.status == 'notice_given':
                tenant_profile.status = 'active'
                tenant_profile.intended_move_out_date = None
                tenant_profile.move_out_reason = ""
                tenant_profile.notice_sent_at = None
                tenant_profile.save()
                messages.info(request, "Your move-out notice has been successfully cancelled.")
                return redirect('tenant_dashboard')

    # --- 5. FETCH DATA FOR DISPLAY ---
    move_out_form = MoveOutRequestForm(instance=tenant_profile)
    
    # We now look for either the explicit "is_broadcast" flag 
    # OR if the announcement was specifically targeted to this tenant's property.
    announcements = Announcement.objects.filter(
        Q(is_broadcast=True) | Q(target_property=tenant_profile.assigned_property),
        is_active=True
    ).order_by('-date_posted')[:3]


    my_payments = Payment.objects.filter(tenant=tenant_profile).order_by('-date')[:5]

    # ⭐ INTELLIGENCE FIX: Separate Active vs. Completed Maintenance
    # Fetch all tasks linked to this tenant
    all_tenant_requests = MaintenanceRequest.objects.filter(tenant=tenant_profile)
    
    # 1. Active: Anything not completed (shown in the stat card and "Current Repairs" list)
    active_requests = all_tenant_requests.exclude(status='completed').order_by('-date_reported')
    
    # 2. History: Recently completed items (shown in the "Archive" link/history view)
    completed_requests = all_tenant_requests.filter(status='completed').order_by('-date_resolved')[:3]

    context = {
        'tenant': tenant_profile,
        'property': tenant_profile.assigned_property,
        'payments': my_payments,
        'requests': active_requests, # ⭐ Now strictly shows active jobs for the counter
        'completed_requests': completed_requests,
        'announcements': announcements,
        'move_out_form': move_out_form,
        
        # Clean Math for the UI
        'rounded_balance': int(tenant_profile.balance),
        # Extra: Send a count of "In Progress" specifically for the progress bar if needed
        'in_progress_count': active_requests.filter(status='in_progress').count(),
    }
    
    return render(request, 'tenants/tenant_dashboard.html', context)

@login_required
def report_issue(request):
    # Security: Ensure only tenants can report issues here
    if request.user.role != 'tenant':
        return redirect('dashboard')
    
    tenant_profile = Tenant.objects.get(user=request.user)

    if request.method == 'POST':
        form = TenantMaintenanceRequestForm(request.POST)
        if form.is_valid():
            # commit=False lets us fill in the tenant hidden from the form
            new_request = form.save(commit=False)
            new_request.tenant = tenant_profile
            new_request.status = 'pending' # Default status for new issues
            new_request.save()
            
            messages.success(request, "Maintenance request submitted successfully!")
            return redirect('tenant_dashboard')
    else:
        form = TenantMaintenanceRequestForm()
    
    return render(request, 'tenants/report_issue.html', {'form': form})

@login_required
def report_payment(request):
    # 1. More reliable way to find the tenant profile
    try:
        # This looks for the Tenant object where the 'user' field matches the current user
        tenant_profile = Tenant.objects.get(user=request.user)
    except Tenant.DoesNotExist:
        messages.error(request, "Error: No tenant profile found for this account.")
        return redirect('login')

    if request.method == 'POST':
        form = TenantPaymentForm(request.POST)
        if form.is_valid():
            # commit=False keeps it in memory so we can add the tenant
            payment = form.save(commit=False)
            
            # 2. Assign the tenant profile we found above
            payment.tenant = tenant_profile
            payment.status = 'pending'
            
            try:
                payment.save()
                messages.success(request, "Payment reported! Management will verify the transaction code shortly.")
                return redirect('tenant_dashboard')
            except IntegrityError as e:
                messages.error(request, f"Database Error: {str(e)}")
    else:
        form = TenantPaymentForm(initial={'method': 'M-Pesa'})
        
    return render(request, 'tenants/report_payment.html', {'form': form})

@login_required
def payment_history(request):
    """Shows a full list of all payments (pending and confirmed) for the logged-in tenant."""
    if request.user.role != 'tenant':
        return redirect('dashboard')
        
    tenant_profile = get_object_or_404(Tenant, user=request.user)
    all_payments = Payment.objects.filter(tenant=tenant_profile).order_by('-date')
    
    return render(request, 'tenants/payment_history.html', {
        'all_payments': all_payments,
        'tenant': tenant_profile
    })

@login_required
def maintenance_history(request):
    """Shows a full archive of all maintenance requests (Resolved and Pending) for the tenant."""
    if request.user.role != 'tenant':
        return redirect('dashboard')

    tenant_profile = get_object_or_404(Tenant, user=request.user)
    all_requests = MaintenanceRequest.objects.filter(tenant=tenant_profile).order_by('-date_reported')
    
    return render(request, 'tenants/maintenance_history.html', {
        'all_requests': all_requests,
        'tenant': tenant_profile
    })


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            
            # ⭐ THE SECURITY KEY: Flip the flag back to False
            user.must_change_password = False
            user.save()
            
            # Keep the user logged in after password change (prevents session log out)
            update_session_auth_hash(request, user)
            
            messages.success(request, 'Your password was successfully updated!')
            
            # ⭐ ROLE-BASED REDIRECT: Send them to their specific home base
            if user.role == 'tenant':
                return redirect('tenant_dashboard')
            elif user.role == 'maintenance':
                return redirect('maintenance_dashboard')
            
            # Default for Landlords
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'change_password.html', {'form': form})

# ==============================================================================
# --- 4. MAINTENANCE & STAFF PORTAL VIEWS ---
# ==============================================================================

@login_required
def maintenance_dashboard(request):
    """
    The main control center for technicians. 
    Shows active work orders and a history of recent successes.
    """
    if request.user.role != 'maintenance':
        messages.error(request, "Access denied. Landlords should use the main Maintenance panel.")
        return redirect('dashboard')

    # 1. Active Tasks: Excludes 'Pending' (unassigned) and 'Completed'
    active_tasks = MaintenanceRequest.objects.filter(
        assigned_to=request.user,
        status__in=['assigned', 'in_progress']
    ).select_related('tenant__user', 'tenant__assigned_property').order_by('-priority', '-date_reported')

    # ⭐ NEW: Explicit count for the "Urgent Tasks" stat card
    urgent_count = active_tasks.filter(priority='high').count()

    # 2. History: Last 5 completed jobs
    history = MaintenanceRequest.objects.filter(
        assigned_to=request.user, 
        status='completed'
    ).order_by('-date_resolved')[:5]

    return render(request, 'maintenance/technician_dashboard.html', {
        'active_tasks': active_tasks,
        'urgent_count': urgent_count, # Matches the new dashboard template
        'history': history,
        'today': timezone.now() # For the portal clock
    })

@login_required
def update_task(request, pk):
    """
    Allows a technician to change status, categorize the issue, 
    input completion costs, and leave technical notes.
    """
    task = get_object_or_404(MaintenanceRequest, pk=pk, assigned_to=request.user)
    
    if request.method == 'POST':
        form = MaintenanceTaskUpdateForm(request.POST, instance=task)
        if form.is_valid():
            # 1. Save the task details
            task = form.save() 
            
            # 2. ⭐ THE FIX: Recalculate tenant balance if a tenant is attached
            # This ensures 'completed' tasks push their costs to the ledger instantly
            if task.tenant:
                task.tenant.update_balance()
            
            status_text = task.get_status_display()
            messages.success(request, f"Task #{task.id} updated to '{status_text}' and balance synced.")
            return redirect('maintenance_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = MaintenanceTaskUpdateForm(instance=task)
        
    return render(request, 'maintenance/update_task.html', {
        'form': form, 
        'task': task
    })

@login_required
def maintenance_work_history(request):
    if request.user.role != 'maintenance':
        return redirect('dashboard')

    query = request.GET.get('q')
    history = MaintenanceRequest.objects.filter(
        assigned_to=request.user,
        status='completed'
    ).select_related('tenant__assigned_property').order_by('-date_resolved')

    if query:
        history = history.filter(
            Q(issue__icontains=query) | 
            Q(tenant__assigned_property__name__icontains=query) |
            Q(tenant__unit_number__icontains=query)
        )

    return render(request, 'maintenance/work_history.html', {
        'history': history,
        'query': query
    })

# ==============================================================================
# --- 5. ADD DATA VIEWS ---
# ==============================================================================

@login_required(login_url='login')
def add_property(request):
    if request.method == 'POST':
        form = PropertyForm(request.POST)
        if form.is_valid():
            property_obj = form.save(commit=False)
            property_obj.landlord = request.user # Automated ownership
            property_obj.save()
            messages.success(request, 'Property added successfully')
            return redirect('properties')
    else:
        form = PropertyForm()
    return render(request, 'add_property.html', {'form': form})

@login_required(login_url='login')
def add_tenant(request):
    if request.method == 'POST':
        form = AddTenantFullForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            phone = form.cleaned_data['phone_number']
            first_name = form.cleaned_data['first_name']

            # Check if user already exists
            if CustomUser.objects.filter(email=email).exists():
                messages.error(request, "User with this email already exists")
                return render(request, 'add_tenant.html', {'form': form})

            # 1. Create the base User Account
            user = CustomUser.objects.create(
                username=email, 
                email=email,
                first_name=first_name,
                last_name=form.cleaned_data['last_name'],
                phone_number=phone,
                role='tenant',
                must_change_password=True 
            )

            # Set phone number as initial password
            clean_password = str(phone).replace(' ', '').replace('+', '').replace('-', '')
            user.set_password(clean_password)
            user.save()

            # 2. Create the Tenant Profile
            tenant = form.save(commit=False)
            tenant.user = user
            
            # ⭐ Optional Lease End Handling:
            # If the landlord leaves it blank in the form, it saves as None/Null
            tenant.lease_end = form.cleaned_data.get('lease_end')
            
            tenant.save()
            
            # ⭐ MASTER RECALCULATION:
            # Instead of manually setting balance = rent_amount, we trigger
            # the ledger to calculate the 'Opening Balance' for the first month.
            tenant.update_balance()
            
            messages.success(
                request, 
                f'Account created! {first_name} can now log in using their phone number as the password.'
            )
            return redirect('tenants')
    else:
        form = AddTenantFullForm()
        # Security: Only show this landlord's properties in the dropdown
        form.fields['assigned_property'].queryset = Property.objects.filter(landlord=request.user)
    
    return render(request, 'add_tenant.html', {'form': form})

@login_required(login_url='login')
def record_payment(request, pk=None):
    # Handle Edit Mode if a primary key is passed
    instance = get_object_or_404(Payment, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=instance)
        if form.is_valid():
            payment = form.save()
            
            # ⭐ MASTER RECALCULATION: 
            # This triggers the model logic to look at the tenant's entire 
            # history (Months Lived vs. Total Paid) to update the balance.
            payment.tenant.update_balance()
            
            # Dynamic feedback showing exactly what period was paid for
            month_name = payment.get_for_month_display()
            action = "updated" if instance else "recorded"
            
            messages.success(
                request, 
                f'Payment {action} for {payment.tenant.user.get_full_name()} '
                f'assigned to {month_name} {payment.for_year}.'
            )
            return redirect('payments')
    else:
        form = PaymentForm(instance=instance)
        
        # Security: Only show tenants belonging to THIS landlord's properties
        # Performance: select_related('user') avoids "N+1" queries when building the dropdown
        form.fields['tenant'].queryset = Tenant.objects.filter(
            assigned_property__landlord=request.user
        ).select_related('user')
        
    return render(request, 'record_payment.html', {
        'form': form,
        'edit_mode': bool(instance)
    })
@login_required(login_url='login')
def add_maintenance(request):
    if request.method == 'POST':
        form = MaintenanceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('maintenance')
    else:
        form = MaintenanceForm()
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=request.user)
    return render(request, 'add_maintenance.html', {'form': form, 'edit_mode': False})


# ==============================================================================
# --- 6. EDIT / DELETE VIEWS (With Ownership Validation) ---
# ==============================================================================

@login_required(login_url='login')
def edit_property(request, pk):
    property_obj = get_object_or_404(Property, pk=pk, landlord=request.user)
    if request.method == 'POST':
        form = PropertyForm(request.POST, instance=property_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Updated {property_obj.name} successfully')
            return redirect('properties')
    else:
        form = PropertyForm(instance=property_obj)
    return render(request, 'edit_property.html', {'form': form, 'property': property_obj})

@login_required(login_url='login')
def delete_property(request, pk):
    # Security: Ensure only the landlord who owns the property can delete it
    property_obj = get_object_or_404(Property, pk=pk, landlord=request.user)
    
    if request.method == 'POST':
        name = property_obj.name
        try:
            # Attempt to delete
            property_obj.delete()
            messages.success(request, f"Property {name} deleted successfully.")
            return redirect('properties')
        except ProtectedError:
            # ⭐ THE FIX: Catch the error if tenants are still assigned
            first_tenant = property_obj.tenant_set.first()
            tenant_name = first_tenant.user.get_full_name() if first_tenant else "active tenants"
            
            messages.error(request, 
                f"Cannot delete '{name}' because it still has active tenants (e.g., {tenant_name}). "
                "Please reassign or remove all tenants before deleting this property."
            )
            return redirect('properties')

    # Standard confirmation page
    return render(request, 'confirm_delete.html', {
        'obj': property_obj.name, 
        'type': 'property', 
        'back_url': reverse('properties')
    })

@login_required(login_url='login')
def edit_tenant(request, pk):
    # Security: Ensure the landlord only edits tenants belonging to their properties
    tenant = get_object_or_404(Tenant, pk=pk, assigned_property__landlord=request.user)
    user = tenant.user
    
    if request.method == 'POST':
        form = AddTenantFullForm(request.POST, instance=tenant)
        
        if form.is_valid():
            # 1. Update Core User Account Details
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.phone_number = form.cleaned_data['phone_number']
            user.save()
            
            # 2. Save the Tenant Profile 
            # commit=False allows us to double-check fields if needed
            tenant = form.save(commit=False)
            
            # ⭐ Optional Lease End Handling:
            # Explicitly capture it from the form to ensure 'blank' stays 'None'
            tenant.lease_end = form.cleaned_data.get('lease_end')
            
            tenant.save()
            
            # 3. ⭐ MASTER RECALCULATION:
            # If the landlord changed the monthly rent_amount, this method 
            # recalculates the lifetime balance based on the new rate.
            tenant.update_balance()
            
            messages.success(request, f"Tenant {user.get_full_name()} updated and monthly ledger synced!")
            return redirect('tenants')
    else:
        # Pre-fill form with existing identity data
        initial_data = {
            'first_name': user.first_name, 
            'last_name': user.last_name, 
            'email': user.email, 
            'phone_number': user.phone_number
        }
        form = AddTenantFullForm(instance=tenant, initial=initial_data)
        
        # Security: Only show this landlord's properties in the dropdown
        form.fields['assigned_property'].queryset = Property.objects.filter(landlord=request.user)
        
    return render(request, 'edit_tenant.html', {'form': form, 'tenant': tenant})

@login_required(login_url='login')
def delete_tenant(request, pk):
    # Security: Ensure the landlord can only delete their own tenants
    tenant = get_object_or_404(Tenant, pk=pk, assigned_property__landlord=request.user)
    user = tenant.user
    
    if request.method == 'POST':
        tenant_name = user.get_full_name()
        try:
            # This deletes the User AND the Tenant profile (due to OneToOne CASCADE)
            user.delete() 
            messages.success(request, f"Tenant {tenant_name} has been removed.")
            return redirect('tenants')
        except ProtectedError:
            # ⭐ THE SAFETY FIX: Prevents crash if tenant has protected payments/records
            messages.error(request, 
                f"Cannot delete {tenant_name} because they have linked financial or maintenance records. "
                "Try changing their status to 'Moved Out' instead of deleting."
            )
            return redirect('tenants')

    return render(request, 'confirm_delete.html', {
        'obj': user.get_full_name(), 
        'type': 'tenant and user account', 
        'back_url': reverse('tenants')
    })

@login_required(login_url='login')
def edit_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk, tenant__assigned_property__landlord=request.user)
    tenant = payment.tenant

    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            # 1. Save the payment changes (amount, status, etc.)
            form.save()
            
            # 2. RECALCULATE EVERYTHING
            # This ignores the old balance and finds the new truth
            tenant.update_balance()
            
            messages.success(request, f"Payment for {tenant.user.get_full_name()} updated and balance synced.")
            return redirect('payments')
    else:
        form = PaymentForm(instance=payment)
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=request.user)
    
    return render(request, 'record_payment.html', {'form': form, 'edit_mode': True, 'payment': payment})

@login_required(login_url='login')
@transaction.atomic
def delete_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk, tenant__assigned_property__landlord=request.user)
    tenant = payment.tenant
    
    if request.method == 'POST':
        # 1. Delete the record
        payment.delete()
        
        # 2. RECALCULATE EVERYTHING
        # Since the payment is gone, update_balance() will automatically 
        # add that amount back to what the tenant owes.
        tenant.update_balance()
        
        messages.success(request, "Payment deleted. Tenant balance adjusted automatically.")
        return redirect('payments')
        
    return render(request, 'confirm_delete.html', {
        'obj': f"Payment of KES {payment.amount}", 
        'type': 'payment record', 
        'back_url': reverse('payments')
    })
    

@login_required(login_url='login')
def edit_maintenance(request, pk):
    # Security: Ensure the landlord only edits requests for their own properties
    maintenance_req = get_object_or_404(MaintenanceRequest, pk=pk, tenant__assigned_property__landlord=request.user)
    
    if request.method == 'POST':
        form = MaintenanceForm(request.POST, instance=maintenance_req)
        if form.is_valid():
            # 1. Save the maintenance request details (status, cost, etc.)
            maintenance = form.save()
            
            # 2. ⭐ THE FIX: Explicitly tell the tenant to recalculate their balance
            # This ensures that if the cost changed or status became 'Completed', 
            # the tenant's ledger updates immediately.
            if maintenance.tenant:
                maintenance.tenant.update_balance()
            
            messages.success(request, f"Maintenance for {maintenance.tenant.user.get_full_name()} updated and billed.")
            return redirect('maintenance')
    else:
        form = MaintenanceForm(instance=maintenance_req)
        # Filter the tenant dropdown to only show this landlord's tenants
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=request.user)
        
    return render(request, 'add_maintenance.html', {'form': form, 'edit_mode': True})

@login_required(login_url='login')
@transaction.atomic
def delete_maintenance(request, pk):
    maintenance_req = get_object_or_404(MaintenanceRequest, pk=pk, tenant__assigned_property__landlord=request.user)
    
    if request.method == 'POST':
        # ⭐ THE FIX: Keep a reference to the tenant before deleting the task
        tenant = maintenance_req.tenant
        maintenance_req.delete()
        
        # ⭐ THE FIX: Re-heal the ledger balance
        if tenant:
            tenant.update_balance()
            
        messages.success(request, "Maintenance request deleted and balance updated.")
        return redirect('maintenance')
        
    return render(request, 'confirm_delete.html', {
        'obj': f"Request #MNT-{maintenance_req.id}", 
        'back_url': reverse('maintenance') 
    })

# ==============================================================================
# --- 7. WORKFLOWS, APPROVALS & ASSIGNMENTS ---
# ==============================================================================

@login_required(login_url='login')
@transaction.atomic
def approve_tenant_signup(request, tenant_id):
    if request.user.role != 'landlord':
        return redirect('tenant_dashboard')

    # Security: Ensure the tenant belongs to the landlord making the request
    tenant = get_object_or_404(
        Tenant, 
        id=tenant_id, 
        assigned_property__landlord=request.user
    )

    if request.method == 'POST':
        rent_raw = request.POST.get('rent_amount')
        lease_end = request.POST.get('lease_end')

        # 1. Financial Conversion
        try:
            rent_decimal = Decimal(rent_raw) if rent_raw else Decimal('0.00')
        except (InvalidOperation, TypeError):
            rent_decimal = Decimal('0.00')

        # 2. Update Tenancy Status
        tenant.status = 'active'
        tenant.rent_amount = rent_decimal
        
        # ⭐ Updated Lease Logic: 
        # Only set the date if it's provided; otherwise, ensure it remains None/Null
        if lease_end and lease_end.strip():
            tenant.lease_end = lease_end
        else:
            tenant.lease_end = None
        
        tenant.save()
        
        # ⭐ MASTER RECALCULATION:
        # Now that the status is active and rent is set, calculate the 
        # monthly opening balance for this specific billing period.
        tenant.update_balance() 
        
        messages.success(request, f"Account for {tenant.user.get_full_name()} is now active.")
        return redirect('tenants')

    return redirect('tenants')
@login_required(login_url='login')
@transaction.atomic
def reject_tenant_signup(request, tenant_id):
    if request.user.role != 'landlord':
        return redirect('tenant_dashboard')

    # Find the pending tenant linked to this landlord
    tenant = get_object_or_404(Tenant, id=tenant_id, status='pending', assigned_property__landlord=request.user)

    if request.method == 'POST':
        user_to_delete = tenant.user
        tenant.delete() # Remove the profile
        user_to_delete.delete() # Remove the user account
        
        messages.info(request, "Registration request has been rejected and the account removed.")
    
    return redirect('tenants')

@login_required
@transaction.atomic
def approve_move_out(request, tenant_id):
    # Security: Ensure only the landlord who owns the property can approve
    if request.user.role != 'landlord':
        return redirect('dashboard')
        
    tenant = get_object_or_404(
        Tenant, 
        id=tenant_id, 
        assigned_property__landlord=request.user
    )
    
    if request.method == 'POST':
        # ⭐ THE FIX: Force an instant ledger recalculation to get accurate numbers
        tenant.update_balance()
        
        # Block approval if they still owe money
        if tenant.balance > 0:
            messages.error(
                request, 
                f"Cannot approve move-out. {tenant.user.get_full_name()} "
                f"has an outstanding balance of KES {tenant.balance:,.2f}."
            )
            return redirect('tenants')
            
        # Formal Approval: Update status and set the timestamp
        tenant.status = 'approved'
        tenant.landlord_approved_at = timezone.now()
        
        # Sync the lease end with their intended departure
        if tenant.intended_move_out_date:
            tenant.lease_end = tenant.intended_move_out_date
            
        tenant.save()
        
        messages.success(request, f"Move-out notice for {tenant.user.get_full_name()} has been approved.")
        return redirect('tenants') # Go back to the management list

    # Fallback to safety if someone attempts a direct GET request
    return redirect('tenants')

@login_required
@user_passes_test(lambda u: getattr(u, 'role', None) == 'landlord')
def approve_payment(request, payment_id):
    """
    ⭐ UPDATED: Confirms payment and triggers the Monthly Ledger recalculation.
    """
    if request.method == 'POST':
        # Security: Only allow the landlord who owns the property to approve the payment
        payment = get_object_or_404(
            Payment, 
            id=payment_id, 
            tenant__assigned_property__landlord=request.user
        )
        
        if payment.status == 'pending':
            # 1. Finalize the Transaction
            payment.status = 'confirmed'
            payment.save()
            
            # 2. MASTER RECALCULATION
            # This triggers the model logic: (Months Lived * Rent) - (All Confirmed Payments).
            # If the tenant had arrears from January, this February payment will 
            # automatically reduce that old debt first.
            payment.tenant.update_balance()
            
            # Dynamic feedback including the month/year the payment was tagged for
            messages.success(
                request, 
                f"Payment for {payment.get_for_month_display()} {payment.for_year} confirmed. "
                f"Tenant balance updated automatically."
            )
        else:
            messages.warning(request, "This payment has already been processed.")
            
    return redirect('payments')

@login_required
def assign_maintenance(request, pk):
    # 1. Security Check
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
        
    task = get_object_or_404(MaintenanceRequest, pk=pk)
    
    if request.method == 'POST':
        #  Pass 'user' so the form can filter the technicians dropdown
        form = MaintenanceAssignmentForm(request.POST, instance=task, user=request.user)
        
        if form.is_valid():
            # Create the object but don't hit the DB yet
            assignment = form.save(commit=False)
            
            #  AUTOMATION: If a technician is selected, update status
            if assignment.assigned_to:
                assignment.status = 'assigned'
            
            # Save the main record
            assignment.save()
            # Save any many-to-many data if present (good habit!)
            form.save_m2m()
            
            messages.success(request, f"Task #{task.id} assigned to {assignment.assigned_to.get_full_name()}")
            
            # REDIRECT: Ensure 'maintenance' is the name in your urls.py
            return redirect('maintenance') 
        else:
            # This is where we caught the 'status required' error earlier
            print(f"Form Errors: {form.errors}") 
            messages.error(request, "Assignment failed. Please check the technician selection.")
    else:
        # GET request: Show the form with the landlord's staff only
        form = MaintenanceAssignmentForm(instance=task, user=request.user)
        
    return render(request, 'maintenance/assign_maintenance.html', {
        'form': form,
        'task': task
    })

@login_required
def manage_staff(request):
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    # FIXED: Show technicians who chose YOU as their landlord but aren't active yet
    pending_staff = CustomUser.objects.filter(
        role='maintenance', 
        is_active=False, 
        employer=request.user # Look for your specific applicants
    )

    #  Show technicians who are active and hired by YOU
    active_staff = CustomUser.objects.filter(
        role='maintenance', 
        is_active=True, 
        employer=request.user
    )

    return render(request, 'manage_staff.html', {
        'pending_staff': pending_staff,
        'active_staff': active_staff
    })

@login_required(login_url='login')
def add_staff(request):
    """
    Allows a landlord to manually onboard a trusted technician.
    Sets the phone number as the initial password.
    """
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = AddStaffForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            phone = form.cleaned_data['phone_number']

            # 1. Collision Check: Ensure email is unique
            if CustomUser.objects.filter(email=email).exists():
                messages.error(request, "A user with this email already exists.")
                return render(request, 'add_staff.html', {'form': form})

            # 2. Create the Technician User Account
            user = CustomUser.objects.create(
                username=email, # Using email as username for consistency
                email=email,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                phone_number=phone,
                role='maintenance',
                employer=request.user,      # ⭐ Links them to THIS landlord
                specialization=form.cleaned_data.get('specialization'),
                is_active=True,             # ⭐ Active immediately (Landlord approved)
                must_change_password=True    # ⭐ Forces change on first login
            )

            # 3. Security Logic: Clean phone number to create the temporary password
            clean_password = str(phone).replace(' ', '').replace('+', '').replace('-', '')
            user.set_password(clean_password)
            user.save()

            messages.success(
                request, 
                f"Staff account for {user.get_full_name()} created! "
                f"They can login using their phone number as the password."
            )
            return redirect('manage_staff')
    else:
        form = AddStaffForm()

    return render(request, 'add_staff.html', {'form': form})

@login_required
def remove_staff(request, pk):
    # Security: Ensure this staff belongs to this landlord
    staff = get_object_or_404(
        CustomUser, 
        pk=pk, 
        role='maintenance', 
        employer=request.user
    )
    
    if request.method == 'POST':
        # Logic: Unlink the technician
        staff_name = staff.get_full_name()
        staff.delete()
        
        messages.warning(request, f"{staff_name} has been removed.")
        return redirect('manage_staff')

    # GET Request: Show the confirm delete page
    return render(request, 'confirm_delete.html', {
        'obj': staff.get_full_name(),
        'type': 'technician from your active team',
        'back_url': reverse('manage_staff')
    })

@login_required
def approve_staff(request, pk):
    """Activates a pending staff member account."""
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    # Strictly allow only POST requests for data changes
    if request.method == 'POST':
        # Ensure you can only approve someone who actually applied to YOU
        staff = get_object_or_404(
            CustomUser, 
            pk=pk, 
            role='maintenance', 
            is_active=False, 
            employer=request.user
        )
        
        staff.is_active = True
        staff.save()
        
        messages.success(request, f"{staff.get_full_name()} has been activated and added to your team.")
    
    return redirect('manage_staff')

@login_required
def reject_staff(request, pk):
    """Deletes a pending staff application entirely."""
    if request.user.role != 'landlord':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    # Strictly allow only POST requests for data changes
    if request.method == 'POST':
        # Ensure you can only delete someone who applied to YOU
        staff = get_object_or_404(
            CustomUser, 
            pk=pk, 
            role='maintenance', 
            is_active=False, 
            employer=request.user
        )
        
        staff_name = staff.get_full_name()
        staff.delete() 
        
        messages.warning(request, f"Application for {staff_name} has been rejected and removed.")
        
    return redirect('manage_staff')


# ==============================================================================
# --- 8. EXPORTS (Isolated) ---
# ==============================================================================
# --- 1. PROPERTIES EXPORT ---
@login_required(login_url='login')
def export_properties_csv(request):
    query = request.GET.get('q', '')
    my_properties = Property.objects.filter(landlord=request.user)
    if query:
        my_properties = my_properties.filter(Q(name__icontains=query) | Q(location__icontains=query))

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="my_properties.csv"'
    writer = csv.writer(response)
    writer.writerow(['Property Name', 'Location', 'Units', 'Monthly Target Revenue'])
    for p in my_properties:
        writer.writerow([p.name, p.location, p.total_units, f"{p.monthly_revenue:.0f}"])
    return response

# --- 2. FULL TENANT LIST EXPORT ---
@login_required(login_url='login')
def export_tenants_csv(request):
    search_query = request.GET.get('q', '')
    property_filter = request.GET.get('property_id', 'all')
    tenants = Tenant.objects.filter(assigned_property__landlord=request.user).select_related('user', 'assigned_property')

    if property_filter != 'all':
        tenants = tenants.filter(assigned_property_id=property_filter)
    if search_query:
        tenants = tenants.filter(Q(user__first_name__icontains=search_query) | Q(user__last_name__icontains=search_query) | Q(unit_number__icontains=search_query))

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tenant_directory.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Property', 'Unit', 'Phone', 'Balance', 'Status'])
    for t in tenants:
        status = "Arrears" if t.balance > 0 else "Credit" if t.balance < 0 else "Settled"
        writer.writerow([t.user.get_full_name(), t.assigned_property.name, t.unit_number, f"'{t.user.phone_number}", abs(t.balance), status])
    return response

# --- 3. REVENUE REPORT EXPORT (Date Filtered) ---
@login_required(login_url='login')
def export_revenue_csv(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Defaults for filenames/filtering
    if not start_date or not end_date:
        today = timezone.now().date()
        start_date, end_date = today.replace(day=1), today

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="revenue_{start_date}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Property', 'Monthly Target', 'Collected (In Period)', 'Shortfall', 'Occupancy %'])
    
    for p in Property.objects.filter(landlord=request.user):
        collected = Payment.objects.filter(
            tenant__assigned_property=p, status='confirmed', date__date__range=[start_date, end_date]
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        tenant_count = p.tenant_set.count()
        occ = (tenant_count / p.total_units * 100) if p.total_units > 0 else 0
        writer.writerow([p.name, p.monthly_revenue, collected, p.monthly_revenue - collected, f"{occ:.1f}%"])
    return response

# --- 4. ARREARS (DEBTORS) EXPORT ---
@login_required(login_url='login')
def export_arrears_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="arrears_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tenant', 'Property', 'Unit', 'Phone', 'Balance Due'])
    for t in Tenant.objects.filter(assigned_property__landlord=request.user, balance__gt=0):
        writer.writerow([t.user.get_full_name(), t.assigned_property.name, t.unit_number, f"'{t.user.phone_number}", t.balance])
    return response

# --- 5. PAYMENTS & LEDGER EXPORT ---
@login_required(login_url='login')
def export_payments_csv(request):
    status_filter = request.GET.get('status', 'all')
    billing_month = request.GET.get('billing_month')
    payments = Payment.objects.filter(tenant__assigned_property__landlord=request.user).order_by('-date')

    if status_filter != 'all': payments = payments.filter(status=status_filter)
    if billing_month: payments = payments.filter(for_month=billing_month)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payment_ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(['Reference', 'Tenant', 'Property', 'Amount', 'Billing Month', 'Status', 'Date Paid'])
    for p in payments:
        writer.writerow([p.transaction_id, p.tenant.user.get_full_name(), p.tenant.assigned_property.name, p.amount, p.get_for_month_display(), p.status, p.date.strftime("%Y-%m-%d")])
    return response

# --- 6. MAINTENANCE REQUESTS EXPORT ---
@login_required(login_url='login')
def export_maintenance_csv(request):
    status_filter = request.GET.get('status', 'all')
    maint = MaintenanceRequest.objects.filter(tenant__assigned_property__landlord=request.user)
    if status_filter != 'all': maint = maint.filter(status=status_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="maintenance_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Tenant', 'Property', 'Issue', 'Priority', 'Status', 'Reported On'])
    for req in maint:
        writer.writerow([f"#MNT-{req.id}", req.tenant.user.get_full_name(), req.tenant.assigned_property.name, req.issue, req.priority, req.status, req.date_reported.strftime("%Y-%m-%d")])
    return response
    
# ==============================================================================
# --- 9. EXTRA UTILITIES & NOTIFICATIONS ---
# ==============================================================================

@login_required(login_url='login')
def send_mass_message(request):
    if request.method == 'POST':
        group = request.POST.get('recipient_group')
        subject = request.POST.get('subject')
        content = request.POST.get('message_content')
        methods = request.POST.getlist('delivery_method')

        tenants = Tenant.objects.filter(assigned_property__landlord=request.user)
        
        if group == 'overdue':
            tenants = tenants.filter(balance__gt=0)
        elif group == 'specific':
            tenant_id = request.POST.get('specific_tenant_id')
            tenants = tenants.filter(id=tenant_id)

        # Track successful deliveries for reliable dashboard feedback
        email_count = 0
        sms_count = 0

        for tenant in tenants:
            # Personalize the message content per tenant
            personalized_msg = content.replace("{tenant_name}", tenant.user.get_full_name())
            
            # ✉️ 1. ACTUAL EMAIL INTEGRATION
            if 'email' in methods and tenant.user.email:
                try:
                    send_mail(
                        subject=subject,
                        message=personalized_msg,
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@rhms.co.ke'),
                        recipient_list=[tenant.user.email],
                        fail_silently=False,  # Set to False inside the try block to catch exceptions
                    )
                    email_count += 1
                except Exception as e:
                    # Log the specific error to console but continue the loop for other tenants
                    print(f"ERROR: Failed to send email to {tenant.user.email}. Details: {e}")

            # 📱 2. ACTUAL SMS STRUCTURE
            if 'sms' in methods and tenant.user.phone_number:
                # When you hook up Africa's Talking or Twilio later, place your SDK code right here!
                # example: africastalking.SMS.send(personalized_msg, [tenant.user.phone_number])
                print(f"PRODUCTION SMS BOUND -> To: {tenant.user.phone_number} | Msg: {personalized_msg}")
                sms_count += 1

        # Calculate absolute deliveries
        total_delivered = max(email_count, sms_count) if len(methods) > 1 else (email_count + sms_count)

        # Save record log to tracking ledger
        SentMessage.objects.create(
            subject=subject, 
            content=content, 
            recipient_count=total_delivered, 
            delivery_method=", ".join(methods), 
            sender=request.user
        )
        
        messages.success(
            request, 
            f"Mass notification processed! Delivered {email_count} emails and staged {sms_count} SMS alerts."
        )
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    return redirect('dashboard')

@login_required(login_url='login')
def property_detail(request, pk):
    property_obj = get_object_or_404(Property, pk=pk, landlord=request.user)
    tenants = Tenant.objects.filter(assigned_property=property_obj).select_related('user')
    return render(request, 'property_detail.html', {'property': property_obj, 'tenants': tenants})

@login_required(login_url='login')
def import_properties(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        try:
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            
            if not reader.fieldnames:
                messages.error(request, "The CSV file is empty or has no headers.")
                return redirect('import_properties')
            
            # ⭐ THE FIX (PART 1): Normalize headers by lowering AND replacing spaces with underscores
            # This cleanly handles variations: "Property Name" -> "property_name", "Total Units" -> "total_units"
            reader.fieldnames = [field.strip().lower().replace(" ", "_") for field in reader.fieldnames if field]
            
            count = 0
            skipped_count = 0
            
            for row in reader:
                # Fallback checks just in case the landlord used "name" vs "property_name"
                name = row.get('name') or row.get('property_name')
                
                # ⭐ THE FIX (PART 2): Protect against Null Constraint crashes
                # If a row has an empty name, skip it instead of crashing the ENTIRE import file.
                if not name or not name.strip():
                    skipped_count += 1
                    continue
                
                # ⭐ THE FIX (PART 3): Safe Numeric Conversions
                # If a cell is blank (""), casting directly to int() or float() would throw a ValueError.
                raw_units = row.get('total_units')
                total_units = int(raw_units) if raw_units and str(raw_units).isdigit() else 0
                
                raw_revenue = row.get('monthly_revenue')
                try:
                    monthly_revenue = float(raw_revenue) if raw_revenue else 0.00
                except ValueError:
                    monthly_revenue = 0.00

                # Data is completely clean now; safe to create record
                Property.objects.create(
                    landlord=request.user,
                    name=name.strip(),
                    location=row.get('location') or 'Not Specified',
                    total_units=total_units,
                    monthly_revenue=monthly_revenue,
                    description=row.get('description', '')
                )
                count += 1
                
            success_msg = f"Successfully imported {count} properties."
            if skipped_count > 0:
                success_msg += f" ({skipped_count} rows skipped due to missing name headers)."
                
            messages.success(request, success_msg)
            return redirect('properties')
            
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")
            return redirect('import_properties')
            
    return render(request, 'import_properties.html')


@login_required(login_url='login')
def generate_invoice(request, pk):
    # ⭐ THE SECURITY FIX:
    # Allow access if:
    # 1. The user is the Landlord of the property linked to this payment
    # OR 
    # 2. The user is the Tenant linked to this payment
    payment = get_object_or_404(
        Payment, 
        Q(tenant__assigned_property__landlord=request.user) | Q(tenant__user=request.user),
        pk=pk
    )
    
    tenant = payment.tenant
    start_date = tenant.move_in_date
    today = timezone.now().date()
    
    # 2. Calculate Lifetime Rent Accrued
    # Sum the actual rent charges created for this tenant to match the database ledger
    total_rent_data = tenant.rent_charges.aggregate(total=Sum('amount'))['total'] or 0
    total_rent_due = Decimal(str(total_rent_data))

    # 3. Calculate Lifetime Maintenance Charges
    # Sum only 'Completed' (or 'completed') repair costs
    total_maint_due = tenant.maintenancerequest_set.filter(
        status__iexact='completed'  # __iexact handles both 'Completed' and 'completed'
    ).aggregate(total=Sum('cost'))['total'] or 0
    
    # 4. Calculate Lifetime Payments Made
    total_paid = tenant.payment_set.filter(
        status='confirmed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # 5. Build Context
    context = {
        'payment': payment,
        'tenant': tenant,
        'property': tenant.assigned_property,
        'total_rent_due': total_rent_due,
        'total_maint_due': Decimal(str(total_maint_due)),
        'total_paid': Decimal(str(total_paid)),
        'is_credit': tenant.balance < 0,
        'display_balance': abs(tenant.balance),
        'today': timezone.now(),
    }
    
    return render(request, 'invoice.html', context)
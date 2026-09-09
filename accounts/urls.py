from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # ==========================================================================
    # --- 1. CORE AUTHENTICATION & DASHBOARD ---
    # ==========================================================================
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('settings/', views.settings_view, name='settings'),
    path('profile/settings/', views.profile_settings, name='profile_settings'),
    path('change-password/', views.change_password, name='change_password'),
    #Password Reset
    # 1. Page to submit email
    path('reset_password/', auth_views.PasswordResetView.as_view(
        template_name="password_reset.html",
        email_template_name="password_reset_email.txt"
    ), name="reset_password"),

    # 2. Success message after submitting email
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(
        template_name="password_reset_sent.html"
    ), name="password_reset_done"),

    # 3. The actual link sent to the email
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name="password_reset_form.html"
    ), name="password_reset_confirm"),

    # 4. Final success message
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name="password_reset_done.html"
    ), name="password_reset_complete"),
    
    
    # ==========================================================================
    # --- 2. PROPERTY MANAGEMENT ---
    # ==========================================================================
    path('properties/', views.properties_view, name='properties'),
    path('properties/add/', views.add_property, name='add_property'),
    path('properties/<int:pk>/', views.property_detail, name='property_detail'),
    path('properties/edit/<int:pk>/', views.edit_property, name='edit_property'),
    path('properties/delete/<int:pk>/', views.delete_property, name='delete_property'),
    path('properties/import/', views.import_properties, name='import_properties'),
    path('properties/export/', views.export_properties_csv, name='export_properties_csv'),

    # ==========================================================================
    # --- 3. TENANT MANAGEMENT & DIRECTORY ---
    # ==========================================================================
    path('tenants/', views.tenants_view, name='tenants'),
    path('tenants/add/', views.add_tenant, name='add_tenant'),
    path('tenants/edit/<int:pk>/', views.edit_tenant, name='edit_tenant'),
    path('tenants/delete/<int:pk>/', views.delete_tenant, name='delete_tenant'),
    path('tenants/export/', views.export_tenants_csv, name='export_tenants_csv'),

    # ==========================================================================
    # --- 4. PAYMENTS & REVENUE ---
    # ==========================================================================
    path('payments/', views.payments_view, name='payments'),
    path('payments/record/', views.record_payment, name='record_payment'),
    path('payments/edit/<int:pk>/', views.edit_payment, name='edit_payment'),
    path('payments/delete/<int:pk>/', views.delete_payment, name='delete_payment'),
    path('payments/export/', views.export_payments_csv, name='export_payments_csv'),    
    path('payments/invoice/<int:pk>/', views.generate_invoice, name='generate_invoice'),

    # ==========================================================================
    # --- 5. MAINTENANCE (LANDLORD VIEW) ---
    # ==========================================================================
    path('maintenance/', views.maintenance_view, name='maintenance'),
    path('maintenance/add/', views.add_maintenance, name='add_maintenance'),
    path('maintenance/edit/<int:pk>/', views.edit_maintenance, name='edit_maintenance'),
    path('maintenance/delete/<int:pk>/', views.delete_maintenance, name='delete_maintenance'),
    path('maintenance/export/', views.export_maintenance_csv, name='export_maintenance_csv'),

    # ==========================================================================
    # --- 6. TENANT PORTAL ---
    # ==========================================================================
    path('tenant/dashboard/', views.tenant_dashboard, name='tenant_dashboard'),
    path('tenant/report-issue/', views.report_issue, name='report_issue'),
    path('tenant/report-payment/', views.report_payment, name='report_payment'),
    path('tenant/payments/history/', views.payment_history, name='payment_history'),
    path('tenant/repairs/history/', views.maintenance_history, name='maintenance_history'),
    path('tenant/announcements/', views.all_announcements, name='all_announcements'),

    # ==========================================================================
    # --- 7. MAINTENANCE STAFF PORTAL ---
    # ==========================================================================
    path('maintenance/dashboard/', views.maintenance_dashboard, name='maintenance_dashboard'),
    path('maintenance/task/<int:pk>/update/', views.update_task, name='update_task'),
    path('maintenance/history/', views.maintenance_work_history, name='maintenance_work_history'),

    # ==========================================================================
    # --- 8. WORKFLOWS & APPROVALS (LOGIC PATHS) ---
    # ==========================================================================
    # Staff Approvals
    path('maintenance/staff/', views.manage_staff, name='manage_staff'),
    path('maintenance/staff/add/', views.add_staff, name='add_staff'),
    path('maintenance/staff/remove/<int:pk>/', views.remove_staff, name='remove_staff'),
    path('maintenance/staff/approve/<int:pk>/', views.approve_staff, name='approve_staff'),
    path('maintenance/staff/reject/<int:pk>/', views.reject_staff, name='reject_staff'),
    
    # Tenant & Move-Out Approvals
    path('tenants/approve-signup/<int:tenant_id>/', views.approve_tenant_signup, name='approve_tenant_signup'),
    path('tenants/reject-signup/<int:tenant_id>/', views.reject_tenant_signup, name='reject_tenant_signup'),
    path('tenants/approve-move-out/<int:tenant_id>/', views.approve_move_out, name='approve_move_out'),
    
    # Task & Payment Assignments
    path('maintenance/task/<int:pk>/assign/', views.assign_maintenance, name='assign_maintenance'),
    path('payments/approve/<int:payment_id>/', views.approve_payment, name='approve_payment'),

    # ==========================================================================
    # --- 9. REPORTS & COMMUNICATIONS ---
    # ==========================================================================
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/revenue/', views.export_revenue_csv, name='export_revenue_csv'),
    path('reports/export/arrears/', views.export_arrears_csv, name='export_arrears_csv'),
    path('send-mass-message/', views.send_mass_message, name='send_mass_message'),

    # ==========================================================================
    # --- 10. AI FEATURES ---
    # ==========================================================================
    path('ai/draft-announcement/', views.ai_draft_announcement, name='ai_draft_announcement'),
    path('ai/classify-maintenance/', views.ai_classify_maintenance, name='ai_classify_maintenance'),
    path('ai/tenant-chat/', views.ai_tenant_chat, name='ai_tenant_chat'),
    path('ai/dashboard-insights/', views.ai_dashboard_insights, name='ai_dashboard_insights'),
]
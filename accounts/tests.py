from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import datetime
from accounts.models import Property, Tenant, Payment, Announcement
from accounts.forms import PaymentForm

User = get_user_model()

class RHMSBugFixesTests(TestCase):
    def setUp(self):
        # Create Landlord
        self.landlord = User.objects.create_user(
            username='landlord@test.com',
            email='landlord@test.com',
            password='password123',
            role='landlord',
            is_approved=True
        )
        # Create Property
        self.property = Property.objects.create(
            landlord=self.landlord,
            name='Test Mansion',
            location='Nairobi',
            total_units=10,
            monthly_revenue=150000.00
        )
        # Create Tenant User
        self.tenant_user = User.objects.create_user(
            username='tenant@test.com',
            email='tenant@test.com',
            password='password123',
            role='tenant'
        )
        # Create Tenant Profile
        self.tenant = Tenant.objects.create(
            user=self.tenant_user,
            assigned_property=self.property,
            unit_number='A1',
            rent_amount=Decimal('15000.00'),
            move_in_date=datetime.date(2026, 6, 1),
            status='active'
        )

    def test_clean_transaction_id_handles_falsy_value(self):
        # Test that blank transaction ID on Cash payment is cleaned to None to prevent unique constraint crashes
        form_data = {
            'tenant': self.tenant.id,
            'amount': 15000.00,
            'for_month': 6,
            'for_year': 2026,
            'transaction_id': '',
            'method': 'Cash',
            'status': 'confirmed'
        }
        form = PaymentForm(data=form_data)
        # Filter querysets normally done in view
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=self.landlord)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['transaction_id'])
        
        # Save first Cash payment
        payment1 = form.save()
        
        # Save second Cash payment with empty transaction_id (should also clean to None and not clash)
        form2 = PaymentForm(data=form_data)
        form2.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=self.landlord)
        self.assertTrue(form2.is_valid(), form2.errors)
        self.assertIsNone(form2.cleaned_data['transaction_id'])
        payment2 = form2.save()
        
        # Verify both payments saved successfully and both have null transaction_id in DB
        self.assertIsNone(payment1.transaction_id)
        self.assertIsNone(payment2.transaction_id)

    def test_mpesa_requires_transaction_id(self):
        # M-Pesa payments must include a Transaction ID
        form_data = {
            'tenant': self.tenant.id,
            'amount': 15000.00,
            'for_month': 6,
            'for_year': 2026,
            'transaction_id': '',
            'method': 'M-Pesa',
            'status': 'pending'
        }
        form = PaymentForm(data=form_data)
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=self.landlord)
        self.assertFalse(form.is_valid())
        self.assertIn('transaction_id', form.errors)

    def test_duplicate_transaction_id_validation(self):
        # Save a confirmed payment first
        Payment.objects.create(
            tenant=self.tenant,
            amount=Decimal('15000.00'),
            transaction_id='TX123456',
            method='M-Pesa',
            status='confirmed',
            for_month=6,
            for_year=2026
        )
        
        # Attempt to save another payment with same transaction_id
        form_data = {
            'tenant': self.tenant.id,
            'amount': 15000.00,
            'for_month': 6,
            'for_year': 2026,
            'transaction_id': 'TX123456',
            'method': 'M-Pesa',
            'status': 'confirmed'
        }
        form = PaymentForm(data=form_data)
        form.fields['tenant'].queryset = Tenant.objects.filter(assigned_property__landlord=self.landlord)
        self.assertFalse(form.is_valid())
        self.assertIn('transaction_id', form.errors)

    def test_announcement_broadcast_setting(self):
        # Creating an announcement with no target property should auto-set is_broadcast to True
        announcement = Announcement.objects.create(
            title='General Outage',
            content='Water will be cut off tomorrow.',
            author=self.landlord,
            target_property=None
        )
        self.assertTrue(announcement.is_broadcast)

        # Creating an announcement with a target property should auto-set is_broadcast to False
        announcement_targeted = Announcement.objects.create(
            title='Elevator Repair',
            content='Elevator in B building is out of order.',
            author=self.landlord,
            target_property=self.property
        )
        self.assertFalse(announcement_targeted.is_broadcast)

    def test_tenant_signup_requires_property_and_unit(self):
        # Post to login_view with signup data but no property or unit
        from django.urls import reverse
        signup_data = {
            'signup_submit': 'true',
            'role_selection': 'tenant',
            'first_name': 'New',
            'last_name': 'Tenant',
            'username': 'newtenant',
            'email': 'newtenant@test.com',
            'password1': 'pass123',
            'password2': 'pass123',
        }
        response = self.client.post(reverse('login'), signup_data)
        # Should not create a tenant, should return 200 with error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newtenant').exists())

    def test_generate_invoice_calculates_prorated_rent_correctly(self):
        from django.urls import reverse
        # Create a tenant moving in on June 10, 2026 (partial month)
        prorated_user = User.objects.create_user(
            username='prorated@test.com',
            email='prorated@test.com',
            password='password123',
            role='tenant'
        )
        prorated_tenant = Tenant.objects.create(
            user=prorated_user,
            assigned_property=self.property,
            unit_number='A2',
            rent_amount=Decimal('10000.00'),
            move_in_date=datetime.date(2026, 6, 10),
            status='active'
        )
        # Verify the initial rent charge in database is 7000
        self.assertEqual(prorated_tenant.rent_charges.count(), 1)
        charge = prorated_tenant.rent_charges.first()
        self.assertEqual(charge.amount, Decimal('7000.00'))

        # Create a payment record
        payment = Payment.objects.create(
            tenant=prorated_tenant,
            amount=Decimal('7000.00'),
            method='M-Pesa',
            status='confirmed',
            for_month=6,
            for_year=2026,
            transaction_id='TXPRORATED1'
        )

        # Log in as the landlord
        self.client.force_login(self.landlord)

        # Request invoice
        response = self.client.get(reverse('generate_invoice', kwargs={'pk': payment.pk}))
        self.assertEqual(response.status_code, 200)
        
        # Verify that total_rent_due in context is 7000 instead of 10000
        self.assertEqual(response.context['total_rent_due'], Decimal('7000.00'))

    def test_maintenance_signup_success(self):
        from django.urls import reverse
        signup_data = {
            'signup_submit': 'true',
            'role_selection': 'maintenance',
            'first_name': 'Tech',
            'last_name': 'Staff',
            'username': 'techstaff',
            'email': 'tech@test.com',
            'phone_number': '0711111111',
            'specialization': 'Plumbing',
            'target_landlord': self.landlord.id,
            'password1': 'pass123',
            'password2': 'pass123',
        }
        response = self.client.post(reverse('login'), signup_data)
        # Should redirect to login on successful signup
        self.assertEqual(response.status_code, 302)
        
        # Verify user is created with correct role and is inactive awaiting landlord approval
        new_user = User.objects.get(username='techstaff')
        self.assertEqual(new_user.role, 'maintenance')
        self.assertFalse(new_user.is_active)
        self.assertEqual(new_user.specialization, 'Plumbing')
        self.assertEqual(new_user.employer, self.landlord)

    def test_landlord_signup_success(self):
        from django.urls import reverse
        signup_data = {
            'signup_submit': 'true',
            'role_selection': 'landlord',
            'first_name': 'New',
            'last_name': 'Landlord',
            'username': 'newlandlord',
            'email': 'newlandlord@test.com',
            'phone_number': '0722222222',
            'password1': 'pass123',
            'password2': 'pass123',
        }
        response = self.client.post(reverse('login'), signup_data)
        # Should redirect to login (pending admin approval — no longer auto-logged in)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

        # Verify user is created with correct role, is active, but not yet approved
        new_user = User.objects.get(username='newlandlord')
        self.assertEqual(new_user.role, 'landlord')
        self.assertTrue(new_user.is_active)
        self.assertFalse(new_user.is_approved)

    def test_password_reset_email_template(self):
        from django.urls import reverse
        from django.core import mail
        
        # Post request to send reset email
        response = self.client.post(reverse('reset_password'), {'email': 'tenant@test.com'})
        self.assertEqual(response.status_code, 302)
        
        # Check that one email has been sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        
        # Verify custom content is in the email body
        self.assertIn("You are receiving this email because you requested a password reset", email.body)
        self.assertIn("Your username is: tenant@test.com", email.body)
        
        # Ensure no smart apostrophe Unicode characters (e.g. ’) exist in the email body
        self.assertNotIn("'", email.body)
        self.assertNotIn("you've", email.body)
        self.assertNotIn("You're", email.body)


# ==============================================================================
# --- 2. VIEWS, WORKFLOWS & LOGIC TESTS ---
# ==============================================================================

from django.urls import reverse
from accounts.models import MaintenanceRequest, RentCharge


class RHMSViewAndLogicTests(TestCase):
    """
    Covers: login flows, role guards, balance engine, payment approval,
    move-out workflow, staff management, property CRUD, and management commands.
    """

    def setUp(self):
        # --- Landlord ---
        self.landlord = User.objects.create_user(
            username='landlord@rhms.com',
            email='landlord@rhms.com',
            password='securepass99',
            role='landlord',
            is_approved=True
        )
        # --- Property ---
        self.prop = Property.objects.create(
            landlord=self.landlord,
            name='Sunrise Apartments',
            location='Karen, Nairobi',
            total_units=5,
            monthly_revenue=75000
        )
        # --- Active Tenant ---
        self.tenant_user = User.objects.create_user(
            username='jane@rhms.com',
            email='jane@rhms.com',
            password='tenantpass99',
            role='tenant'
        )
        self.tenant = Tenant.objects.create(
            user=self.tenant_user,
            assigned_property=self.prop,
            unit_number='B2',
            rent_amount=Decimal('15000.00'),
            move_in_date=datetime.date(2026, 1, 1),
            status='active'
        )
        # --- Maintenance Staff ---
        self.tech_user = User.objects.create_user(
            username='bob@rhms.com',
            email='bob@rhms.com',
            password='techpass99',
            role='maintenance',
            employer=self.landlord,
            is_active=True
        )

    # ==========================================================================
    # LOGIN FLOW
    # ==========================================================================

    def test_login_with_email_redirects_to_dashboard(self):
        """Landlord can log in using their email address, not just username."""
        response = self.client.post(reverse('login'), {
            'username': 'landlord@rhms.com',
            'password': 'securepass99',
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_with_wrong_password_shows_error(self):
        """Wrong password returns 200 and shows an error message."""
        response = self.client.post(reverse('login'), {
            'username': 'landlord@rhms.com',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context['messages'])
        self.assertTrue(any('Incorrect password' in str(m) for m in messages_list))

    def test_pending_tenant_blocked_from_login(self):
        """A tenant with status='pending' is redirected back to login."""
        pending_user = User.objects.create_user(
            username='pending@rhms.com', email='pending@rhms.com',
            password='pass123', role='tenant'
        )
        Tenant.objects.create(
            user=pending_user, assigned_property=self.prop,
            unit_number='C1', rent_amount=Decimal('10000'),
            move_in_date=datetime.date(2026, 6, 1), status='pending'
        )
        response = self.client.post(reverse('login'), {
            'username': 'pending@rhms.com', 'password': 'pass123'
        })
        self.assertRedirects(response, reverse('login'))

    def test_inactive_maintenance_staff_blocked_from_login(self):
        """Maintenance staff with is_active=False cannot log in."""
        User.objects.create_user(
            username='inactive@rhms.com', email='inactive@rhms.com',
            password='pass123', role='maintenance', is_active=False
        )
        response = self.client.post(reverse('login'), {
            'username': 'inactive@rhms.com', 'password': 'pass123'
        })
        self.assertRedirects(response, reverse('login'))

    # ==========================================================================
    # ROLE-BASED ACCESS CONTROL
    # ==========================================================================

    def test_tenant_cannot_access_landlord_dashboard(self):
        """A logged-in tenant hitting /dashboard/ is redirected to tenant dashboard."""
        self.client.force_login(self.tenant_user)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('tenant_dashboard'))

    def test_unauthenticated_user_redirected_from_dashboard(self):
        """An unauthenticated user hitting /dashboard/ is sent to login."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_tenant_cannot_access_maintenance_view(self):
        """A tenant hitting the landlord maintenance page is denied and redirected."""
        self.client.force_login(self.tenant_user)
        response = self.client.get(reverse('maintenance'))
        self.assertEqual(response.status_code, 302)

    def test_maintenance_staff_redirected_from_landlord_dashboard(self):
        """Maintenance staff hitting /dashboard/ are redirected to maintenance_dashboard."""
        self.client.force_login(self.tech_user)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('maintenance_dashboard'))

    # ==========================================================================
    # BALANCE ENGINE
    # ==========================================================================

    def test_update_balance_reflects_confirmed_payments(self):
        """Confirming a payment reduces the tenant's outstanding balance."""
        initial_balance = self.tenant.balance

        Payment.objects.create(
            tenant=self.tenant,
            amount=Decimal('15000.00'),
            method='M-Pesa',
            status='confirmed',
            for_month=1,
            for_year=2026,
            transaction_id='TXBALTEST01'
        )
        self.tenant.update_balance()
        self.tenant.refresh_from_db()

        self.assertLess(self.tenant.balance, initial_balance)

    def test_update_balance_ignores_pending_payments(self):
        """A pending payment does NOT reduce the tenant's balance."""
        self.tenant.update_balance()
        self.tenant.refresh_from_db()
        balance_before = self.tenant.balance

        Payment.objects.create(
            tenant=self.tenant,
            amount=Decimal('15000.00'),
            method='M-Pesa',
            status='pending',
            for_month=2,
            for_year=2026,
            transaction_id='TXPENDING01'
        )
        self.tenant.update_balance()
        self.tenant.refresh_from_db()

        self.assertEqual(self.tenant.balance, balance_before)

    # ==========================================================================
    # PAYMENT APPROVAL WORKFLOW
    # ==========================================================================

    def test_approve_payment_confirms_and_redirects(self):
        """Landlord approving a pending payment flips its status to 'confirmed'."""
        payment = Payment.objects.create(
            tenant=self.tenant,
            amount=Decimal('15000.00'),
            method='Cash',
            status='pending',
            for_month=3,
            for_year=2026,
        )
        self.client.force_login(self.landlord)
        response = self.client.post(
            reverse('approve_payment', kwargs={'payment_id': payment.pk})
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'confirmed')
        self.assertRedirects(response, reverse('payments'))

    def test_cannot_approve_payment_belonging_to_other_landlord(self):
        """A landlord cannot approve a payment tied to another landlord's tenant."""
        other_landlord = User.objects.create_user(
            username='other@rhms.com', email='other@rhms.com',
            password='pass123', role='landlord', is_approved=True
        )
        payment = Payment.objects.create(
            tenant=self.tenant, amount=Decimal('5000'),
            method='Cash', status='pending', for_month=4, for_year=2026
        )
        self.client.force_login(other_landlord)
        response = self.client.post(
            reverse('approve_payment', kwargs={'payment_id': payment.pk})
        )
        self.assertEqual(response.status_code, 404)

    # ==========================================================================
    # MOVE-OUT WORKFLOW
    # ==========================================================================

    def test_tenant_can_submit_move_out_notice(self):
        """Tenant submitting a move-out notice sets status to 'notice_given'."""
        self.client.force_login(self.tenant_user)
        future_date = (datetime.date.today() + datetime.timedelta(days=31)).isoformat()
        response = self.client.post(reverse('tenant_dashboard'), {
            'submit_move_out': '1',
            'intended_move_out_date': future_date,
            'move_out_reason': 'Relocating for work.',
        })
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'notice_given')
        self.assertRedirects(response, reverse('tenant_dashboard'))

    def test_tenant_can_cancel_move_out_notice(self):
        """Tenant cancelling a move-out notice resets status back to 'active'."""
        self.tenant.status = 'notice_given'
        self.tenant.intended_move_out_date = datetime.date.today() + datetime.timedelta(days=31)
        self.tenant.save(update_fields=['status', 'intended_move_out_date'])

        self.client.force_login(self.tenant_user)
        self.client.post(reverse('tenant_dashboard'), {'cancel_move_out': '1'})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'active')
        self.assertIsNone(self.tenant.intended_move_out_date)

    # ==========================================================================
    # STAFF MANAGEMENT
    # ==========================================================================

    def test_landlord_can_approve_pending_staff(self):
        """Approving a pending staff member sets is_active=True."""
        pending_tech = User.objects.create_user(
            username='pending_tech@rhms.com', email='pending_tech@rhms.com',
            password='pass123', role='maintenance',
            employer=self.landlord, is_active=False
        )
        self.client.force_login(self.landlord)
        response = self.client.post(
            reverse('approve_staff', kwargs={'pk': pending_tech.pk})
        )
        pending_tech.refresh_from_db()
        self.assertTrue(pending_tech.is_active)
        self.assertRedirects(response, reverse('manage_staff'))

    def test_landlord_can_reject_pending_staff(self):
        """Rejecting a pending staff application deletes the account entirely."""
        pending_tech = User.objects.create_user(
            username='reject_tech@rhms.com', email='reject_tech@rhms.com',
            password='pass123', role='maintenance',
            employer=self.landlord, is_active=False
        )
        tech_pk = pending_tech.pk
        self.client.force_login(self.landlord)
        self.client.post(reverse('reject_staff', kwargs={'pk': tech_pk}))
        self.assertFalse(User.objects.filter(pk=tech_pk).exists())

    # ==========================================================================
    # PROPERTY CRUD
    # ==========================================================================

    def test_landlord_can_add_property(self):
        """POSTing valid property data creates a new Property owned by the landlord."""
        self.client.force_login(self.landlord)
        count_before = Property.objects.filter(landlord=self.landlord).count()
        response = self.client.post(reverse('add_property'), {
            'name': 'New Block D',
            'location': 'Westlands',
            'total_units': 8,
            'monthly_revenue': 120000,
            'description': 'Test property',
        })
        self.assertRedirects(response, reverse('properties'))
        self.assertEqual(
            Property.objects.filter(landlord=self.landlord).count(),
            count_before + 1
        )

    def test_landlord_cannot_delete_property_with_active_tenants(self):
        """Attempting to delete a property that has tenants fails gracefully."""
        self.client.force_login(self.landlord)
        # self.prop has self.tenant assigned — PROTECT prevents deletion
        response = self.client.post(
            reverse('delete_property', kwargs={'pk': self.prop.pk})
        )
        self.assertTrue(Property.objects.filter(pk=self.prop.pk).exists())
        self.assertRedirects(response, reverse('properties'))

    # ==========================================================================
    # MANAGEMENT COMMANDS
    # ==========================================================================

    def test_generate_rent_command_creates_charge_for_active_tenants(self):
        """Running generate_rent creates a RentCharge for today's month/year."""
        from django.core.management import call_command
        from io import StringIO

        RentCharge.objects.filter(tenant=self.tenant).delete()
        call_command('generate_rent', stdout=StringIO())

        today = datetime.date.today()
        self.assertTrue(
            RentCharge.objects.filter(
                tenant=self.tenant,
                month=today.month,
                year=today.year
            ).exists()
        )

    def test_generate_rent_command_is_idempotent(self):
        """Running generate_rent twice does NOT create a duplicate charge."""
        from django.core.management import call_command
        from io import StringIO

        RentCharge.objects.filter(tenant=self.tenant).delete()
        call_command('generate_rent', stdout=StringIO())
        call_command('generate_rent', stdout=StringIO())

        today = datetime.date.today()
        charge_count = RentCharge.objects.filter(
            tenant=self.tenant, month=today.month, year=today.year
        ).count()
        self.assertEqual(charge_count, 1)

    def test_check_expired_leases_marks_overdue_tenants(self):
        """check_expired_leases sets status='expired' for past lease-end tenants."""
        from django.core.management import call_command
        from io import StringIO

        self.tenant.lease_end = datetime.date.today() - datetime.timedelta(days=1)
        self.tenant.save(update_fields=['lease_end'])

        call_command('check_expired_leases', stdout=StringIO())
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'expired')

    def test_check_expired_leases_ignores_future_leases(self):
        """check_expired_leases leaves tenants with future lease-end dates untouched."""
        from django.core.management import call_command
        from io import StringIO

        self.tenant.lease_end = datetime.date.today() + datetime.timedelta(days=30)
        self.tenant.save(update_fields=['lease_end'])

        call_command('check_expired_leases', stdout=StringIO())
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'active')

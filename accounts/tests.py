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
            role='landlord'
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
        # Should redirect to dashboard on successful signup
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
        
        # Verify user is created with correct role and is active
        new_user = User.objects.get(username='newlandlord')
        self.assertEqual(new_user.role, 'landlord')
        self.assertTrue(new_user.is_active)

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
        self.assertNotIn("’", email.body)
        self.assertNotIn("you’ve", email.body)
        self.assertNotIn("You're", email.body)


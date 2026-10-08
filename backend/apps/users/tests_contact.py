from django.test import TestCase
from django.core import mail
from django.test.utils import override_settings
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch

from apps.users.models import ContactMessage
from apps.users.services.contact_email import send_contact_emails


class ContactMessageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.contact_url = '/api/contact/'
        self.auth_contact_url = '/api/auth/contact/'
        self.valid_payload = {
            'name': 'Abebe Bikila',
            'email': 'abebe@ethiorunner.et',
            'domain': 'ethiorunner.et',
            'message': 'Hello DoxaRank team, we would like to schedule an enterprise crawl for our site.'
        }

    def test_contact_submission_success(self):
        """Test submitting a valid contact form creates DB entry and sends emails."""
        response = self.client.post(self.contact_url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], 'Abebe Bikila')
        self.assertEqual(response.data['data']['email'], 'abebe@ethiorunner.et')

        # Verify DB object
        msg = ContactMessage.objects.get(email='abebe@ethiorunner.et')
        self.assertEqual(msg.name, 'Abebe Bikila')
        self.assertEqual(msg.domain, 'ethiorunner.et')
        self.assertTrue(msg.email_sent)
        self.assertEqual(msg.email_error, '')

        # Verify emails sent to outbox (admin alert + user auto-responder)
        self.assertGreaterEqual(len(mail.outbox), 2)
        admin_mail = mail.outbox[0]
        user_mail = mail.outbox[1]
        self.assertIn('[DoxaRank Contact]', admin_mail.subject)
        self.assertEqual(admin_mail.reply_to, ['abebe@ethiorunner.et'])
        self.assertIn('We received your message', user_mail.subject)
        self.assertIn('abebe@ethiorunner.et', user_mail.to)

    def test_contact_submission_via_auth_prefix(self):
        """Test /api/auth/contact/ endpoint also works identically."""
        response = self.client.post(self.auth_contact_url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])

    def test_contact_submission_validation_errors(self):
        """Test invalid data returns 400 Bad Request with field errors."""
        invalid_payload = {
            'name': 'A',  # too short (< 2)
            'email': 'not-an-email',
            'message': 'hi',  # too short (< 5)
        }
        response = self.client.post(self.contact_url, invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('name', response.data['errors'])
        self.assertIn('email', response.data['errors'])
        self.assertIn('message', response.data['errors'])

    def test_email_failure_gracefully_handled(self):
        """Test that if email backend raises exception, DB record still saves and API returns 201."""
        with patch('apps.users.services.contact_email.EmailMultiAlternatives.send', side_effect=Exception("SMTP Connection refused")):
            response = self.client.post(self.contact_url, self.valid_payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            msg = ContactMessage.objects.filter(email='abebe@ethiorunner.et').first()
            self.assertIsNotNone(msg)
            self.assertFalse(msg.email_sent)
            self.assertIn('SMTP Connection refused', msg.email_error)

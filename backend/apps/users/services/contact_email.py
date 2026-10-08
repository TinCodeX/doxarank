import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)


def send_contact_emails(contact_message):
    """
    Sends email notifications for an inbound contact message:
    1. Alert email to the DoxaRank support/admin team (with reply-to set to submitter).
    2. Confirmation receipt email to the inquiry sender.
    
    Updates the contact_message record with delivery status.
    """
    errors = []
    
    recipient_admin = getattr(settings, 'CONTACT_NOTIFICATION_EMAIL', 'support@doxarank.com')
    default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', 'DoxaRank <noreply@doxarank.com>')
    
    # ---------------------------------------------------------
    # 1. Admin / Support Notification
    # ---------------------------------------------------------
    admin_subject = f"[DoxaRank Contact] Inquiry from {contact_message.name}"
    admin_plain = f"""New inbound message received on DoxaRank marketing contact form:

Name: {contact_message.name}
Email: {contact_message.email}
Domain / Website: {contact_message.domain or 'Not provided'}
IP Address: {contact_message.ip_address or 'Unknown'}
Submitted At: {contact_message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

Message:
----------------------------------------
{contact_message.message}
----------------------------------------

You can reply directly to this email to reach {contact_message.name}.
"""
    
    safe_name = escape(contact_message.name)
    safe_email = escape(contact_message.email)
    safe_domain = escape(contact_message.domain or 'Not provided')
    safe_msg = escape(contact_message.message).replace('\n', '<br>')
    
    admin_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
    <div style="background: linear-gradient(135deg, #24143C 0%, #774DA9 100%); padding: 24px; color: #ffffff;">
      <h2 style="margin: 0; font-size: 20px; font-weight: 700;">New Contact Form Message</h2>
      <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.85;">DoxaRank Inbound Lead & Support</p>
    </div>
    <div style="padding: 24px;">
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
          <td style="padding: 8px 0; font-size: 13px; color: #64748b; width: 140px; font-weight: 600;">Sender Name:</td>
          <td style="padding: 8px 0; font-size: 14px; color: #0f172a; font-weight: 600;">{safe_name}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; font-size: 13px; color: #64748b; font-weight: 600;">Sender Email:</td>
          <td style="padding: 8px 0; font-size: 14px; color: #774DA9; font-weight: 600;"><a href="mailto:{safe_email}" style="color: #774DA9;">{safe_email}</a></td>
        </tr>
        <tr>
          <td style="padding: 8px 0; font-size: 13px; color: #64748b; font-weight: 600;">Website / Domain:</td>
          <td style="padding: 8px 0; font-size: 14px; color: #0f172a;">{safe_domain}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; font-size: 13px; color: #64748b; font-weight: 600;">IP Address:</td>
          <td style="padding: 8px 0; font-size: 13px; color: #64748b;">{contact_message.ip_address or 'Unknown'}</td>
        </tr>
      </table>
      
      <div style="background-color: #faf5ff; border: 1px solid #ebd5ff; border-radius: 8px; padding: 16px; margin-top: 12px;">
        <h4 style="margin: 0 0 8px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #774DA9;">Message</h4>
        <div style="font-size: 14px; color: #334155; line-height: 1.7;">
          {safe_msg}
        </div>
      </div>
      
      <p style="margin-top: 24px; font-size: 12px; color: #94a3b8; text-align: center;">
        Reply directly to this email to respond to {safe_name}.
      </p>
    </div>
  </div>
</body>
</html>"""

    try:
        admin_email = EmailMultiAlternatives(
            subject=admin_subject,
            body=admin_plain,
            from_email=default_from,
            to=[recipient_admin],
            reply_to=[contact_message.email],
        )
        admin_email.attach_alternative(admin_html, "text/html")
        admin_email.send(fail_silently=False)
        logger.info(f"Contact notification email sent to admin {recipient_admin} for inquiry #{contact_message.id}")
    except Exception as e:
        logger.error(f"Failed to send admin contact email for #{contact_message.id}: {e}", exc_info=True)
        errors.append(f"Admin email: {str(e)}")

    # ---------------------------------------------------------
    # 2. Submitter Auto-Acknowledgment
    # ---------------------------------------------------------
    user_subject = "We received your message — DoxaRank Support"
    user_plain = f"""Hi {contact_message.name},

Thank you for reaching out to DoxaRank!

We have successfully received your inquiry. Our support and SEO specialist team based in Addis Ababa, Ethiopia will review your message and get back to you within 24 hours.

Summary of your message:
----------------------------------------
{contact_message.message}
----------------------------------------

If you have urgent inquiries, feel free to write directly to support@doxarank.com.

Best regards,
The DoxaRank Team
https://doxarank.com
"""

    user_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; padding: 24px;">
  <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
    <div style="background: linear-gradient(135deg, #24143C 0%, #774DA9 100%); padding: 24px; color: #ffffff; text-align: center;">
      <h2 style="margin: 0; font-size: 22px; font-weight: 700;">DoxaRank</h2>
      <p style="margin: 6px 0 0; font-size: 13px; opacity: 0.9;">Inquiry Confirmation</p>
    </div>
    <div style="padding: 28px 24px;">
      <h3 style="margin: 0 0 12px; font-size: 18px; color: #0f172a;">Hi {safe_name},</h3>
      <p style="font-size: 14px; color: #334155; margin-bottom: 16px;">
        Thank you for contacting DoxaRank! We have received your message and our team will get back to you within 24 hours.
      </p>
      
      <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 6px;">Your Inquiry</div>
        <div style="font-size: 13px; color: #475569; line-height: 1.6;">
          {safe_msg}
        </div>
      </div>

      <p style="font-size: 13px; color: #64748b;">
        If you have any additional questions or need enterprise onboarding immediately, you can also reach us directly at <a href="mailto:support@doxarank.com" style="color: #774DA9; font-weight: 600;">support@doxarank.com</a>.
      </p>
      
      <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
      
      <p style="margin: 0; font-size: 13px; color: #334155; font-weight: 600;">Warm regards,</p>
      <p style="margin: 2px 0 0; font-size: 13px; color: #64748b;">The DoxaRank Team &bull; Addis Ababa, Ethiopia</p>
    </div>
  </div>
</body>
</html>"""

    try:
        user_email = EmailMultiAlternatives(
            subject=user_subject,
            body=user_plain,
            from_email=default_from,
            to=[contact_message.email],
        )
        user_email.attach_alternative(user_html, "text/html")
        user_email.send(fail_silently=False)
        logger.info(f"Contact receipt email sent to user {contact_message.email} for inquiry #{contact_message.id}")
    except Exception as e:
        logger.error(f"Failed to send user confirmation email for #{contact_message.id}: {e}", exc_info=True)
        errors.append(f"User email: {str(e)}")

    if not errors:
        contact_message.email_sent = True
        contact_message.email_error = ''
    else:
        contact_message.email_sent = False
        contact_message.email_error = '; '.join(errors)
        
    contact_message.save(update_fields=['email_sent', 'email_error'])
    return len(errors) == 0, contact_message.email_error


def send_contact_emails_by_id(contact_message_id):
    """Helper to load ContactMessage and send emails."""
    from apps.users.models import ContactMessage
    try:
        msg = ContactMessage.objects.get(id=contact_message_id)
        return send_contact_emails(msg)
    except ContactMessage.DoesNotExist:
        logger.warning(f"ContactMessage id={contact_message_id} does not exist.")
        return False, "Not found"

import logging
from celery import shared_task
from .services import send_contact_emails_by_id

logger = logging.getLogger(__name__)


@shared_task(name='apps.users.tasks.send_contact_email_task')
def send_contact_email_task(contact_message_id):
    """
    Celery task to asynchronously send notification and confirmation emails
    for a contact message.
    """
    logger.info(f"[Celery] Processing contact emails for id={contact_message_id}")
    success, error = send_contact_emails_by_id(contact_message_id)
    return {'success': success, 'error': error}

from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.subscriptions'
    verbose_name = 'Subscriptions & Plan Entitlements'

    def ready(self):
        # Import signal handlers if needed
        try:
            import apps.subscriptions.signals  # noqa
        except ImportError:
            pass

from .base import PaymentProvider, CheckoutResult, VerificationResult
from .doxa import DoxaPaymentsProvider, WebhookSecurityError


def get_payment_provider(provider_name: str = 'doxa') -> PaymentProvider:
    """
    Factory function returning an instance of the requested payment gateway provider.
    Defaults to 'doxa' for Ethiopian and regional payment processing.
    """
    if provider_name == 'doxa':
        return DoxaPaymentsProvider()
    # Can be extended in the future with other providers (e.g. stripe, paypal)
    return DoxaPaymentsProvider()


__all__ = [
    'PaymentProvider',
    'CheckoutResult',
    'VerificationResult',
    'DoxaPaymentsProvider',
    'WebhookSecurityError',
    'get_payment_provider',
]

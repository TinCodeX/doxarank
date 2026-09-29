from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, Any


@dataclass
class CheckoutResult:
    """
    Standardized result returned after creating a payment session.
    """
    checkout_url: str
    provider_reference: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """
    Standardized result returned after verifying payment authenticity and settlement.
    """
    is_successful: bool
    status: str  # PaymentStatus choices: PENDING, SUCCESS, FAILED, CANCELLED
    provider_transaction_id: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    """
    Abstract payment gateway provider interface for DoxaRank subscription billing.
    Decouples payment orchestration from gateway-specific implementations.
    """

    @abstractmethod
    def create_checkout(
        self,
        transaction,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> CheckoutResult:
        """
        Create a payment checkout session with the external provider.
        """
        pass

    @abstractmethod
    def verify_payment(
        self,
        transaction,
        payload: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify payment status directly with the provider or validate callback payload.
        """
        pass

    @abstractmethod
    def get_transaction(
        self,
        transaction
    ) -> VerificationResult:
        """
        Query external gateway for current transaction state.
        """
        pass

    @abstractmethod
    def handle_webhook(
        self,
        payload: Dict[str, Any],
        raw_body: bytes,
        headers: Dict[str, str]
    ) -> VerificationResult:
        """
        Verify webhook signature, authenticity, and extract transaction result.
        """
        pass

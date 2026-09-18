"""
DoxaRank External System Adapters Package (Milestone 6.5).
"""

from .base import (
    BaseExternalAdapter,
    ExternalSystemType,
    CMSCapability,
    GitCapability,
    WebhookCapability,
    ExternalOperationResult,
    is_safe_target_url,
    redact_secrets,
)
from .cms_adapter import CMSAdapter
from .git_adapter import GitAdapter
from .webhook_adapter import WebhookAdapter
from .registry import (
    ExternalAdapterRegistry,
    get_external_adapter_registry,
    get_external_adapter,
)
from .service import (
    ExternalIntegrationService,
    READ_ONLY_OPERATIONS,
    MUTATION_AUTHORIZED_AGENTS,
)

__all__ = [
    "BaseExternalAdapter",
    "ExternalSystemType",
    "CMSCapability",
    "GitCapability",
    "WebhookCapability",
    "ExternalOperationResult",
    "is_safe_target_url",
    "redact_secrets",
    "CMSAdapter",
    "GitAdapter",
    "WebhookAdapter",
    "ExternalAdapterRegistry",
    "get_external_adapter_registry",
    "get_external_adapter",
    "ExternalIntegrationService",
    "READ_ONLY_OPERATIONS",
    "MUTATION_AUTHORIZED_AGENTS",
]

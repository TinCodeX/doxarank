"""
DoxaRank External System Adapter Registry (Milestone 6.5).

Provides centralized discovery and capability matching across external system adapters.
Guarantees explicit capability routing:
- CMS -> CMSAdapter
- Git -> GitAdapter
- Webhook -> WebhookAdapter

Forbids arbitrary connector registration or bypassing ToolRegistry.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from .base import (
    BaseExternalAdapter,
    ExternalSystemType,
    CMSCapability,
    GitCapability,
    WebhookCapability,
)
from .cms_adapter import CMSAdapter
from .git_adapter import GitAdapter
from .webhook_adapter import WebhookAdapter

logger = logging.getLogger(__name__)


class ExternalAdapterRegistry:
    """
    Registry for external system adapters with explicit capability discovery.
    """

    def __init__(self):
        self._adapters: Dict[str, BaseExternalAdapter] = {}
        self._register_defaults()

    def _register_defaults(self):
        cms_adapter = CMSAdapter()
        git_adapter = GitAdapter()
        webhook_adapter = WebhookAdapter()

        self._adapters[ExternalSystemType.CMS.value] = cms_adapter
        self._adapters[ExternalSystemType.GIT.value] = git_adapter
        self._adapters[ExternalSystemType.WEBHOOK.value] = webhook_adapter

    def get_adapter(self, system_type: str, provider: Optional[str] = None) -> BaseExternalAdapter:
        sys_key = (system_type or "").lower().strip()
        if sys_key not in self._adapters:
            raise KeyError(f"No adapter registered for external system type '{system_type}'.")
        return self._adapters[sys_key]

    def get_adapter_for_capability(self, capability: str) -> BaseExternalAdapter:
        cap = (capability or "").strip().upper()
        if cap.startswith("CMS."):
            return self.get_adapter(ExternalSystemType.CMS.value)
        elif cap.startswith("GIT."):
            return self.get_adapter(ExternalSystemType.GIT.value)
        elif cap.startswith("WEBHOOK."):
            return self.get_adapter(ExternalSystemType.WEBHOOK.value)
        raise ValueError(f"Unknown or unsupported capability '{capability}'.")

    def discover_capabilities(self, system_type: Optional[str] = None) -> Dict[str, List[str]]:
        """Returns structured dictionary of declared capabilities by system type."""
        result = {}
        if system_type:
            adapter = self.get_adapter(system_type)
            result[adapter.system_type] = adapter.get_capabilities()
        else:
            for sys_type, adapter in self._adapters.items():
                result[sys_type] = adapter.get_capabilities()
        return result


_REGISTRY_INSTANCE: Optional[ExternalAdapterRegistry] = None


def get_external_adapter_registry() -> ExternalAdapterRegistry:
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is None:
        _REGISTRY_INSTANCE = ExternalAdapterRegistry()
    return _REGISTRY_INSTANCE


def get_external_adapter(system_type: str, provider: Optional[str] = None) -> BaseExternalAdapter:
    return get_external_adapter_registry().get_adapter(system_type, provider)

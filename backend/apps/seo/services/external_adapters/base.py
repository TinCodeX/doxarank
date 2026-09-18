"""
DoxaRank External System Adapter & Capability Abstraction Layer (Milestone 6.5).

Defines the foundational abstractions for multi-system agent operations across:
- CMS (WordPress, Shopify, generic CMS)
- Git (Repository inspection, branch creation, file modification, PR/commit staging)
- Webhooks / External APIs (Allowlisted endpoints, verified payloads, bounded retries)

Enforces:
1. Structured, explicit capabilities (no execute_anything or arbitrary command execution).
2. Anti-SSRF & domain allowlists (no arbitrary URL/IP execution).
3. Secret redaction on all payloads, logs, and results.
4. Deterministic reversibility / rollback state capture.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from django.utils import timezone

logger = logging.getLogger(__name__)


class ExternalSystemType(str, Enum):
    CMS = "cms"
    GIT = "git"
    WEBHOOK = "webhook"


class CMSCapability(str, Enum):
    READ_PAGE = "CMS.READ_PAGE"
    READ_METADATA = "CMS.READ_METADATA"
    UPDATE_METADATA = "CMS.UPDATE_METADATA"
    PUBLISH_CONTENT = "CMS.PUBLISH_CONTENT"


class GitCapability(str, Enum):
    READ_REPOSITORY = "GIT.READ_REPOSITORY"
    CREATE_BRANCH = "GIT.CREATE_BRANCH"
    WRITE_FILE = "GIT.WRITE_FILE"
    CREATE_COMMIT = "GIT.CREATE_COMMIT"


class WebhookCapability(str, Enum):
    SEND_WEBHOOK = "WEBHOOK.SEND_WEBHOOK"
    CHECK_STATUS = "WEBHOOK.CHECK_STATUS"


# Common disallowed hosts and private IP ranges for Anti-SSRF
DISALLOWED_HOSTS: Set[str] = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254", "metadata.google.internal"
}


def is_safe_target_url(target_url: str, allowlisted_domains: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Validates that a URL is safe to query/mutate.
    Strictly forbids private IP ranges, loopback, link-local (cloud metadata),
    and non-http(s) schemes. If allowlisted_domains is provided, target must match.
    """
    if not target_url or not isinstance(target_url, str):
        return False, "Target URL must be a non-empty string."

    try:
        parsed = urlparse(target_url.strip())
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Disallowed URL scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed."

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, "Target URL missing valid hostname."

    if hostname in DISALLOWED_HOSTS or hostname.endswith(".local") or hostname.endswith(".internal"):
        return False, f"Target hostname '{hostname}' is forbidden (SSRF protection)."

    # Check for private/loopback IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Target IP '{hostname}' resolves to private/internal network (SSRF protection)."
    except ValueError:
        # Not a raw IP literal, normal domain name
        pass

    if allowlisted_domains:
        normalized_allowed = [d.lower().strip() for d in allowlisted_domains if d]
        if normalized_allowed:
            domain_match = any(
                hostname == d or hostname.endswith(f".{d}")
                for d in normalized_allowed
            )
            if not domain_match:
                return False, f"Target domain '{hostname}' is not in configured allowlisted domains: {normalized_allowed}."

    return True, None


def redact_secrets(data: Any) -> Any:
    """Recursively scrub secrets, tokens, and authorization headers from data structures."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ['password', 'secret', 'token', 'auth_token', 'api_key', 'authorization', 'bearer', 'cookie']):
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = redact_secrets(v)
        return cleaned
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, str):
        clean = re.sub(r'\b(sk-[a-zA-Z0-9_-]{8,}|ghp_[a-zA-Z0-9]{20,}|glpat-[a-zA-Z0-9_-]{20,})', '***REDACTED***', data)
        clean = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer ***REDACTED***', clean, flags=re.IGNORECASE)
        clean = re.sub(r'(?i)(api[_-]?key|apikey|secret|password|token|auth_token)\s*[:=]\s*[^\s,;]+', r'\1=***REDACTED***', clean)
        return clean
    return data


@dataclass
class ExternalOperationResult:
    """
    Standardized, structured execution outcome for any external system adapter.
    Preserves audit trail, before/after states, and error categorization without secrets.
    """
    success: bool
    system: str
    provider: str
    operation: str
    target: str
    status_code: Optional[int] = None
    response_summary: Dict[str, Any] = field(default_factory=dict)
    changed: bool = False
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    error_category: str = ""
    error_message: Optional[str] = None
    correlation_id: str = ""
    duration_ms: int = 0
    retry_count: int = 0
    is_reversible: bool = False
    notes: str = ""

    def __post_init__(self):
        self.response_summary = redact_secrets(self.response_summary or {})
        self.before_state = redact_secrets(self.before_state or {})
        self.after_state = redact_secrets(self.after_state or {})
        if self.error_message:
            self.error_message = redact_secrets(self.error_message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "system": self.system,
            "provider": self.provider,
            "operation": self.operation,
            "target": self.target,
            "status_code": self.status_code,
            "response_summary": self.response_summary,
            "changed": self.changed,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "correlation_id": self.correlation_id,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "is_reversible": self.is_reversible,
            "notes": self.notes,
        }


class BaseExternalAdapter(ABC):
    """
    Abstract Base Class for all DoxaRank External System Adapters.
    Every adapter MUST declare supported providers and explicit capabilities.
    """

    system_type: str = "base"
    supported_providers: List[str] = []
    declared_capabilities: Set[str] = set()

    def get_capabilities(self) -> List[str]:
        return sorted(list(self.declared_capabilities))

    def supports_capability(self, capability: str) -> bool:
        return capability in self.declared_capabilities

    def supports_provider(self, provider: str) -> bool:
        return (provider or "").lower().strip() in self.supported_providers

    @abstractmethod
    def validate_parameters(self, operation: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate input parameters against schema for the given operation."""
        pass

    @abstractmethod
    def preview(
        self,
        connection: Any,
        operation: str,
        target: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a structured, non-destructive before/after preview diff."""
        pass

    @abstractmethod
    def execute(
        self,
        connection: Any,
        operation: str,
        target: str,
        params: Dict[str, Any],
        correlation_id: str = "",
        retry_count: int = 0
    ) -> ExternalOperationResult:
        """Execute the operation against the external target system."""
        pass

    @abstractmethod
    def verify(
        self,
        connection: Any,
        operation: str,
        target: str,
        expected_state: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verify the external state post-execution."""
        pass

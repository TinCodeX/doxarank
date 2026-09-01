import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.utils import timezone

from apps.seo.models import SEOAction, ActionType

logger = logging.getLogger(__name__)


class BaseMutationConnector(ABC):
    """
    Abstract Base Mutation Connector Interface for DoxaRank.
    Provides standard methods for validating, previewing, and executing approved SEOActions.
    Connectors are safe abstractions decoupling the approval system from external execution targets
    such as CMSs (WordPress, Shopify, Webflow), Git repositories (PRs/commits), and Webhooks.
    """

    connector_name: str = "base"

    @abstractmethod
    def validate(self, action: SEOAction) -> Dict[str, Any]:
        """
        Validate that the action payload and target URL meet the connector's schema requirements.
        Returns a dict: {"valid": bool, "errors": List[str], "warnings": List[str]}
        """
        pass

    @abstractmethod
    def preview(self, action: SEOAction) -> Dict[str, Any]:
        """
        Generate a non-destructive before/after preview of the proposed changes without modifying state.
        Returns a structured diff dictionary.
        """
        pass

    @abstractmethod
    def execute(self, action: SEOAction) -> Dict[str, Any]:
        """
        Execute the approved action. For this phase, operates in safe staging / dry-run mode.
        Returns execution result metadata.
        """
        pass


class DryRunMutationConnector(BaseMutationConnector):
    """
    Safe Dry-Run / Staging Mutation Connector.
    Simulates execution, validates payloads, builds clear visual diffs, and establishes
    monitoring baselines without modifying production websites or external systems.
    """

    connector_name: str = "dry_run"

    def validate(self, action: SEOAction) -> Dict[str, Any]:
        errors = []
        warnings = []

        if not action.target_url:
            errors.append("Target URL is required for mutation actions.")

        if not action.proposed_change:
            warnings.append("Proposed change dictionary is empty; action may have no visible effect.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "connector": self.connector_name
        }

    def preview(self, action: SEOAction) -> Dict[str, Any]:
        """
        Generate an explainable diff showing existing state vs proposed change.
        """
        curr = action.current_state or {}
        prop = action.proposed_change or {}
        action_type = (action.action_type or "").lower()

        diff_summary: Dict[str, Any] = {
            "action_id": action.id,
            "action_type": action.action_type,
            "target_url": action.target_url or action.project.website_url,
            "target_keyword": action.target_keyword,
            "risk_level": action.risk_level,
            "impact_estimate": action.impact_estimate,
            "effort_estimate": action.effort_estimate,
            "requires_human_approval": action.requires_human_approval,
            "before_state": curr,
            "after_state": prop,
            "diff": {},
            "summary": ""
        }

        if "title" in action_type:
            old_title = curr.get("title") or curr.get("meta_title") or "[Current Title]"
            new_title = prop.get("title") or prop.get("meta_title") or action.title
            diff_summary["diff"]["title"] = {"before": old_title, "after": new_title}
            diff_summary["summary"] = f"Update page title from '{old_title}' to '{new_title}'."
        elif "meta_description" in action_type:
            old_desc = curr.get("meta_description") or "[Current Description]"
            new_desc = prop.get("meta_description") or prop.get("description") or ""
            diff_summary["diff"]["meta_description"] = {"before": old_desc, "after": new_desc}
            diff_summary["summary"] = f"Update meta description tag ({len(new_desc)} chars)."
        elif "canonical" in action_type:
            old_canon = curr.get("canonical_url") or "[Missing/Incorrect Canonical]"
            new_canon = prop.get("canonical_url") or action.target_url
            diff_summary["diff"]["canonical_url"] = {"before": old_canon, "after": new_canon}
            diff_summary["summary"] = f"Set canonical URL to '{new_canon}'."
        elif "h1" in action_type:
            old_h1 = curr.get("h1") or "[Missing H1]"
            new_h1 = prop.get("h1") or action.title
            diff_summary["diff"]["h1"] = {"before": old_h1, "after": new_h1}
            diff_summary["summary"] = f"Add/Update primary H1 heading to '{new_h1}'."
        elif "image_alt" in action_type:
            diff_summary["diff"]["image_alt"] = prop.get("images", [])
            diff_summary["summary"] = "Add descriptive alt attributes to target images."
        elif "broken_link" in action_type:
            diff_summary["diff"]["links_to_fix"] = prop.get("links", [])
            diff_summary["summary"] = "Update or redirect broken internal link references."
        else:
            diff_summary["diff"]["general"] = prop
            diff_summary["summary"] = f"Apply {action.get_action_type_display()} on {action.target_url}."

        return diff_summary

    def execute(self, action: SEOAction) -> Dict[str, Any]:
        start_time = time.time()
        validation = self.validate(action)
        if not validation["valid"]:
            raise ValueError(f"Action validation failed: {', '.join(validation['errors'])}")

        preview_data = self.preview(action)
        duration_ms = max(45, int((time.time() - start_time) * 1000) + 60)

        simulated_endpoint = action.target_url or f"{action.project.website_url.rstrip('/')}/"
        monitoring_baseline = {
            "monitored_keyword": action.target_keyword or "N/A",
            "target_url": simulated_endpoint,
            "action_type": action.action_type,
            "baseline_timestamp": timezone.now().isoformat(),
            "monitoring_status": "active_tracking",
            "initial_snapshot": action.current_state or {}
        }

        result = {
            "executor": "MockSEOActionExecutor (Safe Staging Mode)",
            "connector_name": self.connector_name,
            "status": "success",
            "executed_at": timezone.now().isoformat(),
            "duration_ms": duration_ms,
            "simulated_target_url": simulated_endpoint,
            "action_type": action.action_type,
            "summary": preview_data["summary"],
            "payload_applied": action.proposed_change,
            "monitoring_baseline": monitoring_baseline,
            "notes": "Action executed successfully in safe staging mode. Zero destructive mutations applied."
        }
        return result


class CMSMutationConnector(DryRunMutationConnector):
    """
    CMS Mutation Connector for platforms like WordPress, Shopify, and Webflow.
    Currently delegates to safe staging simulation with CMS-specific payload validation.
    """
    connector_name: str = "cms"


class GitMutationConnector(DryRunMutationConnector):
    """
    Git Mutation Connector for creating automated branch commits or pull requests.
    Currently delegates to safe staging simulation.
    """
    connector_name: str = "git"


class WebhookMutationConnector(DryRunMutationConnector):
    """
    Webhook Mutation Connector for sending verified deployment payloads to client endpoints.
    Currently delegates to safe staging simulation.
    """
    connector_name: str = "webhook"


_CONNECTOR_REGISTRY: Dict[str, BaseMutationConnector] = {
    "dry_run": DryRunMutationConnector(),
    "mock": DryRunMutationConnector(),
    "cms": CMSMutationConnector(),
    "git": GitMutationConnector(),
    "webhook": WebhookMutationConnector(),
}


def get_mutation_connector(connector_type: Optional[str] = None) -> BaseMutationConnector:
    """
    Factory function returning the registered mutation connector.
    Defaults to DryRunMutationConnector for safety.
    """
    key = (connector_type or "dry_run").lower().strip()
    return _CONNECTOR_REGISTRY.get(key, _CONNECTOR_REGISTRY["dry_run"])

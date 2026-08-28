import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.utils import timezone
from apps.seo.models import SEOAction, ActionStatus

logger = logging.getLogger(__name__)


class BaseSEOActionExecutor(ABC):
    """
    Abstract base executor interface for applying approved SEO actions.
    Future implementations may include WordPressExecutor, ShopifyExecutor,
    WebflowExecutor, CustomAPIExecutor, GitHubPRActionExecutor, JiraTaskExecutor.
    """

    @abstractmethod
    def execute(self, action: SEOAction) -> Dict[str, Any]:
        """
        Execute an approved SEO action safely and return execution result payload.
        Must enforce that action is approved before executing.
        """
        pass


class MockSEOActionExecutor(BaseSEOActionExecutor):
    """
    Safe Mock Action Executor for DoxaRank.
    Validates human approval, executes safe simulation, captures execution metadata,
    records before/after monitoring baseline, and transitions action status to completed.
    Guarantees no arbitrary/unsafe direct modification of third-party client sites.
    """

    def execute(self, action: SEOAction) -> Dict[str, Any]:
        """
        Executes an approved SEOAction in safe staging mode.
        """
        # Strict validation: Only approved or ready_to_execute actions can be executed
        if action.status not in [ActionStatus.APPROVED, ActionStatus.READY_TO_EXECUTE]:
            raise ValueError(
                f"Cannot execute action #{action.id}. Current status is '{action.status}'. "
                f"A human must review and approve the action before execution."
            )

        start_time = time.time()
        action.status = ActionStatus.EXECUTING
        action.save(update_fields=['status', 'updated_at'])

        try:
            # Simulate execution delay and processing
            simulated_endpoint = action.target_url or f"{action.project.website_url.rstrip('/')}/"

            # Construct monitoring baseline snapshot
            monitoring_baseline = {
                "monitored_keyword": action.target_keyword or "N/A",
                "target_url": simulated_endpoint,
                "action_type": action.action_type,
                "baseline_timestamp": timezone.now().isoformat(),
                "monitoring_status": "active_tracking",
                "initial_snapshot": action.current_state or {}
            }

            deployment_summary = self._build_deployment_summary(action)

            duration_ms = max(45, int((time.time() - start_time) * 1000) + 75)

            result_metadata = {
                "executor": "MockSEOActionExecutor (Safe Staging Mode)",
                "status": "success",
                "executed_at": timezone.now().isoformat(),
                "duration_ms": duration_ms,
                "simulated_target_url": simulated_endpoint,
                "action_type": action.action_type,
                "deployment_summary": deployment_summary,
                "payload_applied": action.proposed_change,
                "monitoring_baseline": monitoring_baseline,
                "notes": "Action executed successfully in safe staging mode. Ready for live monitoring."
            }

            action.status = ActionStatus.COMPLETED
            action.completed_at = timezone.now()
            action.execution_metadata = result_metadata
            action.save(update_fields=['status', 'completed_at', 'execution_metadata', 'updated_at'])

            logger.info(f"Successfully executed SEOAction #{action.id} via MockSEOActionExecutor.")
            return result_metadata

        except Exception as exc:
            action.status = ActionStatus.FAILED
            error_metadata = {
                "executor": "MockSEOActionExecutor",
                "status": "failed",
                "failed_at": timezone.now().isoformat(),
                "error": str(exc),
                "action_type": action.action_type
            }
            action.execution_metadata = error_metadata
            action.save(update_fields=['status', 'execution_metadata', 'updated_at'])
            logger.error(f"Execution failed for SEOAction #{action.id}: {exc}")
            raise

    def _build_deployment_summary(self, action: SEOAction) -> str:
        """
        Generate a human-readable deployment summary based on action type.
        """
        proposed = action.proposed_change or {}
        if action.action_type == 'publish_new_content':
            title = proposed.get('title', action.title)
            slug = proposed.get('slug', action.target_url)
            return f"Published new content asset '{title}' to route `{slug}` with structured Article schema & FAQs."
        elif action.action_type == 'update_meta_description':
            desc = proposed.get('meta_description', '')
            return f"Updated meta description tag on `{action.target_url}` ({len(desc)} characters)."
        elif action.action_type == 'update_title':
            title = proposed.get('title', '')
            return f"Updated title tag on `{action.target_url}` to '{title}'."
        elif action.action_type == 'update_slug':
            slug = proposed.get('slug', '')
            return f"Configured 301 redirect and updated URL slug to `{slug}` on `{action.target_url}`."
        elif action.action_type == 'add_structured_data':
            return f"Injected valid JSON-LD structured data into header of `{action.target_url}`."
        elif action.action_type == 'add_internal_links':
            links_count = len(proposed.get('internal_links', []))
            return f"Deployed {links_count} contextual internal links pointing to relevant subpages."
        else:
            return f"Applied on-page SEO optimization package for '{action.target_keyword}' on `{action.target_url}`."


def get_action_executor(executor_type: Optional[str] = None) -> BaseSEOActionExecutor:
    """
    Factory function returning the configured SEO Action Executor instance.
    Defaults to MockSEOActionExecutor for safety.
    """
    return MockSEOActionExecutor()

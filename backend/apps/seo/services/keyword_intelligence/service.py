"""
Keyword Intelligence Service for DoxaRank.

Coordinates caching, throttling, snapshot recording, multi-tenant security,
and dispatching to provider layer.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.seo.models import (
    Keyword, KeywordIntelligence, KeywordIntelligenceSnapshot,
    IntelligenceStatus, CompetitionLevel, SearchIntent
)
from apps.projects.models import Project
from apps.subscriptions.services import PlanEntitlementService
from apps.subscriptions.models import FeatureCode
from apps.subscriptions.exceptions import FeatureNotEntitledException

from .provider import (
    get_keyword_intelligence_provider,
    KeywordMetricsResult,
    BaseKeywordIntelligenceProvider
)
from .intent_classifier import classify_search_intent

logger = logging.getLogger(__name__)


class KeywordIntelligenceService:
    """
    Core service managing keyword intelligence retrieval, caching, and refreshes.
    """

    @classmethod
    def get_or_create_intelligence(cls, keyword: Keyword) -> KeywordIntelligence:
        """
        Get or initialize the KeywordIntelligence record for a Keyword.
        """
        intel, created = KeywordIntelligence.objects.get_or_create(
            keyword=keyword,
            defaults={
                'source': 'unconfigured',
                'status': IntelligenceStatus.UNAVAILABLE,
                'intent': classify_search_intent(keyword.keyword, keyword.language),
            }
        )
        return intel

    @classmethod
    def refresh_keyword_intelligence(
        cls,
        keyword_id: int,
        force: bool = False,
        provider: Optional[BaseKeywordIntelligenceProvider] = None
    ) -> KeywordIntelligence:
        """
        Refresh keyword intelligence metrics for a single keyword.
        Respects caching TTL and in-progress refresh locks.
        Preserves previously recorded metrics if provider call fails.
        Records historical snapshot on successful refresh.
        """
        try:
            keyword = Keyword.objects.select_related('project', 'project__owner').get(id=keyword_id)
        except Keyword.DoesNotExist:
            logger.error(f"[KeywordIntelligence] Keyword #{keyword_id} not found.")
            raise ValueError(f"Keyword #{keyword_id} does not exist.")

        intelligence = cls.get_or_create_intelligence(keyword)

        # 1. Freshness Check (if not forced, return cached if fresh)
        if not force and intelligence.is_fresh:
            logger.info(f"[KeywordIntelligence] Serving fresh cached intelligence for '{keyword.keyword}'.")
            return intelligence

        # 2. Duplicate refresh / in-progress lock
        now = timezone.now()
        cooldown = getattr(settings, 'KEYWORD_INTELLIGENCE_REFRESH_COOLDOWN_SECONDS', 60)

        if intelligence.status == IntelligenceStatus.REFRESHING and intelligence.updated_at:
            # If refreshing within last 2 minutes, avoid duplicate worker run
            if (now - intelligence.updated_at).total_seconds() < 120:
                logger.info(f"[KeywordIntelligence] Refresh already running for '{keyword.keyword}'. Skipping.")
                return intelligence

        # 3. Minimum cooldown check if recently refreshed
        if not force and intelligence.last_refreshed_at:
            elapsed = (now - intelligence.last_refreshed_at).total_seconds()
            if elapsed < cooldown:
                logger.info(f"[KeywordIntelligence] Cooldown active for '{keyword.keyword}' ({elapsed:.0f}s < {cooldown}s).")
                return intelligence

        # Mark as REFRESHING
        intelligence.status = IntelligenceStatus.REFRESHING
        intelligence.save(update_fields=['status', 'updated_at'])

        # 4. Fetch from provider
        active_provider = provider or get_keyword_intelligence_provider()
        try:
            metrics: KeywordMetricsResult = active_provider.get_keyword_metrics(
                keyword=keyword.keyword,
                country=keyword.country,
                language=keyword.language,
                search_domain=keyword.search_domain,
                device=keyword.device
            )
        except Exception as exc:
            logger.error(f"[KeywordIntelligence] Provider unhandled error for '{keyword.keyword}': {exc}", exc_info=True)
            metrics = KeywordMetricsResult(
                source=active_provider.provider_name,
                success=False,
                error_message=f"Provider call failed: {str(exc)}"
            )

        # 5. Process result
        with transaction.atomic():
            intel_record = KeywordIntelligence.objects.select_for_update().get(id=intelligence.id)

            if metrics.success:
                # Determine intent if not supplied by provider
                derived_intent = metrics.intent or classify_search_intent(keyword.keyword, keyword.language)

                intel_record.search_volume = metrics.search_volume
                intel_record.cpc = metrics.cpc
                intel_record.currency = metrics.currency
                intel_record.competition = metrics.competition
                intel_record.competition_index = metrics.competition_index
                intel_record.difficulty = metrics.difficulty
                intel_record.intent = derived_intent
                intel_record.source = metrics.source
                intel_record.status = IntelligenceStatus.FRESH
                intel_record.error_message = ''
                intel_record.last_refreshed_at = timezone.now()
                intel_record.raw_metadata = metrics.raw_metadata
                intel_record.save()

                # Record historical snapshot
                KeywordIntelligenceSnapshot.objects.create(
                    keyword=keyword,
                    search_volume=metrics.search_volume,
                    cpc=metrics.cpc,
                    currency=metrics.currency,
                    competition=metrics.competition,
                    competition_index=metrics.competition_index,
                    difficulty=metrics.difficulty,
                    intent=derived_intent,
                    source=metrics.source,
                    recorded_at=intel_record.last_refreshed_at,
                    raw_metadata=metrics.raw_metadata,
                )

                logger.info(
                    f"[KeywordIntelligence] Successfully refreshed '{keyword.keyword}': "
                    f"Vol={metrics.search_volume}, CPC={metrics.cpc}, Comp={metrics.competition}."
                )
            else:
                # Failure / Unconfigured handling: preserve existing valid metrics!
                if metrics.source == 'unconfigured':
                    intel_record.status = IntelligenceStatus.UNAVAILABLE
                else:
                    intel_record.status = IntelligenceStatus.ERROR

                intel_record.source = metrics.source
                intel_record.error_message = metrics.error_message
                # If intent not yet set, apply deterministic intent
                if not intel_record.intent:
                    intel_record.intent = classify_search_intent(keyword.keyword, keyword.language)
                intel_record.save()

                logger.warning(
                    f"[KeywordIntelligence] Refresh failed for '{keyword.keyword}' ({metrics.source}): "
                    f"{metrics.error_message}. Preserving previous metrics."
                )

            return intel_record

    @classmethod
    def bulk_refresh_project_keywords(
        cls,
        project_id: int,
        user,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk refresh keyword intelligence for all active keywords under a user's project.
        Enforces project ownership and PlanEntitlementService.
        """
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise ValueError(f"Project #{project_id} not found.")

        # Multi-tenant security check
        if project.owner != user:
            raise PermissionError("You do not own this project.")

        # Subscription entitlement check
        PlanEntitlementService.check_can_use_feature(user, FeatureCode.RANK_TRACKING)

        keywords = list(Keyword.objects.filter(project=project, is_active=True).order_by('-created_at'))
        queued_ids = []

        from apps.seo.tasks import refresh_keyword_intelligence_task

        for kw in keywords:
            # Enqueue Celery task for each keyword
            task = refresh_keyword_intelligence_task.delay(kw.id, force=force)
            queued_ids.append(kw.id)

        return {
            'status': 'queued',
            'project_id': project.id,
            'project_name': project.name,
            'total_keywords': len(keywords),
            'queued_keywords_count': len(queued_ids),
            'keyword_ids': queued_ids,
        }

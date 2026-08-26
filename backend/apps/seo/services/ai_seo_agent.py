import logging
from typing import Optional, List, Dict, Any
from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    SEOInsight, SEORecommendation,
    RecommendationType, RecommendationPriority, RecommendationStatus,
    InsightStatus, KeywordRanking, SearchAnalyticsData
)
from .ai_providers import BaseAIProvider, get_ai_provider

logger = logging.getLogger(__name__)

VALID_TYPES = set(RecommendationType.values)
VALID_PRIORITIES = set(RecommendationPriority.values)


class AISeoAgentService:
    """
    AI SEO Agent Service for DoxaRank.
    Reads structured, deterministic SEO insights and orchestrates LLM providers
    to generate evidence-backed, explainable recommendations for human review.
    """

    def __init__(self, project: Project, provider: Optional[BaseAIProvider] = None):
        self.project = project
        self.provider = provider or get_ai_provider()

    def generate_for_insight(self, insight: SEOInsight) -> SEORecommendation:
        """
        Generate a structured AI recommendation for a specific SEO insight.
        """
        if insight.project_id != self.project.id:
            raise ValueError(f"Insight {insight.id} does not belong to project {self.project.id}.")

        context = self._build_insight_context(insight)
        raw_rec = self.provider.generate_recommendation(context)

        sanitized = self._validate_and_sanitize_response(raw_rec, insight)

        # Upsert recommendation for the insight
        existing = SEORecommendation.objects.filter(
            project=self.project,
            insight=insight,
            status=RecommendationStatus.PENDING_REVIEW
        ).first()

        if existing:
            existing.title = sanitized['title']
            existing.summary = sanitized['summary']
            existing.explanation = sanitized['explanation']
            existing.priority = sanitized['priority']
            existing.recommendation_type = sanitized['recommendation_type']
            existing.recommended_action = sanitized['recommended_action']
            existing.expected_impact = sanitized['expected_impact']
            existing.affected_url = sanitized['affected_url']
            existing.affected_keyword = sanitized['affected_keyword']
            existing.generated_content = sanitized['generated_content']
            existing.save()
            return existing

        recommendation = SEORecommendation.objects.create(
            project=self.project,
            insight=insight,
            recommendation_type=sanitized['recommendation_type'],
            title=sanitized['title'],
            summary=sanitized['summary'],
            explanation=sanitized['explanation'],
            priority=sanitized['priority'],
            recommended_action=sanitized['recommended_action'],
            expected_impact=sanitized['expected_impact'],
            affected_url=sanitized['affected_url'],
            affected_keyword=sanitized['affected_keyword'],
            generated_content=sanitized['generated_content'],
            status=RecommendationStatus.PENDING_REVIEW
        )
        return recommendation

    def generate_batch(self, insight_ids: Optional[List[int]] = None) -> List[SEORecommendation]:
        """
        Generate recommendations for a batch of insights or all open insights for the project.
        """
        qs = SEOInsight.objects.filter(project=self.project)
        if insight_ids:
            qs = qs.filter(id__in=insight_ids)
        else:
            qs = qs.filter(status=InsightStatus.OPEN)

        recommendations: List[SEORecommendation] = []
        for insight in qs:
            try:
                rec = self.generate_for_insight(insight)
                recommendations.append(rec)
            except Exception as e:
                logger.error(f"Failed to generate recommendation for insight #{insight.id}: {e}")

        return recommendations

    def _build_insight_context(self, insight: SEOInsight) -> Dict[str, Any]:
        """
        Extract and assemble structured evidence from the insight and surrounding models.
        """
        context: Dict[str, Any] = {
            "project_name": self.project.name,
            "project_website_url": self.project.website_url,
            "insight_id": insight.id,
            "insight_type": insight.insight_type,
            "severity": insight.severity,
            "title": insight.title,
            "description": insight.description,
            "original_recommendation": insight.recommendation,
            "source": insight.source,
            "url": insight.related_url or self.project.website_url,
            "keyword": insight.related_keyword.keyword if insight.related_keyword else "",
            "metadata": insight.metadata or {}
        }

        # Supplement with historical ranking trend if keyword is attached
        if insight.related_keyword:
            recent_rankings = list(
                KeywordRanking.objects.filter(keyword=insight.related_keyword)
                .order_by('-recorded_at')[:3]
                .values('position', 'ranking_url', 'recorded_at')
            )
            context["recent_rankings"] = [
                {
                    "position": r['position'],
                    "ranking_url": r['ranking_url'] or '',
                    "date": r['recorded_at'].strftime('%Y-%m-%d')
                }
                for r in recent_rankings
            ]

        # Supplement with GSC query performance if available
        if insight.source == 'search_console' and insight.metadata.get('query'):
            query_str = insight.metadata.get('query')
            gsc_data = list(
                SearchAnalyticsData.objects.filter(
                    connection__project=self.project,
                    query__iexact=query_str
                ).order_by('-date')[:5].values('date', 'clicks', 'impressions', 'ctr', 'position')
            )
            context["gsc_observations"] = [
                {
                    "date": str(d['date']),
                    "clicks": d['clicks'],
                    "impressions": d['impressions'],
                    "ctr": float(d['ctr']),
                    "position": float(d['position'])
                }
                for d in gsc_data
            ]

        return context

    def _validate_and_sanitize_response(self, raw: Dict[str, Any], insight: SEOInsight) -> Dict[str, Any]:
        """
        Strict validation ensuring output matches internal choices and schemas.
        """
        title = str(raw.get('title') or f"Recommendation for {insight.title}").strip()
        summary = str(raw.get('summary') or insight.description).strip()
        explanation = str(raw.get('explanation') or insight.description).strip()
        recommended_action = str(raw.get('recommended_action') or insight.recommendation or 'Audit and optimize targeted SEO elements.').strip()
        expected_impact = str(raw.get('expected_impact') or 'Aims to improve search visibility and organic click-through rate.').strip()

        rec_type = raw.get('recommendation_type')
        if rec_type not in VALID_TYPES:
            # Fallback mapping
            type_fallback = {
                'ranking_drop': RecommendationType.RANKING_RECOVERY,
                'ranking_improvement': RecommendationType.KEYWORD_OPTIMIZATION,
                'page_two_keyword': RecommendationType.PAGE_TWO_OPPORTUNITY,
                'high_impressions_low_ctr': RecommendationType.CTR_OPTIMIZATION,
                'low_ctr': RecommendationType.CTR_OPTIMIZATION,
                'technical_seo_issue': RecommendationType.TECHNICAL_SEO,
                'declining_clicks': RecommendationType.RANKING_RECOVERY,
                'declining_impressions': RecommendationType.RANKING_RECOVERY,
            }
            rec_type = type_fallback.get(insight.insight_type, RecommendationType.GENERAL_SEO)

        priority = raw.get('priority')
        if priority not in VALID_PRIORITIES:
            sev_to_prio = {
                'critical': RecommendationPriority.CRITICAL,
                'warning': RecommendationPriority.HIGH,
                'opportunity': RecommendationPriority.MEDIUM,
                'info': RecommendationPriority.LOW
            }
            priority = sev_to_prio.get(insight.severity, RecommendationPriority.HIGH)

        affected_url = str(raw.get('affected_url') or insight.related_url or '').strip()
        affected_keyword = str(raw.get('affected_keyword') or (insight.related_keyword.keyword if insight.related_keyword else '')).strip()
        generated_content = raw.get('generated_content')
        if not isinstance(generated_content, dict):
            generated_content = {}

        return {
            "title": title[:255],
            "summary": summary,
            "explanation": explanation,
            "priority": priority,
            "recommendation_type": rec_type,
            "recommended_action": recommended_action,
            "expected_impact": expected_impact,
            "affected_url": affected_url[:500],
            "affected_keyword": affected_keyword[:255],
            "generated_content": generated_content
        }

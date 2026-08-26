import logging
from typing import Optional, List, Dict, Any
from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    SEORecommendation, SEOInsight, SEOContentBrief,
    BriefContentType, BriefSearchIntent, BriefStatus,
    KeywordRanking, SearchAnalyticsData, AuditIssue
)
from .ai_providers import BaseAIProvider, get_ai_provider

logger = logging.getLogger(__name__)

VALID_CONTENT_TYPES = set(BriefContentType.values)
VALID_INTENTS = set(BriefSearchIntent.values)
VALID_STATUSES = set(BriefStatus.values)


class SEOContentBriefService:
    """
    SEO Content Brief Generator Service for DoxaRank.
    Takes an AI recommendation, grounds it in real Search Console data, ranking history,
    and site audit findings, then synthesizes a comprehensive, actionable SEO content brief.
    """

    def __init__(self, project: Project, provider: Optional[BaseAIProvider] = None):
        self.project = project
        self.provider = provider or get_ai_provider()

    def generate_for_recommendation(
        self,
        recommendation: SEORecommendation,
        content_type_override: Optional[str] = None
    ) -> SEOContentBrief:
        """
        Generate a structured SEO Content Brief for a given recommendation.
        Strictly verifies that recommendation belongs to self.project.
        """
        if recommendation.project_id != self.project.id:
            raise ValueError(f"Recommendation #{recommendation.id} does not belong to project #{self.project.id}.")

        # Determine target content brief type
        inferred_type = content_type_override or self._infer_content_type(recommendation)
        if inferred_type not in VALID_CONTENT_TYPES:
            inferred_type = BriefContentType.BLOG_POST

        context = self._build_brief_context(recommendation, inferred_type)
        raw_brief = self.provider.generate_content_brief(context)
        sanitized = self._validate_and_sanitize_response(raw_brief, recommendation, inferred_type)

        # Upsert content brief linked to recommendation
        existing = SEOContentBrief.objects.filter(
            project=self.project,
            recommendation=recommendation
        ).first()

        if existing:
            existing.title = sanitized['title']
            existing.target_keyword = sanitized['target_keyword']
            existing.secondary_keywords = sanitized['secondary_keywords']
            existing.search_intent = sanitized['search_intent']
            existing.target_url = sanitized['target_url']
            existing.content_type = sanitized['content_type']
            existing.recommended_title = sanitized['recommended_title']
            existing.meta_description = sanitized['meta_description']
            existing.suggested_slug = sanitized['suggested_slug']
            existing.content_angle = sanitized['content_angle']
            existing.audience = sanitized['audience']
            existing.outline = sanitized['outline']
            existing.key_points = sanitized['key_points']
            existing.internal_link_suggestions = sanitized['internal_link_suggestions']
            existing.external_link_suggestions = sanitized['external_link_suggestions']
            existing.faq_questions = sanitized['faq_questions']
            existing.entities_topics = sanitized['entities_topics']
            existing.content_length_target = sanitized['content_length_target']
            existing.generated_content = sanitized['generated_content']
            existing.save()
            return existing

        brief = SEOContentBrief.objects.create(
            project=self.project,
            recommendation=recommendation,
            title=sanitized['title'],
            target_keyword=sanitized['target_keyword'],
            secondary_keywords=sanitized['secondary_keywords'],
            search_intent=sanitized['search_intent'],
            target_url=sanitized['target_url'],
            content_type=sanitized['content_type'],
            recommended_title=sanitized['recommended_title'],
            meta_description=sanitized['meta_description'],
            suggested_slug=sanitized['suggested_slug'],
            content_angle=sanitized['content_angle'],
            audience=sanitized['audience'],
            outline=sanitized['outline'],
            key_points=sanitized['key_points'],
            internal_link_suggestions=sanitized['internal_link_suggestions'],
            external_link_suggestions=sanitized['external_link_suggestions'],
            faq_questions=sanitized['faq_questions'],
            entities_topics=sanitized['entities_topics'],
            content_length_target=sanitized['content_length_target'],
            generated_content=sanitized['generated_content'],
            status=BriefStatus.DRAFT
        )
        return brief

    def _infer_content_type(self, recommendation: SEORecommendation) -> str:
        """
        Dynamically infer best content brief type based on recommendation and insight context.
        """
        rec_type = recommendation.recommendation_type
        insight = recommendation.insight

        if rec_type == 'technical_seo' or (insight and insight.insight_type == 'technical_seo_issue'):
            return BriefContentType.TECHNICAL_IMPLEMENTATION
        elif rec_type in ['meta_title', 'meta_description', 'ctr_optimization', 'ranking_recovery', 'content_update']:
            return BriefContentType.PAGE_OPTIMIZATION
        elif rec_type in ['page_two_opportunity', 'keyword_optimization']:
            return BriefContentType.BLOG_POST
        else:
            return BriefContentType.BLOG_POST

    def _build_brief_context(self, recommendation: SEORecommendation, content_type: str) -> Dict[str, Any]:
        """
        Extract and assemble structured evidence from recommendation, insight, GSC, rankings, and audits.
        """
        insight = recommendation.insight

        target_keyword = recommendation.affected_keyword or (
            insight.related_keyword.keyword if insight and insight.related_keyword else ''
        ) or (insight.metadata.get('query') if insight and insight.metadata else '')

        target_url = recommendation.affected_url or (
            insight.related_url if insight else ''
        ) or self.project.website_url

        context: Dict[str, Any] = {
            "project_name": self.project.name,
            "project_website_url": self.project.website_url,
            "recommendation_id": recommendation.id,
            "recommendation_title": recommendation.title,
            "recommendation_summary": recommendation.summary,
            "recommendation_type": recommendation.recommendation_type,
            "recommended_action": recommendation.recommended_action,
            "priority": recommendation.priority,
            "content_type": content_type,
            "target_keyword": target_keyword,
            "target_url": target_url,
            "insight_title": insight.title if insight else "",
            "insight_type": insight.insight_type if insight else "",
            "insight_description": insight.description if insight else "",
            "metadata": insight.metadata if insight else {}
        }

        # Supplement with ranking trajectory if keyword is linked
        if insight and insight.related_keyword:
            rankings = list(
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
                for r in rankings
            ]

        # Supplement with GSC queries on the affected page/query
        if target_keyword:
            gsc_data = list(
                SearchAnalyticsData.objects.filter(
                    connection__project=self.project,
                    query__iexact=target_keyword
                ).order_by('-date')[:5].values('date', 'clicks', 'impressions', 'ctr', 'position')
            )
            if gsc_data:
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

        # Supplement with audit issues if relevant
        if rec_type_is_tech := (recommendation.recommendation_type == 'technical_seo'):
            recent_issues = list(
                AuditIssue.objects.filter(audit__project=self.project)
                .order_by('-created_at')[:3]
                .values('issue_type', 'severity', 'title', 'page_url')
            )
            if recent_issues:
                context["related_audit_issues"] = recent_issues

        return context

    def _validate_and_sanitize_response(
        self,
        raw: Dict[str, Any],
        recommendation: SEORecommendation,
        default_type: str
    ) -> Dict[str, Any]:
        """
        Validate and sanitize the raw AI dictionary ensuring clean data types and boundaries.
        """
        if not isinstance(raw, dict):
            raw = {}

        title = str(raw.get('title') or f"SEO Content Brief: {recommendation.title}").strip()[:255]
        target_keyword = str(raw.get('target_keyword') or recommendation.affected_keyword or '').strip()[:255]

        # Secondary keywords
        raw_sec = raw.get('secondary_keywords')
        secondary_keywords = [str(k).strip() for k in raw_sec if str(k).strip()] if isinstance(raw_sec, list) else []

        # Search intent
        search_intent = str(raw.get('search_intent') or 'informational').strip().lower()
        if search_intent not in VALID_INTENTS:
            search_intent = BriefSearchIntent.INFORMATIONAL

        target_url = str(raw.get('target_url') or recommendation.affected_url or '').strip()[:500]

        # Content type
        content_type = str(raw.get('content_type') or default_type).strip().lower()
        if content_type not in VALID_CONTENT_TYPES:
            content_type = default_type

        recommended_title = str(raw.get('recommended_title') or recommendation.title).strip()[:255]
        meta_description = str(raw.get('meta_description') or recommendation.summary or '').strip()
        suggested_slug = str(raw.get('suggested_slug') or '').strip()[:255]
        content_angle = str(raw.get('content_angle') or recommendation.explanation or '').strip()
        audience = str(raw.get('audience') or 'General searchers and target customers.').strip()[:255]

        # Outline sanitization
        raw_outline = raw.get('outline')
        outline = []
        if isinstance(raw_outline, list):
            for item in raw_outline:
                if isinstance(item, dict):
                    h_title = str(item.get('heading') or '').strip()
                    h_level = str(item.get('level') or 'H2').strip().upper()
                    if h_level not in ['H1', 'H2', 'H3']:
                        h_level = 'H2'
                    raw_pts = item.get('key_points')
                    pts = [str(p).strip() for p in raw_pts if str(p).strip()] if isinstance(raw_pts, list) else []
                    if h_title:
                        outline.append({
                            "heading": h_title[:255],
                            "level": h_level,
                            "key_points": pts
                        })
        if not outline:
            outline = [
                {"heading": title, "level": "H1", "key_points": ["Introduction and search intent answer."]},
                {"heading": "Core Analysis & Recommendations", "level": "H2", "key_points": ["Key actionable steps."]}
            ]

        # Key points
        raw_kp = raw.get('key_points')
        key_points = [str(p).strip() for p in raw_kp if str(p).strip()] if isinstance(raw_kp, list) else [
            recommendation.recommended_action[:200]
        ]

        # Internal link suggestions
        raw_int = raw.get('internal_link_suggestions')
        internal_links = []
        if isinstance(raw_int, list):
            for link in raw_int:
                if isinstance(link, dict) and link.get('anchor_text'):
                    internal_links.append({
                        "target_url": str(link.get('target_url') or '').strip()[:500],
                        "anchor_text": str(link.get('anchor_text') or '').strip()[:255],
                        "context": str(link.get('context') or '').strip()
                    })

        # External link suggestions
        raw_ext = raw.get('external_link_suggestions')
        external_links = []
        if isinstance(raw_ext, list):
            for link in raw_ext:
                if isinstance(link, dict) and link.get('source'):
                    external_links.append({
                        "source": str(link.get('source') or '').strip()[:255],
                        "anchor_text": str(link.get('anchor_text') or '').strip()[:255],
                        "context": str(link.get('context') or '').strip()
                    })

        # FAQ questions
        raw_faq = raw.get('faq_questions')
        faq_questions = []
        if isinstance(raw_faq, list):
            for faq in raw_faq:
                if isinstance(faq, dict) and faq.get('question'):
                    faq_questions.append({
                        "question": str(faq.get('question') or '').strip(),
                        "answer_guidance": str(faq.get('answer_guidance') or '').strip()
                    })

        # Entities / topics
        raw_ent = raw.get('entities_topics')
        entities_topics = [str(e).strip() for e in raw_ent if str(e).strip()] if isinstance(raw_ent, list) else []

        # Content length target
        try:
            content_length_target = int(raw.get('content_length_target') or 1500)
            if content_length_target < 200:
                content_length_target = 500
            elif content_length_target > 20000:
                content_length_target = 20000
        except (ValueError, TypeError):
            content_length_target = 1500

        return {
            "title": title,
            "target_keyword": target_keyword,
            "secondary_keywords": secondary_keywords,
            "search_intent": search_intent,
            "target_url": target_url,
            "content_type": content_type,
            "recommended_title": recommended_title,
            "meta_description": meta_description,
            "suggested_slug": suggested_slug,
            "content_angle": content_angle,
            "audience": audience,
            "outline": outline,
            "key_points": key_points,
            "internal_link_suggestions": internal_links,
            "external_link_suggestions": external_links,
            "faq_questions": faq_questions,
            "entities_topics": entities_topics,
            "content_length_target": content_length_target,
            "generated_content": raw
        }

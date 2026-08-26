import logging
import re
from typing import Dict, Any, Optional, Tuple
from django.utils import timezone
from django.db import transaction

from apps.projects.models import Project
from apps.seo.models import (
    SEOContentBrief,
    SEOContentDraft,
    SEORecommendation,
    SEOInsight,
    KeywordRanking,
    SearchAnalyticsData,
    AuditIssue,
    DraftStatus
)
from apps.seo.services.ai_providers import get_ai_provider

logger = logging.getLogger(__name__)


class SEOContentWriterService:
    """
    Service responsible for generating and managing SEO Content Drafts.
    Consumes SEOContentBrief and grounded performance evidence to produce
    publish-ready, highly structured SEO content drafts.
    """

    @classmethod
    def calculate_keyword_usage(
        cls,
        text_content: str,
        target_keyword: str,
        secondary_keywords: list
    ) -> Dict[str, Any]:
        """
        Calculates exact deterministic keyword occurrences and density across the generated draft.
        """
        lower_text = text_content.lower()
        total_words = max(1, len(re.findall(r'\b\w+\b', lower_text)))

        def count_phrase(phrase: str) -> int:
            if not phrase:
                return 0
            # Clean punctuation from search phrase
            cleaned = re.escape(phrase.strip().lower())
            if not cleaned:
                return 0
            matches = re.findall(rf'\b{cleaned}\b', lower_text)
            return len(matches)

        primary_count = count_phrase(target_keyword)
        primary_density_pct = round((primary_count / total_words) * 100, 2)

        secondary_breakdown = {}
        secondary_found_count = 0
        for sk in (secondary_keywords or []):
            if sk and isinstance(sk, str):
                c = count_phrase(sk)
                secondary_breakdown[sk] = c
                if c > 0:
                    secondary_found_count += 1

        total_secondary = len(secondary_keywords) if secondary_keywords else 0
        coverage_pct = round((secondary_found_count / max(1, total_secondary)) * 100, 1) if total_secondary > 0 else 100.0

        return {
            "total_words": total_words,
            "target_keyword": {
                "phrase": target_keyword,
                "occurrences": primary_count,
                "density_percent": primary_density_pct,
                "in_title": target_keyword.lower() in text_content[:150].lower() if target_keyword else False
            },
            "secondary_keywords": secondary_breakdown,
            "secondary_coverage_percent": coverage_pct,
            "secondary_covered_count": secondary_found_count,
            "secondary_total_count": total_secondary
        }

    @classmethod
    def assemble_grounded_context(cls, brief: SEOContentBrief) -> Dict[str, Any]:
        """
        Aggregates grounded context from the brief, its parent recommendation,
        and real project data (rankings, GSC metrics, audit issues).
        """
        project = brief.project
        context: Dict[str, Any] = {
            "project_name": project.name,
            "website_url": project.website_url,
            "brief_id": brief.id,
            "brief_title": brief.title,
            "content_type": brief.content_type,
            "target_keyword": brief.target_keyword,
            "secondary_keywords": brief.secondary_keywords or [],
            "search_intent": brief.search_intent,
            "target_url": brief.target_url,
            "recommended_title": brief.recommended_title,
            "meta_description": brief.meta_description,
            "suggested_slug": brief.suggested_slug,
            "content_angle": brief.content_angle,
            "audience": brief.audience,
            "outline": brief.outline or [],
            "key_points": brief.key_points or [],
            "internal_link_suggestions": brief.internal_link_suggestions or [],
            "external_link_suggestions": brief.external_link_suggestions or [],
            "faq_questions": brief.faq_questions or [],
            "entities_topics": brief.entities_topics or [],
            "content_length_target": brief.content_length_target or 1500
        }

        # 1. Parent Recommendation context if available
        rec = brief.recommendation
        if rec:
            context["recommendation_title"] = rec.title
            context["recommendation_type"] = rec.recommendation_type
            context["priority"] = rec.priority

        # 2. Latest Keyword Rankings
        if brief.target_keyword:
            rk = (
                KeywordRanking.objects.filter(
                    keyword__project=project,
                    keyword__keyword__iexact=brief.target_keyword
                )
                .order_by('-recorded_at')
                .first()
            )
            if rk:
                context["ranking_evidence"] = {
                    "position": rk.position,
                    "ranking_url": rk.ranking_url,
                    "search_engine": rk.search_engine,
                    "recorded_at": rk.recorded_at.isoformat()
                }

        # 3. Search Console Analytics
        if brief.target_keyword:
            gsc_data = (
                SearchAnalyticsData.objects.filter(
                    connection__project=project,
                    query__iexact=brief.target_keyword
                )
                .order_by('-date')
                .first()
            )
            if gsc_data:
                context["search_console_evidence"] = {
                    "clicks": gsc_data.clicks,
                    "impressions": gsc_data.impressions,
                    "ctr_percent": round(gsc_data.ctr * 100, 2),
                    "position": round(gsc_data.position, 1),
                    "date": gsc_data.date.isoformat()
                }

        # 4. Relevant Site Audit Issues
        audit_issues = (
            AuditIssue.objects.filter(
                audit__project=project,
                severity__in=['critical', 'warning']
            )
            .order_by('-created_at')[:3]
        )
        if audit_issues.exists():
            context["audit_issues_evidence"] = [
                {
                    "title": issue.title,
                    "severity": issue.severity,
                    "issue_type": issue.issue_type,
                    "page_url": issue.page_url
                }
                for issue in audit_issues
            ]

        return context

    @classmethod
    def generate_for_brief(
        cls,
        project: Project,
        brief: SEOContentBrief,
        regenerate: bool = False
    ) -> SEOContentDraft:
        """
        Synthesizes a full SEOContentDraft for the given brief using the active AI provider.
        Upserts the draft into the database to avoid uncontrolled duplicate records.
        """
        if brief.project_id != project.id:
            raise ValueError("SEO Content Brief does not belong to the specified project.")

        context = cls.assemble_grounded_context(brief)
        provider = get_ai_provider()

        logger.info(f"Generating SEO Content Draft for brief #{brief.id} ('{brief.title}') via {provider.__class__.__name__}")
        raw_result = provider.generate_content_draft(context)

        # Validate and sanitize raw AI output
        title = raw_result.get('title') or brief.recommended_title or brief.title
        meta_title = raw_result.get('meta_title') or brief.recommended_title or title
        meta_description = raw_result.get('meta_description') or brief.meta_description or ''
        suggested_slug = raw_result.get('slug') or brief.suggested_slug or ''
        introduction = raw_result.get('introduction') or ''
        sections = raw_result.get('sections') or []
        faq_section = raw_result.get('faq') or []
        internal_links = raw_result.get('internal_links') or brief.internal_link_suggestions or []
        external_links = raw_result.get('external_links') or brief.external_link_suggestions or []
        schema_json_ld = raw_result.get('schema_json_ld') or {}

        # Construct markdown content body
        body_lines = []
        body_lines.append(f"# {title}")
        body_lines.append("")
        if introduction:
            body_lines.append(introduction)
            body_lines.append("")

        for sec in sections:
            heading = sec.get('heading', '')
            level = sec.get('level', 'H2').upper()
            prefix = "###" if level == 'H3' else "##"
            body_lines.append(f"{prefix} {heading}")
            body_lines.append("")
            content = sec.get('content', '')
            if content:
                body_lines.append(content)
                body_lines.append("")

        if faq_section:
            body_lines.append("## Frequently Asked Questions")
            body_lines.append("")
            for item in faq_section:
                q = item.get('question', '')
                a = item.get('answer', '')
                body_lines.append(f"**Q: {q}**")
                body_lines.append(f"{a}")
                body_lines.append("")

        content_body = "\n".join(body_lines)
        word_count = len(re.findall(r'\b\w+\b', content_body))

        # Calculate deterministic keyword usage metrics
        keyword_usage = cls.calculate_keyword_usage(
            text_content=content_body,
            target_keyword=brief.target_keyword,
            secondary_keywords=brief.secondary_keywords or []
        )

        # Fallback schema JSON-LD if empty
        if not schema_json_ld:
            schema_type = "WebPage" if brief.content_type == 'landing_page' else "TechArticle" if brief.content_type == 'technical_implementation' else "Article"
            schema_json_ld = {
                "@context": "https://schema.org",
                "@type": schema_type,
                "headline": title,
                "description": meta_description,
                "author": {
                    "@type": "Organization",
                    "name": project.name
                }
            }
            if faq_section:
                schema_json_ld["mainEntity"] = [
                    {
                        "@type": "Question",
                        "name": f.get("question", ""),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f.get("answer", "")
                        }
                    }
                    for f in faq_section
                ]

        generation_metadata = {
            "provider": provider.__class__.__name__,
            "generated_at": timezone.now().isoformat(),
            "brief_id": brief.id,
            "recommendation_id": brief.recommendation_id,
            "content_type": brief.content_type
        }

        with transaction.atomic():
            # Upsert into SEOContentDraft
            draft = (
                SEOContentDraft.objects.filter(
                    project=project,
                    brief=brief
                )
                .first()
            )

            if draft and regenerate:
                draft.title = title
                draft.target_keyword = brief.target_keyword
                draft.secondary_keywords = brief.secondary_keywords or []
                draft.search_intent = brief.search_intent
                draft.target_url = brief.target_url
                draft.content_type = brief.content_type
                draft.introduction = introduction
                draft.content_body = content_body
                draft.outline_structure = sections
                draft.word_count = word_count
                draft.keyword_usage = keyword_usage
                draft.internal_links = internal_links
                draft.external_links = external_links
                draft.faq_section = faq_section
                draft.meta_title = meta_title
                draft.meta_description = meta_description
                draft.suggested_slug = suggested_slug
                draft.schema_json_ld = schema_json_ld
                draft.generated_content = raw_result
                draft.generation_metadata = generation_metadata
                draft.status = DraftStatus.GENERATED
                draft.save()
            elif not draft:
                draft = SEOContentDraft.objects.create(
                    project=project,
                    brief=brief,
                    recommendation=brief.recommendation,
                    insight=brief.recommendation.insight if brief.recommendation else None,
                    title=title,
                    target_keyword=brief.target_keyword,
                    secondary_keywords=brief.secondary_keywords or [],
                    search_intent=brief.search_intent,
                    target_url=brief.target_url,
                    content_type=brief.content_type,
                    introduction=introduction,
                    content_body=content_body,
                    outline_structure=sections,
                    word_count=word_count,
                    keyword_usage=keyword_usage,
                    internal_links=internal_links,
                    external_links=external_links,
                    faq_section=faq_section,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    suggested_slug=suggested_slug,
                    schema_json_ld=schema_json_ld,
                    generated_content=raw_result,
                    generation_metadata=generation_metadata,
                    status=DraftStatus.GENERATED
                )

        return draft

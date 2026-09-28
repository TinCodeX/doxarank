"""
SEO Recommendations Engine for DoxaRank (Original SRS Task).

This service deterministically inspects existing DoxaRank project findings from:
- Technical SEO Crawler (CrawlJob / CrawlPage / issues)
- Rank Tracker (Keyword / KeywordRanking / historical position changes)
- Competitor SERP Snapshots (Competitor / CompetitorSnapshot / visibility gaps)

Features:
- Deterministic, explainable rule execution without ML/LLMs.
- Clear structured output: Problem, Why it matters, Recommended action.
- Explainable priority scoring (1 - 100) based on severity, impact, and frequency.
- Idempotent generation with fingerprint-based deduplication.
- Preserves tenant isolation (project-scoped).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from django.utils import timezone
from django.db import transaction

from apps.projects.models import Project
from apps.seo.models import (
    CrawlJob,
    CrawlJobStatus,
    CrawlPage,
    Keyword,
    KeywordRanking,
    RankingResultStatus,
    Competitor,
    CompetitorSnapshot,
    Recommendation,
    RecommendationSource,
    RecommendationCategory,
    RecommendationSeverity,
    RecommendationState,
)

logger = logging.getLogger(__name__)


def calculate_recommendation_priority(
    severity: str,
    category: str,
    is_broken: bool = False,
    is_ranking_drop: bool = False,
    count_affected: int = 1,
) -> int:
    """
    Deterministic priority calculation returning an integer between 1 and 100.

    Base score by severity:
      critical: 90
      high: 70
      medium: 50
      low: 30
      info: 15

    Deterministic modifiers:
      +10 if resource is completely broken / inaccessible (HTTP 4xx/5xx)
      +8  if ranking drop or competitor directly outranking project
      +min(10, count_affected * 2) if systemic issue affecting multiple items

    Result is strictly clamped to [1, 100].
    """
    base_scores = {
        RecommendationSeverity.CRITICAL: 90,
        RecommendationSeverity.HIGH: 70,
        RecommendationSeverity.MEDIUM: 50,
        RecommendationSeverity.LOW: 30,
        RecommendationSeverity.INFO: 15,
    }
    score = base_scores.get(severity, 50)

    if is_broken:
        score += 10
    if is_ranking_drop or category == RecommendationCategory.COMPETITORS:
        score += 8
    if count_affected > 1:
        score += min(10, count_affected * 2)

    return max(1, min(100, score))


class RecommendationEngine:
    """
    Deterministic recommendation engine evaluating existing project data.
    """

    @classmethod
    def evaluate_crawler_findings(cls, project: Project) -> List[Dict[str, Any]]:
        """
        Evaluate technical crawler data from the latest completed crawl job for this project.
        """
        findings: List[Dict[str, Any]] = []

        latest_crawl = CrawlJob.objects.filter(
            project=project,
            status=CrawlJobStatus.COMPLETED
        ).order_by('-completed_at', '-id').first()

        if not latest_crawl:
            return findings

        pages = list(latest_crawl.pages.all())
        if not pages:
            return findings

        # Track title frequencies for duplicate title detection
        title_to_pages: Dict[str, List[CrawlPage]] = defaultdict(list)
        for page in pages:
            if page.title and page.title.strip():
                clean_title = page.title.strip().lower()
                title_to_pages[clean_title].append(page)

        for page in pages:
            url = page.url or ''

            # 1. Broken Internal Page (HTTP 4xx or 5xx)
            if page.is_broken or (page.status_code and page.status_code >= 400):
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.INDEXING,
                    'severity': RecommendationSeverity.CRITICAL,
                    'title': f"Fix broken internal page (HTTP {page.status_code})",
                    'description': (
                        f"Problem: The page {url} returned HTTP status {page.status_code}, indicating it is broken or missing.\n"
                        f"Why it matters: Broken pages degrade user trust, waste search engine crawl budget, and will be dropped from Google search index."
                    ),
                    'recommended_action': "Restore the missing content, correct internal links pointing to this URL, or configure a permanent 301 redirect to an active equivalent page.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.CRITICAL, RecommendationCategory.INDEXING, is_broken=True),
                    'fingerprint': f"crawler_broken:{url}",
                    'metadata': {'status_code': page.status_code, 'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 2. Missing <title> Tag
            if not page.title or not page.title.strip():
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.ON_PAGE_SEO,
                    'severity': RecommendationSeverity.HIGH,
                    'title': f"Add missing <title> tag on {url}",
                    'description': (
                        f"Problem: The page {url} is missing an HTML <title> tag.\n"
                        f"Why it matters: The title tag is one of Google's primary ranking signals and determines the clickable headline shown in SERP snippets."
                    ),
                    'recommended_action': "Add a descriptive, unique <title> tag between 50 and 60 characters containing the primary target keyword for this page.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.ON_PAGE_SEO),
                    'fingerprint': f"crawler_missing_title:{url}",
                    'metadata': {'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 3. Missing Meta Description
            if not page.meta_description or not page.meta_description.strip():
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.ON_PAGE_SEO,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Add missing meta description on {url}",
                    'description': (
                        f"Problem: The page {url} does not have a meta description specified.\n"
                        f"Why it matters: A compelling meta description increases click-through rates (CTR) from search results by clearly conveying page value."
                    ),
                    'recommended_action': "Add a concise, compelling meta description (120 to 155 characters) summarizing the page value proposition with a clear call-to-action.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.ON_PAGE_SEO),
                    'fingerprint': f"crawler_missing_meta_desc:{url}",
                    'metadata': {'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 4. Missing H1 Heading
            if page.h1_count == 0:
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.ON_PAGE_SEO,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Add primary <h1> heading to {url}",
                    'description': (
                        f"Problem: No <h1> heading tag was detected on {url}.\n"
                        f"Why it matters: The H1 heading provides top-level semantic structure for search engine crawlers and screen readers to understand the primary topic."
                    ),
                    'recommended_action': "Add exactly one semantic <h1> element prominently near the top of the main body content reflecting the page subject.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.ON_PAGE_SEO),
                    'fingerprint': f"crawler_missing_h1:{url}",
                    'metadata': {'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 5. Multiple H1 Headings
            elif page.h1_count > 1:
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.ON_PAGE_SEO,
                    'severity': RecommendationSeverity.LOW,
                    'title': f"Consolidate multiple <h1> headings on {url}",
                    'description': (
                        f"Problem: Found {page.h1_count} <h1> heading tags on {url}.\n"
                        f"Why it matters: Multiple H1 tags can dilute keyword focus and create ambiguous hierarchy for search engine crawlers."
                    ),
                    'recommended_action': "Keep a single primary <h1> heading for the page topic and convert secondary headings to semantic <h2> or <h3> tags.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.LOW, RecommendationCategory.ON_PAGE_SEO),
                    'fingerprint': f"crawler_multiple_h1:{url}",
                    'metadata': {'h1_count': page.h1_count, 'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 6. Missing Canonical URL
            if not page.canonical_url or not page.canonical_url.strip():
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.TECHNICAL_SEO,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Specify canonical URL for {url}",
                    'description': (
                        f"Problem: No <link rel=\"canonical\"> tag was found on {url}.\n"
                        f"Why it matters: Canonical tags prevent duplicate content dilution caused by URL parameters, session IDs, or http/https protocol variants."
                    ),
                    'recommended_action': f'Add a self-referential <link rel="canonical" href="{url}" /> tag within the <head> section.',
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.TECHNICAL_SEO),
                    'fingerprint': f"crawler_missing_canonical:{url}",
                    'metadata': {'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 7. Slow Page Response (> 3000ms)
            if page.is_slow or (page.response_time_ms and page.response_time_ms > 3000):
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.PERFORMANCE,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Optimize slow page load time ({page.response_time_ms:.0f}ms) on {url}",
                    'description': (
                        f"Problem: The page {url} took {page.response_time_ms:.0f}ms to respond, exceeding the 3000ms threshold.\n"
                        f"Why it matters: Server latency directly impacts Google Core Web Vitals (TTFB, LCP) and causes high user abandonment."
                    ),
                    'recommended_action': "Optimize backend queries, enable page caching / CDN edge caching, and compress unoptimized asset payloads.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.PERFORMANCE),
                    'fingerprint': f"crawler_slow_page:{url}",
                    'metadata': {'response_time_ms': page.response_time_ms, 'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 8. Images Missing Alt Attributes
            if page.images_missing_alt_count > 0:
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.CONTENT,
                    'severity': RecommendationSeverity.LOW,
                    'title': f"Add alt attributes to {page.images_missing_alt_count} image(s) on {url}",
                    'description': (
                        f"Problem: {page.images_missing_alt_count} image element(s) on {url} are missing descriptive alt text.\n"
                        f"Why it matters: Alt attributes are essential for Google Image search visibility and accessibility for visually impaired users."
                    ),
                    'recommended_action': "Add descriptive alt attributes accurately detailing what each image depicts, integrating contextual keywords where appropriate.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.LOW, RecommendationCategory.CONTENT),
                    'fingerprint': f"crawler_missing_alt:{url}",
                    'metadata': {'images_missing_alt_count': page.images_missing_alt_count, 'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

            # 9. Redirect Issues (Redirect Chains > 1 hop)
            if page.has_redirect and page.redirect_chain and len(page.redirect_chain) > 1:
                hops = len(page.redirect_chain)
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(page.id),
                    'category': RecommendationCategory.TECHNICAL_SEO,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Eliminate redirect chain ({hops} hops) for {url}",
                    'description': (
                        f"Problem: URL {url} underwent a redirect chain across {hops} intermediate URLs before reaching {page.final_url}.\n"
                        f"Why it matters: Redirect chains waste crawler budget, introduce page latency, and dilute link equity."
                    ),
                    'recommended_action': f"Update links to point directly to the destination URL ({page.final_url}) in a single 301 hop.",
                    'affected_url': url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.TECHNICAL_SEO),
                    'fingerprint': f"crawler_redirect_chain:{url}",
                    'metadata': {'hops': hops, 'chain': page.redirect_chain, 'crawl_page_id': page.id, 'crawl_job_id': latest_crawl.id},
                })

        # 10. Duplicate Title Detection (Grouped across multiple pages)
        for clean_title, dup_pages in title_to_pages.items():
            if len(dup_pages) > 1:
                dup_urls = [p.url for p in dup_pages]
                first_url = dup_urls[0]
                findings.append({
                    'source_type': RecommendationSource.CRAWLER,
                    'source_id': str(dup_pages[0].id),
                    'category': RecommendationCategory.ON_PAGE_SEO,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Resolve duplicate <title> across {len(dup_pages)} pages",
                    'description': (
                        f"Problem: The title '{dup_pages[0].title}' is duplicated across {len(dup_pages)} distinct pages: {', '.join(dup_urls[:3])}{'...' if len(dup_urls) > 3 else ''}.\n"
                        f"Why it matters: Duplicate titles create internal keyword cannibalization and force search engines to guess which page to rank."
                    ),
                    'recommended_action': "Provide unique, context-specific titles for each page reflecting its distinctive content and purpose.",
                    'affected_url': first_url,
                    'affected_keyword': '',
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.ON_PAGE_SEO, count_affected=len(dup_pages)),
                    'fingerprint': f"crawler_duplicate_title:{clean_title[:80]}",
                    'metadata': {'duplicate_urls': dup_urls, 'count': len(dup_pages), 'title': dup_pages[0].title, 'crawl_job_id': latest_crawl.id},
                })

        return findings

    @classmethod
    def evaluate_rank_tracker_findings(cls, project: Project) -> List[Dict[str, Any]]:
        """
        Evaluate ranking data across all active tracked keywords for the project.
        """
        findings: List[Dict[str, Any]] = []
        active_keywords = project.keywords.filter(is_active=True)

        for kw in active_keywords:
            rankings = list(kw.rankings.order_by('-recorded_at', '-id')[:2])
            if not rankings:
                continue

            latest = rankings[0]
            previous = rankings[1] if len(rankings) > 1 else None

            # 1. Keyword Not Found in Top 100
            if latest.result_status == RankingResultStatus.NOT_FOUND or latest.position is None:
                findings.append({
                    'source_type': RecommendationSource.RANK_TRACKER,
                    'source_id': str(kw.id),
                    'category': RecommendationCategory.RANKINGS,
                    'severity': RecommendationSeverity.HIGH,
                    'title': f"Target keyword not ranking in Top 100: \"{kw.keyword}\"",
                    'description': (
                        f"Problem: The tracked keyword \"{kw.keyword}\" does not appear in the top 100 Google Ethiopia search results.\n"
                        f"Why it matters: Target keywords outside the top 100 receive zero organic impressions and organic search traffic."
                    ),
                    'recommended_action': f"Create or optimize a dedicated landing page targeting \"{kw.keyword}\", improve internal linking, and ensure high content relevance.",
                    'affected_url': project.website_url,
                    'affected_keyword': kw.keyword,
                    'priority': calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.RANKINGS),
                    'fingerprint': f"rank_not_found:{kw.id}",
                    'metadata': {'keyword_id': kw.id, 'search_domain': kw.search_domain, 'language': kw.language},
                })

            # 2. Significant Ranking Decline (dropped by >= 3 positions)
            elif previous and latest.position and previous.position and (latest.position - previous.position >= 3):
                drop = latest.position - previous.position
                findings.append({
                    'source_type': RecommendationSource.RANK_TRACKER,
                    'source_id': str(kw.id),
                    'category': RecommendationCategory.RANKINGS,
                    'severity': RecommendationSeverity.HIGH,
                    'title': f"Ranking decline for \"{kw.keyword}\" (dropped {drop} positions to #{latest.position})",
                    'description': (
                        f"Problem: Ranking for \"{kw.keyword}\" dropped from #{previous.position} to #{latest.position} (loss of {drop} positions).\n"
                        f"Why it matters: Rapid ranking declines signal emerging competitor movement, algorithm updates, or content freshness degradation."
                    ),
                    'recommended_action': f"Audit the ranking page ({latest.ranking_url or project.website_url}), refresh outdated information, verify technical health, and review competitors that gained positions.",
                    'affected_url': latest.ranking_url or project.website_url,
                    'affected_keyword': kw.keyword,
                    'priority': calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.RANKINGS, is_ranking_drop=True),
                    'fingerprint': f"rank_decline:{kw.id}",
                    'metadata': {'keyword_id': kw.id, 'previous_position': previous.position, 'current_position': latest.position, 'drop': drop},
                })

            # 3. Striking Distance Opportunity (Page 2: positions 11 to 20)
            elif latest.position and 11 <= latest.position <= 20:
                findings.append({
                    'source_type': RecommendationSource.RANK_TRACKER,
                    'source_id': str(kw.id),
                    'category': RecommendationCategory.RANKINGS,
                    'severity': RecommendationSeverity.MEDIUM,
                    'title': f"Striking distance opportunity: \"{kw.keyword}\" at #{latest.position}",
                    'description': (
                        f"Problem: \"{kw.keyword}\" is ranking at #{latest.position} on Page 2 of Google Ethiopia results.\n"
                        f"Why it matters: Page 2 results are within striking distance of Page 1 where over 90% of all organic clicks occur."
                    ),
                    'recommended_action': f"Add targeted internal links with descriptive anchor text to {latest.ranking_url or 'the landing page'} and expand topic depth to break into Page 1.",
                    'affected_url': latest.ranking_url or project.website_url,
                    'affected_keyword': kw.keyword,
                    'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.RANKINGS),
                    'fingerprint': f"rank_page_two:{kw.id}",
                    'metadata': {'keyword_id': kw.id, 'position': latest.position},
                })

            # 4. Low Ranking Position (> 20)
            elif latest.position and latest.position > 20:
                findings.append({
                    'source_type': RecommendationSource.RANK_TRACKER,
                    'source_id': str(kw.id),
                    'category': RecommendationCategory.RANKINGS,
                    'severity': RecommendationSeverity.LOW,
                    'title': f"Improve low ranking position (#{latest.position}) for \"{kw.keyword}\"",
                    'description': (
                        f"Problem: \"{kw.keyword}\" is currently ranking at position #{latest.position} in Google Ethiopia.\n"
                        f"Why it matters: Positions beyond Page 2 generate negligible search traffic and indicate competitors have stronger topical authority."
                    ),
                    'recommended_action': "Review top-ranking SERP competitors, optimize headings and body copy for search intent, and earn authoritative backlinks.",
                    'affected_url': latest.ranking_url or project.website_url,
                    'affected_keyword': kw.keyword,
                    'priority': calculate_recommendation_priority(RecommendationSeverity.LOW, RecommendationCategory.RANKINGS),
                    'fingerprint': f"rank_low_position:{kw.id}",
                    'metadata': {'keyword_id': kw.id, 'position': latest.position},
                })

        return findings

    @classmethod
    def evaluate_competitor_findings(cls, project: Project) -> List[Dict[str, Any]]:
        """
        Evaluate competitor snapshot observations against project rankings for tracked keywords.
        """
        findings: List[Dict[str, Any]] = []
        active_competitors = list(project.competitors.filter(is_active=True))
        if not active_competitors:
            return findings

        active_keywords = list(project.keywords.filter(is_active=True))

        for kw in active_keywords:
            # Get latest project ranking for this keyword
            project_ranking = kw.rankings.order_by('-recorded_at', '-id').first()
            project_pos = project_ranking.position if (project_ranking and project_ranking.result_status == RankingResultStatus.FOUND) else None

            for comp in active_competitors:
                latest_comp_snap = CompetitorSnapshot.objects.filter(
                    competitor=comp,
                    keyword=kw
                ).order_by('-recorded_at', '-id').first()

                if not latest_comp_snap:
                    continue

                comp_pos = latest_comp_snap.position if latest_comp_snap.result_status == RankingResultStatus.FOUND else None

                # 1. Competitor is found while project is NOT found in top 100
                if comp_pos is not None and project_pos is None:
                    findings.append({
                        'source_type': RecommendationSource.COMPETITOR_SNAPSHOT,
                        'source_id': str(latest_comp_snap.id),
                        'category': RecommendationCategory.COMPETITORS,
                        'severity': RecommendationSeverity.HIGH,
                        'title': f"Competitor {comp.domain} ranks (#{comp_pos}) while your site is unranked for \"{kw.keyword}\"",
                        'description': (
                            f"Problem: Competitor {comp.domain} is ranking at #{comp_pos} for \"{kw.keyword}\", while your website does not appear in the top 100.\n"
                            f"Why it matters: Competitors are capturing search volume and customer leads on high-intent target keywords where you have no visibility."
                        ),
                        'recommended_action': f"Inspect competitor URL ({latest_comp_snap.ranking_url or comp.domain}) to analyze their content structure, keyword density, and search intent alignment.",
                        'affected_url': project.website_url,
                        'affected_keyword': kw.keyword,
                        'priority': calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.COMPETITORS),
                        'fingerprint': f"comp_proj_not_found:{comp.id}:{kw.id}",
                        'metadata': {'competitor_id': comp.id, 'competitor_domain': comp.domain, 'competitor_position': comp_pos, 'keyword_id': kw.id},
                    })

                # 2. Competitor outranks project website
                elif comp_pos is not None and project_pos is not None and comp_pos < project_pos:
                    diff = project_pos - comp_pos
                    findings.append({
                        'source_type': RecommendationSource.COMPETITOR_SNAPSHOT,
                        'source_id': str(latest_comp_snap.id),
                        'category': RecommendationCategory.COMPETITORS,
                        'severity': RecommendationSeverity.HIGH,
                        'title': f"{comp.domain} (#{comp_pos}) outranks your website (#{project_pos}) for \"{kw.keyword}\"",
                        'description': (
                            f"Problem: Competitor {comp.domain} is ranking {diff} positions ahead of your website for \"{kw.keyword}\".\n"
                            f"Why it matters: Search results higher up the page capture a disproportionately larger share of total organic clicks."
                        ),
                        'recommended_action': f"Compare your ranking page ({project_ranking.ranking_url or project.website_url}) against {latest_comp_snap.ranking_url or comp.domain} to enhance depth, speed, and topical completeness.",
                        'affected_url': project_ranking.ranking_url or project.website_url,
                        'affected_keyword': kw.keyword,
                        'priority': calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.COMPETITORS),
                        'fingerprint': f"comp_outranks:{comp.id}:{kw.id}",
                        'metadata': {'competitor_id': comp.id, 'competitor_domain': comp.domain, 'competitor_position': comp_pos, 'project_position': project_pos, 'keyword_id': kw.id},
                    })

                # 3. Competitor holds Top 3 position (independent dominance check)
                if comp_pos is not None and comp_pos <= 3 and (project_pos is None or project_pos > 3):
                    findings.append({
                        'source_type': RecommendationSource.COMPETITOR_SNAPSHOT,
                        'source_id': str(latest_comp_snap.id),
                        'category': RecommendationCategory.COMPETITORS,
                        'severity': RecommendationSeverity.MEDIUM,
                        'title': f"{comp.domain} holds dominant Top 3 rank (#{comp_pos}) for \"{kw.keyword}\"",
                        'description': (
                            f"Problem: Competitor {comp.domain} holds a top-3 ranking (#{comp_pos}) on Google Ethiopia for \"{kw.keyword}\".\n"
                            f"Why it matters: Top 3 listings capture over 50% of all user clicks for that search query."
                        ),
                        'recommended_action': f"Audit competitor's snippet title and structure to understand why Google favors their page for this query.",
                        'affected_url': project.website_url,
                        'affected_keyword': kw.keyword,
                        'priority': calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.COMPETITORS),
                        'fingerprint': f"comp_top_three:{comp.id}:{kw.id}",
                        'metadata': {'competitor_id': comp.id, 'competitor_domain': comp.domain, 'competitor_position': comp_pos, 'keyword_id': kw.id},
                    })

        return findings

    @classmethod
    def generate_project_recommendations(cls, project: Project) -> List[Recommendation]:
        """
        Generate, deduplicate, and persist recommendations for a project.

        Guarantees:
        - Deterministic generation across Crawler, Rank Tracker, and Competitor Snapshots.
        - Deduplication: Equivalent open/acknowledged recommendations are updated without duplication.
        - Idempotency: Safe to run repeatedly; multiple runs do not create duplicate records.
        """
        findings: List[Dict[str, Any]] = []

        # 1. Gather findings across all supported subsystems
        findings.extend(cls.evaluate_crawler_findings(project))
        findings.extend(cls.evaluate_rank_tracker_findings(project))
        findings.extend(cls.evaluate_competitor_findings(project))

        generated_recommendations: List[Recommendation] = []

        with transaction.atomic():
            for item in findings:
                fingerprint = item['fingerprint']

                # Look for existing active recommendation
                existing = Recommendation.objects.filter(
                    project=project,
                    fingerprint=fingerprint,
                    status__in=[RecommendationState.OPEN, RecommendationState.ACKNOWLEDGED]
                ).first()

                if existing:
                    # Update fields that may have evolved (priority, description, metadata)
                    existing.priority = item['priority']
                    existing.severity = item['severity']
                    existing.title = item['title']
                    existing.description = item['description']
                    existing.recommended_action = item['recommended_action']
                    existing.affected_url = item.get('affected_url', '')
                    existing.affected_keyword = item.get('affected_keyword', '')
                    existing.metadata = item.get('metadata', {})
                    existing.save(update_fields=[
                        'priority', 'severity', 'title', 'description',
                        'recommended_action', 'affected_url', 'affected_keyword',
                        'metadata', 'updated_at'
                    ])
                    generated_recommendations.append(existing)
                else:
                    # Create new open recommendation
                    rec = Recommendation.objects.create(
                        project=project,
                        source_type=item['source_type'],
                        source_id=item.get('source_id', ''),
                        category=item['category'],
                        severity=item['severity'],
                        title=item['title'],
                        description=item['description'],
                        recommended_action=item['recommended_action'],
                        affected_url=item.get('affected_url', ''),
                        affected_keyword=item.get('affected_keyword', ''),
                        status=RecommendationState.OPEN,
                        priority=item['priority'],
                        fingerprint=fingerprint,
                        metadata=item.get('metadata', {}),
                    )
                    generated_recommendations.append(rec)

        logger.info(
            f"[RecommendationEngine] Project #{project.id} ({project.name}): processed {len(findings)} findings, "
            f"active recommendations: {len(generated_recommendations)}"
        )
        return generated_recommendations

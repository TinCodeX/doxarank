import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DoxaRank's Senior AI SEO Specialist Agent.
Your objective is to analyze structured, deterministic SEO insights derived from search performance data, site audits, and rank tracking, and generate actionable, evidence-based SEO recommendations for webmasters and marketers.

CRITICAL SAFETY & QUALITY GUIDELINES:
1. NEVER invent or fabricate search analytics metrics (clicks, impressions, CTR, position), keywords, or URLs. Use ONLY the data provided in the insight context.
2. NEVER guarantee search engine rankings or promise definite traffic increases. Use realistic, evidence-grounded language (e.g. "aims to improve", "can help boost relevance").
3. DO NOT claim that you have executed or modified any website files. Clearly present all suggestions as recommendations for human review.
4. Output MUST be valid JSON adhering strictly to the requested schema.

SCHEMA:
{
  "title": "<Concise recommendation headline>",
  "summary": "<High-level executive summary of the issue and why action is needed>",
  "explanation": "<In-depth analytical explanation detailing observed metrics, search behavior, and underlying cause>",
  "priority": "critical" | "high" | "medium" | "low",
  "recommendation_type": "meta_title" | "meta_description" | "content_update" | "keyword_optimization" | "internal_linking" | "technical_seo" | "ranking_recovery" | "ctr_optimization" | "page_two_opportunity" | "general_seo",
  "recommended_action": "<Concrete, step-by-step developer / marketer execution instructions>",
  "expected_impact": "<Realistic search visibility or engagement benefits without false guarantees>",
  "affected_url": "<Target landing page URL if present, otherwise empty string>",
  "affected_keyword": "<Target search query if present, otherwise empty string>",
  "generated_content": {
    "proposed_title": "<Optional alternative title tag>",
    "proposed_meta_description": "<Optional meta description copy between 140-160 chars>",
    "action_checklist": ["<Step 1>", "<Step 2>", "<Step 3>"],
    "content_suggestions": "<Optional markdown or copy recommendations>"
  }
}
"""


class BaseAIProvider(ABC):
    """Abstract base class for AI LLM providers."""

    @abstractmethod
    def generate_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured recommendation JSON based on insight context."""
        pass


class MockAIProvider(BaseAIProvider):
    """
    Deterministic Mock AI Provider for automated tests, offline environments,
    and fallback operation without third-party API dependencies.
    """

    def generate_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        insight_type = context.get('insight_type', 'general_seo')
        title = context.get('title', 'SEO Recommendation')
        severity = context.get('severity', 'info')
        keyword = context.get('keyword') or ''
        url = context.get('url') or ''
        metadata = context.get('metadata') or {}

        # Default priority mapping from insight severity
        priority_map = {
            'critical': 'critical',
            'warning': 'high',
            'opportunity': 'medium',
            'info': 'low'
        }
        priority = priority_map.get(severity, 'high')

        if insight_type == 'ranking_drop':
            prev_pos = metadata.get('previous_position', 'previous')
            curr_pos = metadata.get('current_position', 'current')
            drop = metadata.get('position_drop', '')
            return {
                "title": f"Execute Ranking Recovery Plan for \"{keyword}\"",
                "summary": f"Keyword \"{keyword}\" dropped from position #{prev_pos} to #{curr_pos}. Urgent on-page and technical verification is required to halt traffic loss.",
                "explanation": f"Observed position drop of {drop} positions suggests search intent divergence, competitor content updates, or loss of internal/external authority for {url or 'the landing page'}.",
                "priority": "critical" if severity == 'critical' else "high",
                "recommendation_type": "ranking_recovery",
                "recommended_action": (
                    f"1. Audit the landing page content against top 3 currently ranking competitors for '{keyword}'.\n"
                    f"2. Ensure primary search intent is answered in the first viewport with clear H1/H2 hierarchy.\n"
                    f"3. Verify that canonical and hreflang tags have not changed.\n"
                    f"4. Add 2-3 contextual internal links from high-authority pages on the site."
                ),
                "expected_impact": "Stabilizes ranking decline and helps restore original page 1 position over subsequent crawl cycles.",
                "affected_url": url,
                "affected_keyword": keyword,
                "generated_content": {
                    "proposed_title": f"{keyword.title()} | Comprehensive Guide & Solutions" if keyword else "",
                    "proposed_meta_description": f"Discover top insights and actionable solutions for {keyword}. Explore comprehensive expert analysis and resources." if keyword else "",
                    "action_checklist": [
                        "Review recent page edits or technical changes",
                        "Inspect SERP features and competitor ranking shifts",
                        "Reinforce on-page topical authority and internal linking",
                        "Re-request indexing in Google Search Console"
                    ],
                    "content_suggestions": f"Expand section answering search queries related to '{keyword}'."
                }
            }

        elif insight_type == 'page_two_keyword':
            curr_pos = metadata.get('current_position', '11-20')
            return {
                "title": f"Push \"{keyword}\" from Page 2 (#{curr_pos}) to Page 1",
                "summary": f"Keyword \"{keyword}\" is currently ranking at #{curr_pos}. Page 2 keywords have established topical baseline and offer high ROI for targeted optimization.",
                "explanation": f"Google already recognizes {url or 'the site'} as relevant for '{keyword}'. A modest increase in content depth, on-page headers, and internal link equity can push this into the top 10 search results.",
                "priority": "high",
                "recommendation_type": "page_two_opportunity",
                "recommended_action": (
                    f"1. Update H1 and H2 subheadings to incorporate '{keyword}' naturally.\n"
                    f"2. Add a dedicated FAQ or practical takeaway section addressing user questions.\n"
                    f"3. Build internal links with exact and partial-match anchor text from related blog posts.\n"
                    f"4. Ensure page speed LCP is under 2.5 seconds."
                ),
                "expected_impact": "Moving from page 2 to page 1 typically yields a significant increase in organic click-through rate.",
                "affected_url": url,
                "affected_keyword": keyword,
                "generated_content": {
                    "proposed_title": f"{keyword.title()} — Complete 2026 Overview",
                    "proposed_meta_description": f"Looking for {keyword}? Learn everything you need to know with our comprehensive guide, key tips, and expert analysis.",
                    "action_checklist": [
                        "Incorporate keyword variations into H2/H3 headings",
                        "Add 2 high-relevance internal links",
                        "Improve page load speed and core web vitals",
                        "Add structured data markup (FAQPage / Article)"
                    ],
                    "content_suggestions": f"Add an FAQ section addressing high-volume long-tail queries related to '{keyword}'."
                }
            }

        elif insight_type in ['high_impressions_low_ctr', 'low_ctr']:
            imp = metadata.get('impressions', 'high')
            clicks = metadata.get('clicks', 'low')
            ctr = metadata.get('ctr_percent', '<3')
            query = metadata.get('query') or keyword
            return {
                "title": f"Optimize SERP Snippet for \"{query}\" ({imp} Impressions, {ctr}% CTR)",
                "summary": f"Query \"{query}\" generates {imp} search impressions but only {clicks} clicks. High visibility with low CTR indicates snippet optimization opportunity.",
                "explanation": "Searchers frequently see your listing in search results but choose competing snippets due to uncompelling meta titles, vague descriptions, or lack of clear value proposition.",
                "priority": "medium",
                "recommendation_type": "ctr_optimization",
                "recommended_action": (
                    f"1. Replace generic meta title with a specific, benefit-driven headline.\n"
                    f"2. Write an actionable meta description (140-155 characters) with a clear call-to-action.\n"
                    f"3. Implement Rich Snippets (Review, FAQ, or HowTo schema) where applicable.\n"
                    f"4. Monitor CTR in Search Console over the next 14 days."
                ),
                "expected_impact": "Improving CTR by even 1-2% on high-impression queries can generate substantial incremental organic traffic without needing higher positions.",
                "affected_url": url,
                "affected_keyword": query,
                "generated_content": {
                    "proposed_title": f"{query.title()} — Proven Tips & Full Guide",
                    "proposed_meta_description": f"Discover how to master {query} with our step-by-step guide. Fast, practical insights and best practices updated for 2026.",
                    "action_checklist": [
                        "Update HTML title tag in CMS",
                        "Update meta description tag in CMS",
                        "Verify snippet appearance using Google Rich Results test",
                        "Inspect Search Console performance in 14 days"
                    ],
                    "content_suggestions": "Add an action-oriented trigger word (e.g. 'Guide', 'Best', 'Review', 'How-To') in the first 30 characters of the title."
                }
            }

        elif insight_type == 'technical_seo_issue':
            issue_type = metadata.get('issue_type', 'technical_issue')
            return {
                "title": f"Resolve Technical SEO Bottleneck: {title}",
                "summary": f"Technical audit detected {severity.upper()} issue: {title}. Resolving this unblocks crawl efficiency and search indexation.",
                "explanation": f"Search engine bots encounter obstacles when processing pages affected by '{issue_type}', potentially degrading page rank distribution and mobile usability.",
                "priority": "critical" if severity == 'critical' else "high",
                "recommendation_type": "technical_seo",
                "recommended_action": (
                    f"1. Inspect affected URL: {url or 'site-wide templates'}.\n"
                    f"2. Apply standard technical SEO remedy for {issue_type}.\n"
                    f"3. Validate clean HTTP 200 response code and valid structured HTML.\n"
                    f"4. Run a fresh site audit in DoxaRank to confirm resolution."
                ),
                "expected_impact": "Restores full crawl budget efficiency and prevents search engines from demoting affected landing pages.",
                "affected_url": url,
                "affected_keyword": keyword,
                "generated_content": {
                    "action_checklist": [
                        f"Locate affected template or page at {url or 'CMS settings'}",
                        "Apply recommended HTML/server configuration fix",
                        "Test via Google Mobile-Friendly and PageSpeed tools",
                        "Re-run DoxaRank site audit to verify clean health score"
                    ],
                    "content_suggestions": "Ensure all required metadata and structured data tags are dynamically populated by CMS."
                }
            }

        elif insight_type in ['declining_clicks', 'declining_impressions']:
            metric = metadata.get('metric', 'traffic')
            pct = metadata.get('decline_percent', '15+')
            return {
                "title": f"Mitigate Organic Search {metric.title()} Decline (-{pct}%)",
                "summary": f"Overall organic search {metric} declined by {pct}%. A comprehensive audit of top traffic-driving pages and search queries is advised.",
                "explanation": f"A site-wide {metric} decline across observation periods points to either seasonal fluctuations, Google core algorithm shifts, or technical indexing issues on key landing pages.",
                "priority": "critical" if severity == 'critical' else "high",
                "recommendation_type": "ranking_recovery",
                "recommended_action": (
                    "1. Cross-reference decline dates with known Google Search algorithm updates.\n"
                    "2. Identify the top 5 lost queries in Google Search Console.\n"
                    "3. Perform content freshness refreshes on affected top landing pages.\n"
                    "4. Verify that robots.txt and sitemaps are not blocking crawl paths."
                ),
                "expected_impact": "Identifies root causes of traffic loss and prevents further erosion of search visibility.",
                "affected_url": url,
                "affected_keyword": keyword,
                "generated_content": {
                    "action_checklist": [
                        "Isolate top pages and queries with largest negative delta",
                        "Audit page freshness and competitors who gained rank",
                        "Review backlink profile for recently lost high-value links",
                        "Submit updated XML sitemaps in Search Console"
                    ]
                }
            }

        # General fallback
        return {
            "title": f"Optimize Strategy for: {title}",
            "summary": f"Actionable recommendation addressing {severity} insight on {keyword or url or 'project'}.",
            "explanation": "Continuous SEO optimization across content, technical foundations, and search intent alignment maintains competitive search advantages.",
            "priority": priority,
            "recommendation_type": "general_seo",
            "recommended_action": "Review the insight findings, update corresponding on-page elements or technical configurations, and monitor ranking progress.",
            "expected_impact": "Improves overall domain authority, keyword relevance, and organic visibility.",
            "affected_url": url,
            "affected_keyword": keyword,
            "generated_content": {
                "action_checklist": [
                    "Review underlying insight metadata",
                    "Execute recommended on-page optimizations",
                    "Verify indexation and tracking status in DoxaRank"
                ]
            }
        }


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI GPT Provider implementing structured JSON output via API.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = 'gpt-4o-mini'):
        self.api_key = api_key or getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')
        self.model = model

    def generate_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockAIProvider.")
            return MockAIProvider().generate_recommendation(context)

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Generate a structured SEO recommendation for the following insight context:\n{json.dumps(context, indent=2)}"
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3
            }

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                content_str = res_data['choices'][0]['message']['content']
                parsed = json.loads(content_str)
                return parsed

        except Exception as e:
            logger.error(f"OpenAI API invocation failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider().generate_recommendation(context)


def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """
    Factory function returning the configured AI Provider instance.
    """
    if provider_type == 'mock':
        return MockAIProvider()

    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')
    if api_key and provider_type != 'mock':
        return OpenAIProvider(api_key=api_key)

    return MockAIProvider()

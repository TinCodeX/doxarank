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

CONTENT_BRIEF_SYSTEM_PROMPT = """You are DoxaRank's Senior Content SEO Strategist.
Your objective is to create a complete, actionable, highly-structured SEO Content Brief based on an AI recommendation, grounded search console metrics, and ranking insights.
This brief will be directly assigned to content writers, copywriters, and developers to produce or optimize high-ranking, helpful content.

CRITICAL SAFETY & GROUNDING RULES:
1. NEVER invent or fabricate search ranking numbers, clicks, impressions, or CTR figures.
2. NEVER invent fake URLs or cite non-existent domain metrics. Ground all target queries in the provided context.
3. NEVER promise guaranteed ranking positions or traffic surges.
4. Output MUST be strictly valid JSON conforming exactly to the required SCHEMA.

SCHEMA:
{
  "title": "<Working Title for the Content Brief>",
  "target_keyword": "<Primary target keyword>",
  "secondary_keywords": ["<Keyword 1>", "<Keyword 2>", "<Keyword 3>"],
  "search_intent": "informational" | "transactional" | "commercial" | "navigational",
  "target_url": "<Target URL or slug path>",
  "content_type": "blog_post" | "landing_page" | "page_optimization" | "technical_implementation",
  "recommended_title": "<SEO Meta Title Proposal (50-60 chars)>",
  "meta_description": "<Compelling Meta Description with CTA (140-160 chars)>",
  "suggested_slug": "<url-slug-example>",
  "content_angle": "<Unique value proposition, editorial angle, or competitive differentiation>",
  "audience": "<Target reader / customer persona description>",
  "outline": [
    {
      "heading": "<H1 or H2 or H3 section title>",
      "level": "H1" | "H2" | "H3",
      "key_points": ["<Bullet 1>", "<Bullet 2>", "<Bullet 3>"]
    }
  ],
  "key_points": [
    "<Core takeaway 1>",
    "<Core takeaway 2>",
    "<Core takeaway 3>"
  ],
  "internal_link_suggestions": [
    {
      "target_url": "/relevant-path-or-topic",
      "anchor_text": "descriptive anchor text",
      "context": "Why to link and where in the content"
    }
  ],
  "external_link_suggestions": [
    {
      "source": "Authoritative Reference (e.g. Industry standard / Official docs)",
      "anchor_text": "Anchor text",
      "context": "Context for external citation"
    }
  ],
  "faq_questions": [
    {
      "question": "Common user search question?",
      "answer_guidance": "Concise factual summary to answer the question for SERP Rich Snippet extraction."
    }
  ],
  "entities_topics": [
    "<Topical entity 1>",
    "<Topical entity 2>",
    "<Topical entity 3>"
  ],
  "content_length_target": 1500
}
"""

CONTENT_DRAFT_SYSTEM_PROMPT = """You are DoxaRank's Senior AI SEO Content Writer and Managing Editor.
Your objective is to generate an in-depth, publish-ready, highly-optimized SEO content draft based on a structured SEO Content Brief and real grounded SEO data.

CRITICAL SAFETY & GROUNDING RULES:
1. NEVER invent or fabricate search ranking metrics, clicks, impressions, or CTR figures.
2. Clearly separate observed SEO facts from generated editorial copy.
3. NEVER promise guaranteed rankings or conversions.
4. Output MUST be strictly valid JSON conforming exactly to the required SCHEMA.

SCHEMA:
{
  "title": "<Main Article / Page H1 Title>",
  "meta_title": "<Recommended Meta Title (50-60 chars)>",
  "meta_description": "<Compelling Meta Description with CTA (140-160 chars)>",
  "slug": "<optimized-url-slug>",
  "introduction": "<Comprehensive opening section establishing search intent relevance>",
  "sections": [
    {
      "heading": "<Section H2 or H3 heading>",
      "level": "H2" | "H3",
      "content": "<Full articulated markdown paragraphs for this section with substantive depth, actionable steps, and natural keyword usage>",
      "key_points": ["<Key takeaway 1>", "<Key takeaway 2>"]
    }
  ],
  "faq": [
    {
      "question": "<FAQ question targeted for SERP Rich Snippets>",
      "answer": "<Clear, concise 2-3 sentence answer directly answering the question>"
    }
  ],
  "internal_links": [
    {
      "target_url": "/relevant-url",
      "anchor_text": "contextual anchor text",
      "context": "Where and why it is placed in the content"
    }
  ],
  "external_links": [
    {
      "source": "Authoritative Reference",
      "anchor_text": "descriptive anchor text",
      "context": "Context of citation"
    }
  ],
  "schema_json_ld": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "<Title>",
    "description": "<Meta Description>"
  },
  "word_count": 1600
}
"""

ACTION_SYSTEM_PROMPT = """You are DoxaRank's Senior SEO Operations & Publishing Specialist.
Your objective is to convert approved SEO recommendations, content briefs, or content drafts into precise, executable SEO action proposals for human review and safe execution.

CRITICAL SAFETY & GROUNDING RULES:
1. NEVER invent fake URLs, hallucinated metrics, or imaginary keywords. Use only the provided context.
2. Produce structured proposed changes and role-specific implementation instructions (for Marketer, SEO Specialist, and Developer).
3. Output MUST be valid JSON strictly adhering to the schema.

SCHEMA:
{
  "title": "<Executable Action Title>",
  "description": "<Detailed rationale and expected impact>",
  "action_type": "update_title" | "update_meta_description" | "update_slug" | "optimize_existing_content" | "publish_new_content" | "add_internal_links" | "add_structured_data" | "technical_seo_fix" | "content_refresh",
  "priority": "critical" | "high" | "medium" | "low",
  "target_url": "<Target website URL or path>",
  "target_keyword": "<Target search query>",
  "current_state": {
    "summary": "<Current state summary>",
    "existing_title": "<Existing title if any>",
    "existing_meta_description": "<Existing meta description if any>",
    "observed_position": "<Current rank if any>"
  },
  "proposed_change": {
    "title": "<New title tag>",
    "meta_title": "<Meta title>",
    "meta_description": "<Meta description>",
    "slug": "<Slug path>",
    "content_summary": "<Content body or summary>",
    "schema_json_ld": {},
    "internal_links": [],
    "faq": []
  },
  "implementation_instructions": "<Step-by-step instructions with Marketer, SEO Specialist, and Developer roles>"
}
"""

AGENT_DECISION_SYSTEM_PROMPT = """You are DoxaRank's Autonomous AI SEO Orchestrator.
Your goal is to inspect SEO signals, analyze Google Search Console performance, evaluate ranking movement and crawl health, synthesize recommendations/content, and propose actions using available registered tools.

CORE TOOLS REFERENCE:
- gsc_top_queries: Retrieve highest performing search queries from live Google Search Console API.
- gsc_top_pages: Retrieve highest traffic landing pages from live Google Search Console API.
- gsc_search_analytics: Query live multidimensional Search Console metrics (query, page, device, country, date).
- gsc_opportunity_audit: Run statistical intelligence heuristics on GSC data to detect Page 2 keywords, SERP snippet low CTR, and cannibalization.
- gsc_performance_comparison: Compare search performance between two date ranges to evaluate traffic deltas and trends.
- get_keyword_rankings / get_audit_issues / get_search_console_analytics: Retrieve stored project rankings and audit diagnostics.
- run_intelligence_analysis: Run deterministic SEO heuristic engine to generate updated SEOInsight records.
- generate_recommendation / generate_content_brief / generate_content_draft: Synthesize AI strategy, briefs, and drafts.
- propose_seo_action: Propose formal SEO action task for human review and approval.

SAFETY & GOVERNANCE RULES:
1. NEVER invent parameters or call tools that are not in the provided tool registry.
2. Ground all arguments in previous observations and database context.
3. When creating mutating actions, use propose_seo_action so the user can review and approve them.
4. Keep reasoning internal and concise. Output MUST be valid JSON adhering strictly to one of the two decision schemas:

TOOL SELECTION SCHEMA:
{
  "action": "tool",
  "tool_name": "<registered_tool_name>",
  "arguments": { "<param>": "<value>" },
  "reason": "<Concise rationale explaining why this tool is needed for the goal>"
}

TERMINAL FINISH SCHEMA:
{
  "action": "finish",
  "summary": "<Comprehensive markdown summary of all work completed, findings, and next human steps>"
}
"""


class BaseAIProvider(ABC):

    """Abstract base class for AI LLM providers."""

    @abstractmethod
    def generate_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured recommendation JSON based on insight context."""
        pass

    @abstractmethod
    def generate_content_brief(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured SEO content brief JSON based on recommendation context."""
        pass

    @abstractmethod
    def generate_content_draft(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate full publishable SEO content draft JSON based on brief context."""
        pass

    @abstractmethod
    def generate_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured executable SEO action task JSON based on recommendation or draft context."""
        pass

    @abstractmethod
    def decide_agent_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Decide next agent action (tool call or finish) based on run goal, history, and available tools."""
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

    def generate_content_brief(self, context: Dict[str, Any]) -> Dict[str, Any]:
        content_type = context.get('content_type') or 'blog_post'
        target_keyword = context.get('target_keyword') or context.get('keyword') or 'SEO Best Practices'
        target_url = context.get('target_url') or context.get('url') or ''
        rec_title = context.get('recommendation_title') or f"Optimize {target_keyword}"
        project_name = context.get('project_name') or 'DoxaRank'

        kw_clean = target_keyword.strip()
        kw_title = kw_clean.title() if kw_clean else 'Target Topic'
        slug = kw_clean.lower().replace(' ', '-').replace('/', '-') if kw_clean else 'seo-content-brief'

        # Content brief variations based on type
        if content_type == 'landing_page':
            return {
                "title": f"High-Converting Landing Page Brief: {kw_title}",
                "target_keyword": kw_clean,
                "secondary_keywords": [
                    f"best {kw_clean}",
                    f"{kw_clean} services",
                    f"{kw_clean} solutions",
                    f"top {kw_clean} company"
                ],
                "search_intent": "commercial",
                "target_url": target_url or f"/{slug}",
                "content_type": "landing_page",
                "recommended_title": f"{kw_title} — Leading Solutions & Services | {project_name}",
                "meta_description": f"Explore top-tier {kw_clean} solutions tailored for your business. Fast implementation, transparent pricing, and measurable growth. Get started today.",
                "suggested_slug": f"/{slug}",
                "content_angle": f"Focus on ROI, speed-to-value, and social proof to convert high-intent commercial searchers looking for {kw_clean}.",
                "audience": "Decision makers, business owners, and marketing managers evaluating service providers.",
                "outline": [
                    {
                        "heading": f"{kw_title}: Transform Your Results",
                        "level": "H1",
                        "key_points": [
                            "Hero value proposition with clear primary CTA",
                            "Trust indicators, security badges, and client logos",
                            "Quantified benefit summary in above-the-fold viewport"
                        ]
                    },
                    {
                        "heading": f"Why Choose Our {kw_title} Solutions?",
                        "level": "H2",
                        "key_points": [
                            "Differentiating feature comparison against industry alternatives",
                            "Key pain points resolved with concrete workflows",
                            "Interactive feature spotlight with visuals"
                        ]
                    },
                    {
                        "heading": "How It Works: 3-Step Process",
                        "level": "H2",
                        "key_points": [
                            "Step 1: Initial audit and baseline discovery",
                            "Step 2: Custom execution and integration",
                            "Step 3: Ongoing optimization and reporting"
                        ]
                    },
                    {
                        "heading": "Frequently Asked Questions",
                        "level": "H2",
                        "key_points": [
                            "Address pricing, onboarding timeframe, and contract flexibility",
                            "Implement FAQPage Schema markup for SERP rich snippet coverage"
                        ]
                    },
                    {
                        "heading": f"Ready to Get Started with {kw_title}?",
                        "level": "H2",
                        "key_points": [
                            "Final conversion form with minimal input fields",
                            "Direct contact option for enterprise inquiries"
                        ]
                    }
                ],
                "key_points": [
                    f"Position {kw_clean} as a seamless, high-ROI solution.",
                    "Ensure mobile load speed is under 2.0s with immediate visual hierarchy.",
                    "Include prominent CTA buttons in header, mid-page, and footer."
                ],
                "internal_link_suggestions": [
                    {
                        "target_url": "/case-studies",
                        "anchor_text": f"{kw_clean} case studies",
                        "context": "Link from the social proof section to validate claimed results."
                    },
                    {
                        "target_url": "/pricing",
                        "anchor_text": "view transparent pricing plans",
                        "context": "Link from FAQ or comparison section for commercial intent clarity."
                    }
                ],
                "external_link_suggestions": [
                    {
                        "source": "Gartner / Statista Industry Benchmark",
                        "anchor_text": "market research data",
                        "context": "Cite verified industry statistics supporting market demand."
                    }
                ],
                "faq_questions": [
                    {
                        "question": f"What is the typical turnaround for {kw_clean}?",
                        "answer_guidance": "Standard onboarding takes between 3-5 business days with full dedicated support."
                    },
                    {
                        "question": f"How do I know if {kw_clean} fits my organization?",
                        "answer_guidance": "Ideal for growing teams looking to scale efficiency, visibility, and conversion metrics."
                    }
                ],
                "entities_topics": [
                    kw_clean,
                    "Conversion Rate Optimization",
                    "Commercial Search Intent",
                    "Customer Lifetime Value",
                    "Enterprise Solutions"
                ],
                "content_length_target": 1200
            }

        elif content_type == 'page_optimization':
            return {
                "title": f"On-Page Content Refresh & Optimization: {kw_title}",
                "target_keyword": kw_clean,
                "secondary_keywords": [
                    f"{kw_clean} guide",
                    f"{kw_clean} tips",
                    f"{kw_clean} examples",
                    f"how to {kw_clean}"
                ],
                "search_intent": "informational",
                "target_url": target_url or f"/{slug}",
                "content_type": "page_optimization",
                "recommended_title": f"{kw_title}: Step-by-Step Practical Optimization Guide (2026)",
                "meta_description": f"Master {kw_clean} with actionable tactics, expert frameworks, and real-world examples. Updated for 2026 search quality standards.",
                "suggested_slug": f"/{slug}",
                "content_angle": f"Upgrade existing page depth to satisfy modern Google helpful content standards for '{kw_clean}' with unique expert insights.",
                "audience": "Practitioners, website managers, and search marketers refining existing workflows.",
                "outline": [
                    {
                        "heading": f"{kw_title}: Comprehensive Expert Guide",
                        "level": "H1",
                        "key_points": [
                            "Direct definition answering primary search query in first 100 words",
                            "Key takeaway summary box for quick skimmers",
                            "Editorial update notice for 2026 freshness"
                        ]
                    },
                    {
                        "heading": f"Core Foundations of {kw_title}",
                        "level": "H2",
                        "key_points": [
                            "Breakdown of essential components with diagrams/tables",
                            "Common misconceptions versus proven best practices",
                            "Data-backed performance correlations"
                        ]
                    },
                    {
                        "heading": "Step-by-Step Implementation Framework",
                        "level": "H2",
                        "key_points": [
                            "Actionable workflow checklist from beginner to advanced",
                            "Code or template snippets ready to copy and deploy",
                            "Diagnostic checkpoints to verify success"
                        ]
                    },
                    {
                        "heading": "Frequently Asked Questions",
                        "level": "H2",
                        "key_points": [
                            "Target high-frequency People Also Ask questions",
                            "Concise 2-3 sentence answers for snippet captures"
                        ]
                    }
                ],
                "key_points": [
                    f"Refresh stale paragraphs with 2026 data and direct answers.",
                    f"Elevate H2/H3 subheadings to incorporate secondary keyword variations.",
                    "Embed schema markup and visual comparison tables."
                ],
                "internal_link_suggestions": [
                    {
                        "target_url": "/blog/seo-fundamentals",
                        "anchor_text": "core SEO fundamentals",
                        "context": "Contextual link in introductory section."
                    },
                    {
                        "target_url": "/tools/rank-tracker",
                        "anchor_text": "track your keyword rankings",
                        "context": "CTA link in conclusion section."
                    }
                ],
                "external_link_suggestions": [
                    {
                        "source": "Google Search Central Documentation",
                        "anchor_text": "Google Search Central best practices",
                        "context": "Reference official guidelines on search quality."
                    }
                ],
                "faq_questions": [
                    {
                        "question": f"Why is {kw_clean} important for organic search?",
                        "answer_guidance": "It establishes topical depth and algorithmic relevance for high-volume informational queries."
                    },
                    {
                        "question": f"How often should {kw_clean} content be updated?",
                        "answer_guidance": "At least every 6-12 months or whenever search engine guidelines and user intent evolve."
                    }
                ],
                "entities_topics": [
                    kw_clean,
                    "Information Gain Score",
                    "E-E-A-T Quality Guidelines",
                    "Topical Authority Map",
                    "Search Intent Alignment"
                ],
                "content_length_target": 1800
            }

        elif content_type == 'technical_implementation':
            return {
                "title": f"Technical SEO Implementation Brief: {kw_title}",
                "target_keyword": kw_clean,
                "secondary_keywords": [
                    f"technical {kw_clean}",
                    f"fix {kw_clean}",
                    f"{kw_clean} audit",
                    "core web vitals optimization"
                ],
                "search_intent": "informational",
                "target_url": target_url or "/",
                "content_type": "technical_implementation",
                "recommended_title": f"Technical Implementation Guide: Resolving {kw_title} Issues",
                "meta_description": f"Developer execution brief to resolve {kw_clean} bottlenecks. Step-by-step code snippets, server headers, and validation benchmarks.",
                "suggested_slug": f"/dev/{slug}",
                "content_angle": "Developer-first technical specification with exact code blocks, HTTP status requirements, and test suites.",
                "audience": "Full-stack engineers, DevOps specialists, and technical SEO architects.",
                "outline": [
                    {
                        "heading": f"Technical SEO Specification: {kw_title}",
                        "level": "H1",
                        "key_points": [
                            "Executive summary of the technical bottleneck and affected endpoints",
                            "Severity rating, crawl budget impact, and indexation risks",
                            "Architecture diagram or request/response lifecycle"
                        ]
                    },
                    {
                        "heading": "Root Cause Analysis & Audit Findings",
                        "level": "H2",
                        "key_points": [
                            "Observed HTTP response codes, headers, and DOM anomalies",
                            "Mobile viewport rendering and Googlebot crawl simulation",
                            "Log analysis evidence"
                        ]
                    },
                    {
                        "heading": "Step-by-Step Code & Configuration Changes",
                        "level": "H2",
                        "key_points": [
                            "Web server / CDN configuration changes (Nginx / Cloudflare)",
                            "Application backend changes with code diffs",
                            "Frontend template fixes (canonical, robots, schema JSON-LD)"
                        ]
                    },
                    {
                        "heading": "Verification & Regression Testing Protocol",
                        "level": "H2",
                        "key_points": [
                            "Automated curl and header inspection commands",
                            "Google Search Console URL Inspection verification",
                            "DoxaRank site audit re-run checklist"
                        ]
                    }
                ],
                "key_points": [
                    "Ensure HTTP 200 responses with valid canonical tags across all devices.",
                    "Verify XML sitemaps match current indexable URLs without redirects.",
                    "Validate structured data syntax using Schema.org validator."
                ],
                "internal_link_suggestions": [
                    {
                        "target_url": "/audits/technical",
                        "anchor_text": "site audit dashboard",
                        "context": "Direct engineers to monitor health score improvements."
                    }
                ],
                "external_link_suggestions": [
                    {
                        "source": "W3C / IETF RFC Standards",
                        "anchor_text": "HTTP/1.1 Specification",
                        "context": "Reference official standard for status code and header handling."
                    }
                ],
                "faq_questions": [
                    {
                        "question": f"What is the crawl budget impact of {kw_clean}?",
                        "answer_guidance": "Eliminating redirect chains and 4xx errors frees up Googlebot crawl budget for high-priority landing pages."
                    },
                    {
                        "question": f"How to verify {kw_clean} in Google Search Console?",
                        "answer_guidance": "Use the URL Inspection Tool to request live test and validate clean indexing state."
                    }
                ],
                "entities_topics": [
                    "HTTP Response Headers",
                    "Canonicalization",
                    "Crawl Efficiency",
                    "Schema JSON-LD",
                    "Core Web Vitals"
                ],
                "content_length_target": 1400
            }

        # Default Blog Post / Article Brief
        return {
            "title": f"In-Depth Article Brief: Complete Guide to {kw_title}",
            "target_keyword": kw_clean,
            "secondary_keywords": [
                f"{kw_clean} guide",
                f"{kw_clean} strategies",
                f"{kw_clean} best practices",
                f"{kw_clean} in 2026"
            ],
            "search_intent": "informational",
            "target_url": target_url or f"/blog/{slug}",
            "content_type": "blog_post",
            "recommended_title": f"The Ultimate Guide to {kw_title} (2026 Edition)",
            "meta_description": f"Learn everything you need to know about {kw_clean}. Discover actionable strategies, expert insights, and step-by-step best practices.",
            "suggested_slug": f"/blog/{slug}",
            "content_angle": f"Authoritative, data-rich guide offering practical frameworks and templates that outperform thin competitor summaries for '{kw_clean}'.",
            "audience": "Industry professionals, business owners, and learners seeking practical actionable advice.",
            "outline": [
                {
                    "heading": f"The Complete Guide to {kw_title}",
                    "level": "H1",
                    "key_points": [
                        "Engaging hook highlighting why this topic matters today",
                        "Clear summary table of contents for seamless navigation",
                        "High-level takeaway box"
                    ]
                },
                {
                    "heading": f"What is {kw_title} and Why Does It Matter?",
                    "level": "H2",
                    "key_points": [
                        "Concise definition targeting featured snippet answer box",
                        "Current industry landscape and common challenges",
                        "Real-world impact and business benefits"
                    ]
                },
                {
                    "heading": f"Essential Strategies for Mastering {kw_title}",
                    "level": "H2",
                    "key_points": [
                        "Strategy 1: Foundational setup and best practices",
                        "Strategy 2: Advanced tactics and optimization techniques",
                        "Strategy 3: Measuring performance and scaling results"
                    ]
                },
                {
                    "heading": "Common Pitfalls and How to Avoid Them",
                    "level": "H2",
                    "key_points": [
                        "Top 3 frequent mistakes made by teams",
                        "Corrective action steps and preventative safeguards"
                    ]
                },
                {
                    "heading": "Frequently Asked Questions",
                    "level": "H2",
                    "key_points": [
                        "Answers to top related search queries",
                        "FAQPage schema optimization"
                    ]
                },
                {
                    "heading": "Conclusion & Next Steps",
                    "level": "H2",
                    "key_points": [
                        "Actionable recap checklist",
                        "Contextual call to action"
                    ]
                }
            ],
            "key_points": [
                f"Establish comprehensive authority around '{kw_clean}'.",
                "Incorporate original data, practical examples, and visual breakdowns.",
                "Structure content with clear semantic H2/H3 headers for readability."
            ],
            "internal_link_suggestions": [
                {
                    "target_url": "/blog/seo-strategy",
                    "anchor_text": "complete SEO strategy guide",
                    "context": "Link from the foundational strategy section."
                },
                {
                    "target_url": "/pricing",
                    "anchor_text": "explore DoxaRank features",
                    "context": "Link in concluding CTA section."
                }
            ],
            "external_link_suggestions": [
                {
                    "source": "Leading Industry Publication / Research",
                    "anchor_text": "industry benchmark report",
                    "context": "Cite statistical proof points in the strategy section."
                }
            ],
            "entities_topics": [
                kw_clean,
                "Content Marketing Strategy",
                "User Intent Satisfaction",
                "Search Visibility",
                "Digital Marketing Analytics"
            ],
            "content_length_target": 1600
        }

    def generate_content_draft(self, context: Dict[str, Any]) -> Dict[str, Any]:
        content_type = context.get('content_type') or 'blog_post'
        target_keyword = context.get('target_keyword') or context.get('keyword') or 'SEO Content Strategy'
        secondary_keywords = context.get('secondary_keywords') or []
        rec_title = context.get('title') or context.get('recommended_title') or f"Complete Guide to {target_keyword}"
        project_name = context.get('project_name') or 'DoxaRank'
        slug = context.get('suggested_slug') or target_keyword.lower().replace(' ', '-').replace('/', '-')
        target_url = context.get('target_url') or f"/{slug}"
        audience = context.get('audience') or 'Industry professionals and decision makers'
        content_angle = context.get('content_angle') or f"Actionable, data-driven approach to mastering {target_keyword}."

        kw_clean = target_keyword.strip()
        kw_title = kw_clean.title() if kw_clean else 'Target Topic'

        if content_type == 'landing_page':
            title = f"{kw_title} — Leading Enterprise Solutions | {project_name}"
            meta_title = f"{kw_title} Solutions & Services | {project_name}"
            meta_desc = f"Discover leading {kw_clean} solutions designed for scalable growth. Compare features, transparent pricing, and measurable ROI. Get started today."
            intro = f"In today's fast-moving search and commercial landscape, achieving sustained growth requires a dedicated approach to {kw_clean}. Our enterprise-grade platform empowers your team with automated intelligence, real-time tracking, and verified results."
            sections = [
                {
                    "heading": f"Why Modern Teams Choose Our {kw_title} Solutions",
                    "level": "H2",
                    "content": f"Navigating {kw_clean} demands precision and efficiency. Traditional workflows often suffer from fragmented data and slow execution cycles. Our specialized solution bridges these gaps by providing clear benchmarks, integrated performance metrics, and automated workflows that save your team dozens of hours each month.",
                    "key_points": [
                        "Eliminate manual bottlenecks with automated performance tracking",
                        "Data-backed transparency across all key business touchpoints",
                        "Seamless integration into existing enterprise workflows"
                    ]
                },
                {
                    "heading": "Core Features & Competitive Advantages",
                    "level": "H2",
                    "content": f"When evaluating solutions for {kw_clean}, capability and reliability are paramount. Our platform delivers high-accuracy insights, sub-second response times, and tailored recommendations that ensure you remain ahead of competitors. Every feature is engineered to provide immediate value without steep learning curves.",
                    "key_points": [
                        "Real-time diagnostic alerts and anomaly detection",
                        "Customizable reporting dashboards tailored for executive leadership",
                        "Dedicated support and comprehensive onboarding documentation"
                    ]
                },
                {
                    "heading": "How It Works: Simple 3-Step Implementation",
                    "level": "H2",
                    "content": f"Getting started with {kw_clean} is straightforward:\n\n1. **Connect & Audit:** Integrate your existing assets to establish baseline metrics.\n2. **Optimize & Execute:** Follow prioritized recommendations and automated briefs.\n3. **Measure & Scale:** Track ranking velocity and organic visibility gains over time.",
                    "key_points": [
                        "Setup takes less than 15 minutes",
                        "Zero disruption to existing production environments"
                    ]
                },
                {
                    "heading": f"Ready to Transform Your {kw_title} Strategy?",
                    "level": "H2",
                    "content": f"Join hundreds of forward-thinking organizations using DoxaRank to unlock organic growth. Start your free trial today or request a custom demonstration with our product specialists.",
                    "key_points": [
                        "No long-term contracts required",
                        "Full access to all platform features"
                    ]
                }
            ]
            faqs = [
                {
                    "question": f"How quickly can we implement {kw_clean}?",
                    "answer": f"Standard onboarding and deployment for {kw_clean} is completed within 3 to 5 business days, with guided walkthroughs from our team."
                },
                {
                    "question": f"What measurable results can we expect from {kw_clean}?",
                    "answer": f"Organizations typically experience improved workflow efficiency, higher visibility on commercial search queries, and reduced manual overhead within the first month."
                }
            ]
            schema_type = "WebPage"

        elif content_type == 'page_optimization':
            title = f"{kw_title}: Step-by-Step Practical Optimization Guide"
            meta_title = f"{kw_title} Optimization Guide (2026 Updated)"
            meta_desc = f"Master {kw_clean} with actionable tactics, updated frameworks, and real-world examples. Learn how to optimize on-page signals and search intent."
            intro = f"Search algorithms and user expectations for {kw_clean} continue to evolve rapidly in 2026. This comprehensive optimization guide provides the exact frameworks, content adjustments, and technical checkpoints needed to elevate your page's organic search relevance."
            sections = [
                {
                    "heading": f"Understanding Search Intent for {kw_title}",
                    "level": "H2",
                    "content": f"To optimize effectively for {kw_clean}, you must first align with search intent. Users searching for this query are looking for authoritative, direct, and actionable solutions. Ensuring your introductory section immediately answers the core query establishes high helpfulness scores and reduces bounce rates.",
                    "key_points": [
                        "Address the primary query within the first 100 words",
                        "Incorporate clear visual breakdowns and structured subheadings",
                        "Eliminate fluff and outdated references"
                    ]
                },
                {
                    "heading": "Step-by-Step On-Page Optimization Framework",
                    "level": "H2",
                    "content": f"Follow this prioritized checklist to refresh existing content:\n\n- **Header Hierarchy:** Ensure H1 contains '{kw_clean}' and H2s incorporate secondary variations naturally.\n- **Depth & Originality:** Add first-party examples, data points, or workflows.\n- **Internal Links:** Connect relevant cluster pages with contextual anchor text.\n- **Schema Markup:** Validate Article and FAQPage structured data.",
                    "key_points": [
                        "Refresh stale statistics with 2026 benchmarks",
                        "Add practical bullet points for quick skimmers"
                    ]
                },
                {
                    "heading": "Measuring Post-Optimization Impact",
                    "level": "H2",
                    "content": f"After publishing optimizations for {kw_clean}, monitor Search Console click-through rate and impression trends over a 14-day window. Re-crawling can be accelerated via Google Search Console URL inspection.",
                    "key_points": [
                        "Track ranking position shifts weekly in DoxaRank",
                        "Inspect engagement metrics and bounce rates"
                    ]
                }
            ]
            faqs = [
                {
                    "question": f"Why is optimizing for {kw_clean} essential in 2026?",
                    "answer": f"Search engines prioritize fresh, highly-helpful content that directly satisfies query intent without unnecessary filler."
                },
                {
                    "question": f"How often should {kw_clean} pages be updated?",
                    "answer": "Pages targeting competitive search terms should be reviewed every 6 months to maintain topical relevance and freshness signals."
                }
            ]
            schema_type = "Article"

        elif content_type == 'technical_implementation':
            title = f"Technical Implementation Spec: Resolving {kw_title} Bottlenecks"
            meta_title = f"Technical SEO Spec: {kw_title} Fix & Implementation"
            meta_desc = f"Developer execution guide for {kw_clean}. Step-by-step code snippets, server headers, configuration changes, and validation tests."
            intro = f"This technical specification provides the engineering requirements, architectural considerations, and code configurations necessary to resolve {kw_clean} bottlenecks on production endpoints."
            sections = [
                {
                    "heading": "Issue Summary & Root Cause Analysis",
                    "level": "H2",
                    "content": f"An automated audit identified performance or indexing anomalies relating to {kw_clean}. Left unresolved, these issues consume unnecessary crawl budget and introduce indexation delays. Below is the diagnostic overview of observed response codes and affected templates.",
                    "key_points": [
                        "Identified latency and header misconfigurations",
                        "Impacts mobile crawl budget and page speed indices",
                        "High priority for engineering remediation"
                    ]
                },
                {
                    "heading": "Required Configuration & Code Changes",
                    "level": "H2",
                    "content": f"Apply the following configuration changes across the application and CDN layer:\n\n```nginx\n# Example Nginx Header Configuration for {kw_clean}\nlocation / {{\n    add_header X-Content-Type-Options nosniff;\n    add_header Cache-Control \"public, max-age=31536000, immutable\";\n}}\n```\n\nEnsure canonical tags on all responding URLs strictly match the primary HTTPS host.",
                    "key_points": [
                        "Enforce HTTPS and clean 301 canonical redirects",
                        "Configure proper cache headers for static assets",
                        "Embed valid JSON-LD structured data in document head"
                    ]
                },
                {
                    "heading": "Testing & Verification Protocol",
                    "level": "H2",
                    "content": f"Execute automated curl verification commands to inspect headers and response times:\n\n```bash\ncurl -I -L https://example.com{target_url}\n```\n\nVerify that the response returns HTTP 200 with no redirect loops, and run a site audit re-scan in DoxaRank.",
                    "key_points": [
                        "Validate with Google Rich Results Test tool",
                        "Confirm zero 4xx/5xx status codes in server access logs"
                    ]
                }
            ]
            faqs = [
                {
                    "question": f"What is the impact of resolving {kw_clean}?",
                    "answer": f"Resolving technical bottlenecks ensures optimal crawl efficiency, rapid indexation of new URLs, and improved Core Web Vitals."
                }
            ]
            schema_type = "TechArticle"

        else: # Default blog_post
            title = f"The Ultimate Guide to {kw_title} (2026 Edition)"
            meta_title = f"The Complete Guide to {kw_title} | {project_name}"
            meta_desc = f"Learn everything you need to know about {kw_clean}. Discover actionable strategies, expert insights, and step-by-step best practices."
            intro = f"Mastering {kw_clean} has become one of the most vital imperatives for modern digital growth. Whether you are looking to build authority, capture search intent, or improve execution efficiency, this comprehensive guide delivers the foundational knowledge and advanced frameworks needed to succeed."
            sections = [
                {
                    "heading": f"What is {kw_title} and Why Does It Matter?",
                    "level": "H2",
                    "content": f"{kw_title} refers to the systematic approach of optimizing visibility, quality, and engagement for target audiences. By aligning editorial depth with real user search intent, organizations can establish lasting topical authority and outperform thin summaries across competitive search landscapes.",
                    "key_points": [
                        f"Foundational definition and relevance of {kw_clean}",
                        "Key search intent dynamics and user expectations",
                        "Long-term compounding value of high-quality content"
                    ]
                },
                {
                    "heading": f"Key Strategies for Mastering {kw_title}",
                    "level": "H2",
                    "content": f"Achieving standout results with {kw_clean} requires three core pillars:\n\n1. **Evidence-Based Grounding:** Base every strategy on observed performance data rather than guesswork.\n2. **Structured Editorial Architecture:** Organize information with clear heading hierarchies and concise summaries.\n3. **Continuous Iteration:** Use analytical feedback to refine and expand high-performing sections.",
                    "key_points": [
                        "Prioritize actionable takeaways over generic theory",
                        "Incorporate supporting secondary keywords naturally throughout subheadings",
                        "Maintain high readability with short paragraphs and bulleted lists"
                    ]
                },
                {
                    "heading": "Common Mistakes to Avoid",
                    "level": "H2",
                    "content": f"Many teams struggle with {kw_clean} due to avoidable missteps:\n\n- **Keyword Stuffing:** Always prioritize natural readability and semantic clarity.\n- **Ignoring Search Intent:** Ensure the content matches whether the user wants information, comparison, or direct action.\n- **Neglecting Technical Foundations:** Slow page speeds and missing schema can undermine great content.",
                    "key_points": [
                        "Audit existing content before publishing new duplicates",
                        "Keep user satisfaction as the primary metric of success"
                    ]
                },
                {
                    "heading": "Conclusion & Actionable Next Steps",
                    "level": "H2",
                    "content": f"Building sustainable search visibility around {kw_clean} is an ongoing journey. Start by implementing the core recommendations outlined in this guide, monitor your rank progression with DoxaRank, and continue updating your content as market trends evolve.",
                    "key_points": [
                        "Execute foundational optimizations today",
                        "Track keyword positions and click-through rates regularly"
                    ]
                }
            ]
            faqs = [
                {
                    "question": f"How do I get started with {kw_clean}?",
                    "answer": f"Begin with a baseline audit, identify primary and secondary keywords, and structure your content with clear H1/H2 headings."
                },
                {
                    "question": f"What are the best practices for {kw_clean}?",
                    "answer": "Focus on answering user search intent in depth, maintaining high readability, adding schema markup, and refreshing content regularly."
                }
            ]
            schema_type = "Article"

        # Build full markdown content body
        body_parts = [f"# {title}", "", intro, ""]
        for sec in sections:
            body_parts.append(f"## {sec['heading']}")
            body_parts.append("")
            body_parts.append(sec['content'])
            body_parts.append("")
        if faqs:
            body_parts.append("## Frequently Asked Questions")
            body_parts.append("")
            for f in faqs:
                body_parts.append(f"**Q: {f['question']}**")
                body_parts.append(f"{f['answer']}")
                body_parts.append("")

        full_body = "\n".join(body_parts)
        words = len(full_body.split())

        schema_json_ld = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "headline": title,
            "description": meta_desc,
            "author": {
                "@type": "Organization",
                "name": project_name
            }
        }
        if faqs:
            schema_json_ld["mainEntity"] = [
                {
                    "@type": "Question",
                    "name": f["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": f["answer"]
                    }
                }
                for f in faqs
            ]

        return {
            "title": title,
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "slug": slug,
            "introduction": intro,
            "sections": sections,
            "faq": faqs,
            "internal_links": [
                {
                    "target_url": "/services",
                    "anchor_text": f"explore {kw_clean} solutions",
                    "context": "Contextual link in strategy section."
                }
            ],
            "external_links": [
                {
                    "source": "Official Industry Guide",
                    "anchor_text": "industry benchmark data",
                    "context": "Cited in foundational overview section."
                }
            ],
            "schema_json_ld": schema_json_ld,
            "word_count": words
        }

    def generate_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        source_type = context.get('source_type', 'recommendation')
        action_type = context.get('action_type') or 'optimize_existing_content'
        priority = context.get('priority', 'high')
        target_url = context.get('target_url') or ''
        target_keyword = context.get('target_keyword') or ''
        current_state = context.get('current_state') or {}
        proposed_payload = context.get('proposed_payload') or {}
        rec_title = context.get('title') or 'SEO Action'

        # Build deterministic realistic action proposal based on action_type
        if action_type == 'publish_new_content' or source_type == 'draft':
            draft_title = proposed_payload.get('title') or rec_title or f"Publish: {target_keyword.title()}"
            slug = proposed_payload.get('slug') or f"/blog/{target_keyword.replace(' ', '-') if target_keyword else 'new-guide'}"
            meta_title = proposed_payload.get('meta_title') or f"{draft_title} | Comprehensive Guide"
            meta_desc = proposed_payload.get('meta_description') or f"Explore in-depth analysis and expert recommendations on {target_keyword}."

            return {
                "title": f"Publish New SEO Content: \"{draft_title}\"",
                "description": f"Deploy approved, high-authority content package targeting '{target_keyword}' to capture targeted search traffic and establish topical relevance.",
                "action_type": "publish_new_content",
                "priority": priority,
                "target_url": target_url or slug,
                "target_keyword": target_keyword,
                "current_state": {
                    "status": "unpublished",
                    "existing_url": target_url or "None (New Asset)",
                    "target_query": target_keyword
                },
                "proposed_change": {
                    "title": draft_title,
                    "slug": slug,
                    "meta_title": meta_title,
                    "meta_description": meta_desc,
                    "content": proposed_payload.get('content') or f"# {draft_title}\n\nComprehensive content for {target_keyword}.",
                    "faq": proposed_payload.get('faq') or [],
                    "internal_links": proposed_payload.get('internal_links') or [],
                    "schema_json_ld": proposed_payload.get('schema_json_ld') or {
                        "@context": "https://schema.org",
                        "@type": "Article",
                        "headline": draft_title,
                        "description": meta_desc
                    }
                },
                "implementation_instructions": (
                    "### Implementation Instructions\n\n"
                    "**1. Marketer / Editor Review:**\n"
                    f"- Verify content tone and branding for '{draft_title}'.\n"
                    "- Confirm target audience and value proposition alignment.\n\n"
                    "**2. SEO Specialist Verification:**\n"
                    f"- Confirm primary keyword '{target_keyword}' is present in H1, first 100 words, and meta tags.\n"
                    f"- Validate slug structure: `{slug}`.\n"
                    "- Ensure Schema JSON-LD Article/FAQ markup is valid.\n\n"
                    "**3. Developer / CMS Deployment:**\n"
                    "- Create new CMS entry with the provided Markdown/HTML payload.\n"
                    "- Configure canonical URL and publish status.\n"
                    "- Submit newly published URL to Google Search Console for indexing."
                )
            }

        elif action_type == 'update_meta_description':
            proposed_meta = proposed_payload.get('meta_description') or f"Discover top insights and actionable solutions for {target_keyword}. Explore comprehensive expert analysis."
            return {
                "title": f"Update Meta Description for \"{target_keyword or target_url}\"",
                "description": f"Revise meta description on {target_url} to improve organic click-through rate (CTR) for search query '{target_keyword}'.",
                "action_type": "update_meta_description",
                "priority": priority,
                "target_url": target_url,
                "target_keyword": target_keyword,
                "current_state": {
                    "existing_meta_description": current_state.get('existing_meta_description', 'Missing or outdated meta description'),
                    "observed_ctr": current_state.get('observed_ctr', 'Below SERP average')
                },
                "proposed_change": {
                    "meta_description": proposed_meta,
                    "character_count": len(proposed_meta),
                    "target_keyword_included": target_keyword.lower() in proposed_meta.lower() if target_keyword else True
                },
                "implementation_instructions": (
                    "### Implementation Instructions\n\n"
                    "**1. Marketer / Copywriter:**\n"
                    f"- Review proposed copy for clarity and compelling CTA: \"{proposed_meta}\"\n\n"
                    "**2. SEO Specialist:**\n"
                    f"- Verify length is within 140-160 characters (currently {len(proposed_meta)} chars).\n\n"
                    "**3. Developer:**\n"
                    f"- Update `<meta name=\"description\" content=\"{proposed_meta}\">` tag on `{target_url}`."
                )
            }

        elif action_type == 'update_title':
            proposed_title = proposed_payload.get('title') or proposed_payload.get('meta_title') or f"{target_keyword.title() if target_keyword else 'Target Page'} | Expert Guide"
            return {
                "title": f"Update Title Tag for \"{target_keyword or target_url}\"",
                "description": f"Optimize title tag on {target_url} to strengthen relevance for primary search query '{target_keyword}'.",
                "action_type": "update_title",
                "priority": priority,
                "target_url": target_url,
                "target_keyword": target_keyword,
                "current_state": {
                    "existing_title": current_state.get('existing_title', 'Generic Title'),
                    "target_query": target_keyword
                },
                "proposed_change": {
                    "title": proposed_title,
                    "character_count": len(proposed_title)
                },
                "implementation_instructions": (
                    "### Implementation Instructions\n\n"
                    "**1. Marketer / Copywriter:**\n"
                    f"- Confirm brand suffix and clear value proposition in \"{proposed_title}\".\n\n"
                    "**2. SEO Specialist:**\n"
                    "- Ensure target keyword is front-loaded and under 60 characters.\n\n"
                    "**3. Developer:**\n"
                    f"- Update `<title>` and `og:title` on `{target_url}`."
                )
            }

        else:
            return {
                "title": f"Execute SEO Action: {rec_title}",
                "description": f"Apply evidence-grounded SEO optimizations for '{target_keyword}' on {target_url or 'project landing page'}.",
                "action_type": action_type,
                "priority": priority,
                "target_url": target_url,
                "target_keyword": target_keyword,
                "current_state": current_state or {"target_query": target_keyword, "target_url": target_url},
                "proposed_change": proposed_payload or {
                    "action_summary": f"Apply SEO improvements for {target_keyword}",
                    "guidance": "Follow the structured checklist below."
                },
                "implementation_instructions": (
                    "### Implementation Instructions\n\n"
                    "**1. Marketer / Content Lead:**\n"
                    f"- Review changes to ensure message consistency for '{target_keyword}'.\n\n"
                    "**2. SEO Specialist:**\n"
                    f"- Verify keyword placement, internal links, and search intent alignment on `{target_url}`.\n\n"
                    "**3. Developer / Webmaster:**\n"
                    "- Implement on-page changes, verify canonical configuration, and deploy update."
                )
            }

    def decide_agent_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic Mock reasoning logic for Agent Orchestrator.
        Inspects goal and prior step history to decide the next logical tool call or finish.
        Supports dynamic multi-step exploration for GSC intelligence, audit diagnostics, and rank tracking.
        """
        goal = (context.get('goal') or '').lower()
        history = context.get('history') or []
        available_tools = [t.get('name') for t in context.get('available_tools', []) if isinstance(t, dict)]
        tool_calls = [h.get('tool_name') for h in history if h.get('tool_name')]

        # Custom mock decision injection for testing
        if context.get('mock_decision'):
            return context['mock_decision']

        # Extract returned IDs and data from history observations
        insight_id = context.get('target_insight_id')
        rec_id = context.get('target_recommendation_id')
        brief_id = context.get('target_brief_id')
        draft_id = context.get('target_draft_id')
        top_query_extracted = None

        for h in history:
            t_name = h.get('tool_name')
            t_out = h.get('tool_output') or {}
            if isinstance(t_out, dict):
                if t_name == 'generate_recommendation' and t_out.get('id'):
                    rec_id = t_out['id']
                elif t_name == 'generate_content_brief' and t_out.get('id'):
                    brief_id = t_out['id']
                elif t_name == 'generate_content_draft' and t_out.get('id'):
                    draft_id = t_out['id']
                elif t_name == 'gsc_top_queries' and t_out.get('top_queries'):
                    top_query_extracted = t_out['top_queries'][0].get('query')
                elif t_name == 'gsc_search_analytics' and t_out.get('rows'):
                    top_query_extracted = t_out['rows'][0].get('query')

        # ---------------------------------------------------------------------
        # BRANCH 1: GSC Performance Comparison / Period Trend Goal
        # ---------------------------------------------------------------------
        is_comparison_goal = any(term in goal for term in ['compare', 'comparison', 'trend', 'period', 'previous period', 'over time', 'last 28'])
        if is_comparison_goal and ('gsc_performance_comparison' in available_tools or 'gsc_opportunity_audit' in available_tools):
            if 'gsc_performance_comparison' not in tool_calls and 'gsc_performance_comparison' in available_tools:
                return {
                    "action": "tool",
                    "tool_name": "gsc_performance_comparison",
                    "arguments": {
                        "base_start_date": "2026-08-01",
                        "base_end_date": "2026-08-28",
                        "comp_start_date": "2026-07-04",
                        "comp_end_date": "2026-07-31",
                        "row_limit": 50
                    },
                    "reason": "Compare Search Console performance across consecutive 28-day periods to detect traffic and ranking deltas."
                }

            if 'gsc_opportunity_audit' not in tool_calls and 'gsc_opportunity_audit' in available_tools:
                return {
                    "action": "tool",
                    "tool_name": "gsc_opportunity_audit",
                    "arguments": {"min_impressions": 10, "sync_to_insights": True},
                    "reason": "Execute GSC intelligence audit to identify specific page 2 keywords and CTR underperformance contributing to trend."
                }

            if 'generate_recommendation' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "generate_recommendation",
                    "arguments": {"insight_id": insight_id or 1},
                    "reason": "Generate grounded AI recovery strategy for highest-priority search decline insight."
                }

            if 'propose_seo_action' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "propose_seo_action",
                    "arguments": {"source_type": "recommendation", "source_id": rec_id or 1},
                    "reason": "Propose formal SEO recovery action for human review and approval."
                }

            return {
                "action": "finish",
                "summary": (
                    f"Completed Google Search Console trend comparison workflow for goal: \"{context.get('goal', '')}\". "
                    "Analyzed period-over-period search metrics, evaluated opportunity findings, synthesized a strategic recovery recommendation, "
                    "and proposed a formal SEO Action awaiting human approval."
                )
            }

        # ---------------------------------------------------------------------
        # BRANCH 2: GSC Queries & Opportunity Intelligence Goal
        # ---------------------------------------------------------------------
        is_gsc_goal = any(term in goal for term in ['gsc', 'search console', 'ctr', 'impressions', 'page 2', 'queries', 'snippet'])
        if is_gsc_goal:
            # 1. Inspect top queries from live GSC API
            if 'gsc_top_queries' not in tool_calls and 'gsc_top_queries' in available_tools:
                return {
                    "action": "tool",
                    "tool_name": "gsc_top_queries",
                    "arguments": {"start_date": "2026-08-01", "end_date": "2026-08-28", "limit": 20},
                    "reason": "Query highest-impression organic search queries from Google Search Console."
                }

            # 2. Correlate with top landing pages for the top search query
            if 'gsc_top_pages' not in tool_calls and 'gsc_top_pages' in available_tools:
                args = {"start_date": "2026-08-01", "end_date": "2026-08-28", "limit": 10}
                if top_query_extracted:
                    args["query_filter"] = top_query_extracted
                return {
                    "action": "tool",
                    "tool_name": "gsc_top_pages",
                    "arguments": args,
                    "reason": f"Retrieve landing pages ranking for '{top_query_extracted or 'top queries'}' to evaluate CTR and cannibalization."
                }

            # 3. Run GSC opportunity audit
            if 'gsc_opportunity_audit' not in tool_calls and 'gsc_opportunity_audit' in available_tools:
                return {
                    "action": "tool",
                    "tool_name": "gsc_opportunity_audit",
                    "arguments": {"min_impressions": 10, "sync_to_insights": True},
                    "reason": "Run GSC intelligence heuristics to detect Page 2 opportunities, SERP low-CTR snippets, and cannibalization."
                }

            # Fallback inspection if live GSC tools not in available tools
            if not tool_calls and 'get_search_console_analytics' in available_tools:
                return {
                    "action": "tool",
                    "tool_name": "get_search_console_analytics",
                    "arguments": {"min_impressions": 100, "limit": 10},
                    "reason": "Inspect stored Search Console queries to find low-CTR targets."
                }

            if 'run_intelligence_analysis' not in tool_calls and 'gsc_opportunity_audit' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "run_intelligence_analysis",
                    "arguments": {},
                    "reason": "Run SEO intelligence heuristic analysis to generate fresh anomaly and opportunity insights."
                }

            if 'generate_recommendation' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "generate_recommendation",
                    "arguments": {"insight_id": insight_id or 1},
                    "reason": "Generate grounded AI strategy recommendation for highest-impact GSC search opportunity."
                }

            if 'generate_content_brief' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "generate_content_brief",
                    "arguments": {"recommendation_id": rec_id or 1, "content_type": "blog_post"},
                    "reason": "Synthesize content brief with optimized headings, secondary keywords, and SERP snippet copy."
                }

            if 'generate_content_draft' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "generate_content_draft",
                    "arguments": {"content_brief_id": brief_id or 1},
                    "reason": "Draft full-length optimized content with schema markup and keyword density mapping."
                }

            if 'propose_seo_action' not in tool_calls:
                return {
                    "action": "tool",
                    "tool_name": "propose_seo_action",
                    "arguments": {"source_type": "draft", "source_id": draft_id or 1},
                    "reason": "Create formal SEOAction proposal for human review and approval."
                }

            return {
                "action": "finish",
                "summary": (
                    f"Successfully completed autonomous GSC intelligence workflow for goal: \"{context.get('goal', '')}\". "
                    "Retrieved live search analytics, identified high-impact Page 2 and CTR opportunities, synthesized grounded recommendations, "
                    "drafted full content optimizations, and submitted a formal proposal for human approval."
                )
            }

        # ---------------------------------------------------------------------
        # BRANCH 3: Technical Audit / Crawl Diagnostics Goal
        # ---------------------------------------------------------------------
        # 1. First Step: Inspection
        if not tool_calls:
            if any(term in goal for term in ['audit', 'technical', 'issue', 'health', 'broken']):
                return {
                    "action": "tool",
                    "tool_name": "get_audit_issues",
                    "arguments": {"severity": "warning", "limit": 10},
                    "reason": "Inspect site audit diagnostics to locate technical SEO issues and crawl bottlenecks."
                }
            else:
                return {
                    "action": "tool",
                    "tool_name": "get_keyword_rankings",
                    "arguments": {"limit": 10},
                    "reason": "Query current tracked keyword ranking positions to evaluate baseline search visibility."
                }

        # 2. Second Step: Intelligence Heuristic Run
        if 'run_intelligence_analysis' not in tool_calls:
            return {
                "action": "tool",
                "tool_name": "run_intelligence_analysis",
                "arguments": {},
                "reason": "Run SEO intelligence heuristic analysis to generate fresh anomaly and opportunity insights."
            }

        # 3. Third Step: Generate Recommendation
        if 'generate_recommendation' not in tool_calls:
            return {
                "action": "tool",
                "tool_name": "generate_recommendation",
                "arguments": {"insight_id": insight_id or 1},
                "reason": "Generate grounded AI strategy recommendation for the highest-priority identified insight."
            }

        # 4. Fourth Step: Generate Content Brief
        if 'generate_content_brief' not in tool_calls:
            return {
                "action": "tool",
                "tool_name": "generate_content_brief",
                "arguments": {"recommendation_id": rec_id or 1, "content_type": "blog_post"},
                "reason": "Synthesize comprehensive SEO content brief with topical outline, secondary keywords, and FAQs."
            }

        # 5. Fifth Step: Generate Content Draft
        if 'generate_content_draft' not in tool_calls:
            return {
                "action": "tool",
                "tool_name": "generate_content_draft",
                "arguments": {"content_brief_id": brief_id or 1},
                "reason": "Write full-length publishable SEO article draft with schema markup and keyword density mapping."
            }

        # 6. Sixth Step: Propose SEO Action
        if 'propose_seo_action' not in tool_calls:
            return {
                "action": "tool",
                "tool_name": "propose_seo_action",
                "arguments": {"source_type": "draft", "source_id": draft_id or 1},
                "reason": "Create formal SEOAction proposal for human review and approval."
            }

        # 7. Final Step: Finish
        return {
            "action": "finish",
            "summary": (
                f"Successfully completed autonomous SEO workflow for goal: \"{context.get('goal', '')}\". "
                "Retrieved baseline rankings, executed intelligence heuristics, generated grounded recommendations, "
                "synthesized a structured content brief, drafted publication copy, and created a formal SEO Action proposal for human approval."
            )
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

    def generate_content_brief(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockAIProvider.")
            return MockAIProvider().generate_content_brief(context)

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": CONTENT_BRIEF_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Generate a comprehensive, actionable SEO Content Brief for the following context:\n{json.dumps(context, indent=2)}"
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
            logger.error(f"OpenAI API content brief generation failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider().generate_content_brief(context)

    def generate_content_draft(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockAIProvider.")
            return MockAIProvider().generate_content_draft(context)

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": CONTENT_DRAFT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Generate a complete, high-quality, publish-ready SEO Content Draft for the following brief context:\n{json.dumps(context, indent=2)}"
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

            with urllib.request.urlopen(req, timeout=35) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                content_str = res_data['choices'][0]['message']['content']
                parsed = json.loads(content_str)
                return parsed

        except Exception as e:
            logger.error(f"OpenAI API content draft generation failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider().generate_content_draft(context)

    def generate_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockAIProvider.")
            return MockAIProvider().generate_action(context)

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": ACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Generate a complete, structured executable SEO action for the following context:\n{json.dumps(context, indent=2)}"
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
            logger.error(f"OpenAI API action generation failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider().generate_action(context)

    def decide_agent_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not configured; falling back to MockAIProvider.")
            return MockAIProvider().decide_agent_action(context)

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": AGENT_DECISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Given the following goal, execution history, and available tools, decide the next action:\n{json.dumps(context, indent=2)}"
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
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
            logger.error(f"OpenAI API agent decision failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider().decide_agent_action(context)


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

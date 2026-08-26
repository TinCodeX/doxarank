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
            "faq_questions": [
                {
                    "question": f"How do I get started with {kw_clean}?",
                    "answer_guidance": "Begin with a baseline audit, establish measurable goals, and follow the step-by-step implementation guide."
                },
                {
                    "question": f"What are the most common mistakes in {kw_clean}?",
                    "answer_guidance": "Failing to align with user intent, neglecting mobile performance, and ignoring analytical feedback."
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


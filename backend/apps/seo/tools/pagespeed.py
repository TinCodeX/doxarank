"""
DoxaRank PageSpeed / Core Web Vitals Analyzer (Tool 8).

Integrates with the official Google PageSpeed Insights REST API v5:
https://www.googleapis.com/pagespeedonline/v5/runPagespeed

Extracts Lighthouse audit categories (Performance, Accessibility, Best Practices, SEO)
and Core Web Vitals metrics (LCP, FID/INP, CLS, FCP, TTFB).

Security & Configuration:
- Server-side API key configuration via PAGESPEED_API_KEY / GOOGLE_PAGESPEED_API_KEY.
- Never exposes secrets to frontend.
- Validates URLs against SSRF before making external outbound requests.
- Enforces strict timeout and structured error handling.
- Never fabricates fake scores.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

import httpx
from django.conf import settings
from apps.seo.services.external_adapters.base import is_safe_target_url

logger = logging.getLogger(__name__)

PAGESPEED_API_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DEFAULT_TIMEOUT_SECONDS = 25.0


def get_pagespeed_api_key() -> Optional[str]:
    """Retrieve PageSpeed API key from Django settings or environment."""
    return (
        getattr(settings, 'PAGESPEED_API_KEY', None)
        or getattr(settings, 'GOOGLE_PAGESPEED_API_KEY', None)
        or os.environ.get('PAGESPEED_API_KEY')
        or os.environ.get('GOOGLE_PAGESPEED_API_KEY')
    )


class PageSpeedAnalyzer:
    """
    Domain service for Tool 8: PageSpeed / Core Web Vitals Analyzer.
    """

    @classmethod
    def analyze(
        cls,
        url: str,
        strategy: str = 'mobile',
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> Dict[str, Any]:
        """
        Validates target URL and queries the Google PageSpeed Insights REST API.
        Returns parsed categories and Core Web Vitals metrics.
        """
        url = (url or '').strip()
        strategy = (strategy or 'mobile').lower().strip()

        if not url:
            raise ValueError("Target webpage URL is required for PageSpeed analysis.")

        if strategy not in ('mobile', 'desktop'):
            raise ValueError("Strategy must be either 'mobile' or 'desktop'.")

        # 1. Anti-SSRF validation
        is_safe, error_msg = is_safe_target_url(url)
        if not is_safe:
            raise ValueError(f"Invalid target URL: {error_msg}")

        key = api_key or get_pagespeed_api_key()

        # 2. Build request parameters
        params = {
            'url': url,
            'strategy': strategy,
            'category': ['performance', 'accessibility', 'best-practices', 'seo'],
        }
        if key:
            params['key'] = key

        # 3. Execute external HTTP request to Google PageSpeed Insights
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(PAGESPEED_API_ENDPOINT, params=params)

                if response.status_code == 400:
                    try:
                        err_json = response.json()
                        msg = err_json.get('error', {}).get('message', 'Invalid URL or parameter.')
                    except Exception:
                        msg = response.text[:200]
                    raise ValueError(f"PageSpeed API rejected request: {msg}")

                if response.status_code == 429:
                    raise RuntimeError("PageSpeed API rate limit reached (HTTP 429). Please retry later.")

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Google PageSpeed API returned HTTP {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
        except httpx.TimeoutException:
            raise RuntimeError(f"PageSpeed API timed out after {timeout} seconds.")
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            logger.error("PageSpeed request failed: %s", str(e), exc_info=True)
            raise RuntimeError(f"Failed to communicate with Google PageSpeed API: {str(e)}")

        # 4. Parse response data
        return cls._parse_pagespeed_response(url, strategy, data)

    @classmethod
    def _parse_pagespeed_response(cls, url: str, strategy: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts categories, Core Web Vitals, and diagnostics from raw PageSpeed API v5 response.
        """
        lighthouse = data.get('lighthouseResult')
        if not lighthouse or not isinstance(lighthouse, dict):
            raise RuntimeError("Malformed response from Google PageSpeed API: missing 'lighthouseResult'.")
        categories = lighthouse.get('categories', {})
        audits = lighthouse.get('audits', {})
        loading_experience = data.get('loadingExperience', {})
        metrics_crux = loading_experience.get('metrics', {})

        # Scores (0 - 100)
        perf_score = None
        if 'performance' in categories and categories['performance'].get('score') is not None:
            perf_score = int(round(categories['performance']['score'] * 100))

        acc_score = None
        if 'accessibility' in categories and categories['accessibility'].get('score') is not None:
            acc_score = int(round(categories['accessibility']['score'] * 100))

        bp_score = None
        if 'best-practices' in categories and categories['best-practices'].get('score') is not None:
            bp_score = int(round(categories['best-practices']['score'] * 100))

        seo_score = None
        if 'seo' in categories and categories['seo'].get('score') is not None:
            seo_score = int(round(categories['seo']['score'] * 100))

        # Core Web Vitals extraction helper
        def extract_audit(audit_id: str) -> Dict[str, Any]:
            a = audits.get(audit_id, {})
            numeric = a.get('numericValue')
            display = a.get('displayValue', 'N/A')
            score = a.get('score')

            # Assess status based on score (1.0 = good, 0.5-0.89 = needs improvement, <0.5 = poor)
            if score is not None:
                if score >= 0.9:
                    eval_status = 'good'
                elif score >= 0.5:
                    eval_status = 'needs-improvement'
                else:
                    eval_status = 'poor'
            else:
                eval_status = 'unknown'

            return {
                'id': audit_id,
                'title': a.get('title', audit_id),
                'display_value': display,
                'numeric_value': round(numeric, 2) if numeric is not None else None,
                'score': score,
                'status': eval_status,
                'description': a.get('description', ''),
            }

        # Core Web Vitals
        lcp = extract_audit('largest-contentful-paint')
        cls_metric = extract_audit('cumulative-layout-shift')
        fcp = extract_audit('first-contentful-paint')
        ttfb = extract_audit('server-response-time')
        tbt = extract_audit('total-blocking-time')
        speed_index = extract_audit('speed-index')

        # FID / INP
        fid_inp = None
        if 'max-potential-fid' in audits:
            fid_inp = extract_audit('max-potential-fid')
        elif 'interaction-to-next-paint' in audits:
            fid_inp = extract_audit('interaction-to-next-paint')

        # Extract Opportunities / Diagnostics
        diagnostics: List[Dict[str, Any]] = []
        opportunity_ids = [
            'render-blocking-resources',
            'unminified-css',
            'unminified-javascript',
            'unused-css-rules',
            'unused-javascript',
            'uses-optimized-images',
            'modern-image-formats',
            'uses-text-compression',
            'efficient-animated-content',
        ]
        for opp_id in opportunity_ids:
            if opp_id in audits:
                a = audits[opp_id]
                score = a.get('score')
                if score is not None and score < 1.0:
                    diagnostics.append({
                        'id': opp_id,
                        'title': a.get('title', opp_id),
                        'display_value': a.get('displayValue', ''),
                        'description': a.get('description', ''),
                        'score': score,
                    })

        return {
            'url': url,
            'strategy': strategy,
            'fetch_time': lighthouse.get('fetchTime', ''),
            'lighthouse_version': lighthouse.get('lighthouseVersion', ''),
            'performance_score': perf_score,
            'accessibility_score': acc_score,
            'best_practices_score': bp_score,
            'seo_score': seo_score,
            'scores': {
                'performance': perf_score,
                'accessibility': acc_score,
                'best_practices': bp_score,
                'seo': seo_score,
            },
            'metrics': {
                'lcp': lcp,
                'fid': fid_inp,
                'inp': fid_inp,
                'cls': cls_metric,
                'fcp': fcp,
                'ttfb': ttfb,
                'tbt': tbt,
                'speed_index': speed_index,
            },
            'core_web_vitals': {
                'lcp': lcp,
                'fid_inp': fid_inp,
                'cls': cls_metric,
                'fcp': fcp,
                'ttfb': ttfb,
                'tbt': tbt,
                'speed_index': speed_index,
            },
            'crux_summary': {
                'overall_category': loading_experience.get('overall_category', 'UNKNOWN'),
                'metrics': metrics_crux,
            },
            'crux_metrics': {
                'overall_category': loading_experience.get('overall_category', 'UNKNOWN'),
                **metrics_crux,
            },
            'diagnostics': diagnostics[:6],  # Top actionable diagnostics
        }

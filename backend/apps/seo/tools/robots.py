import re
import urllib.robotparser
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


DEFAULT_USER_AGENTS = [
    '*',
    'Googlebot',
    'Bingbot',
    'Baiduspider',
    'YandexBot',
    'DuckDuckBot',
    'Slurp',
    'facebookexternalhit',
    'Twitterbot',
]


def _validate_url(url: Optional[str], field_name: str) -> Optional[str]:
    url = (url or '').strip()
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f"'{field_name}' must be a valid HTTP or HTTPS URL (got '{url}').")
    return url


def _validate_path(path: str) -> str:
    path = (path or '').strip()
    if not path:
        return ''
    if not path.startswith('/'):
        raise ValueError(f"Robots directive path must start with '/' (got '{path}').")
    return path


class RobotsTxtGenerator:
    """
    Deterministic Robots.txt Generator and Formatter.
    Assembles clean, RFC-compliant robots.txt files with validation and linting.
    """

    @classmethod
    def generate(
        cls,
        groups: List[Dict[str, Any]],
        sitemaps: Optional[List[str]] = None,
        host: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not groups or not isinstance(groups, list):
            raise ValueError("Robots.txt requires at least one rule group.")

        lines: List[str] = []
        warnings: List[str] = []
        parsed_groups: List[Dict[str, Any]] = []

        for idx, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                raise ValueError(f"Rule group #{idx} must be an object.")

            user_agent = (group.get('user_agent') or '*').strip()
            if not user_agent:
                raise ValueError(f"Rule group #{idx} is missing 'user_agent'.")

            disallows = group.get('disallow') or []
            if isinstance(disallows, str):
                disallows = [d.strip() for d in disallows.split('\n') if d.strip()]

            allows = group.get('allow') or []
            if isinstance(allows, str):
                allows = [a.strip() for a in allows.split('\n') if a.strip()]

            crawl_delay = group.get('crawl_delay')

            # Clean and validate paths
            cleaned_disallows = []
            for d in disallows:
                d_clean = _validate_path(d)
                cleaned_disallows.append(d_clean)

            cleaned_allows = []
            for a in allows:
                a_clean = _validate_path(a)
                cleaned_allows.append(a_clean)

            # Check for conflicting rules
            for dis in cleaned_disallows:
                if dis and dis in cleaned_allows:
                    warnings.append(f"Rule group '{user_agent}' has identical Allow and Disallow for '{dis}'.")

            # Check full-site blocking
            if '/' in cleaned_disallows and not cleaned_allows:
                warnings.append(f"Rule group '{user_agent}' disallows '/' (blocks entire site from crawling).")

            parsed_groups.append({
                'user_agent': user_agent,
                'disallow': cleaned_disallows,
                'allow': cleaned_allows,
                'crawl_delay': crawl_delay,
            })

            # Append to text output
            lines.append(f"User-agent: {user_agent}")
            for d in cleaned_disallows:
                lines.append(f"Disallow: {d}")
            for a in cleaned_allows:
                lines.append(f"Allow: {a}")
            if crawl_delay is not None and str(crawl_delay).strip():
                try:
                    delay_val = float(str(crawl_delay).strip())
                    lines.append(f"Crawl-delay: {int(delay_val) if delay_val.is_integer() else delay_val}")
                except ValueError:
                    warnings.append(f"Ignored invalid crawl-delay '{crawl_delay}' in group '{user_agent}'.")

            lines.append("")  # Blank line between groups

        # Sitemaps
        cleaned_sitemaps: List[str] = []
        if sitemaps:
            if isinstance(sitemaps, str):
                sitemaps = [s.strip() for s in sitemaps.split('\n') if s.strip()]
            for s in sitemaps:
                val = _validate_url(s, "Sitemap")
                if val:
                    cleaned_sitemaps.append(val)
                    lines.append(f"Sitemap: {val}")

        # Host
        if host and str(host).strip():
            clean_host = str(host).strip().lower()
            if '://' in clean_host:
                clean_host = urlparse(clean_host).netloc
            lines.append(f"Host: {clean_host}")

        robots_content = "\n".join(lines).strip() + "\n"

        return {
            'content': robots_content,
            'groups': parsed_groups,
            'sitemaps': cleaned_sitemaps,
            'warnings': warnings,
            'metrics': {
                'group_count': len(parsed_groups),
                'sitemap_count': len(cleaned_sitemaps),
                'lines_count': len(robots_content.strip().splitlines()),
            }
        }


class RobotsTxtTester:
    """
    Deterministic, SSRF-safe Robots.txt parser and URL path access evaluator.
    Uses standard RobotFileParser logic to determine whether a given path is Allowed or Blocked.
    """

    @classmethod
    def test(
        cls,
        robots_content: str,
        path: str,
        user_agent: str = '*',
    ) -> Dict[str, Any]:
        robots_content = (robots_content or '').strip()
        path = (path or '').strip()
        user_agent = (user_agent or '*').strip()

        if not robots_content:
            raise ValueError("Robots.txt content is required to test access.")
        if not path:
            raise ValueError("Path or URL to test is required.")

        # Extract normalized test path
        parsed = urlparse(path)
        test_path = parsed.path if parsed.scheme else path
        if not test_path.startswith('/'):
            test_path = f"/{test_path}"

        dummy_base = "https://example.com"
        dummy_full_url = f"{dummy_base}{test_path}"

        # Parse using standard urllib.robotparser
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(robots_content.splitlines())

        can_fetch = parser.can_fetch(user_agent, dummy_full_url)

        # Inspect matching line for clarity
        matched_rule = None
        current_agent_matches = False
        matching_lines: List[str] = []

        for raw_line in robots_content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            lower_line = line.lower()
            if lower_line.startswith('user-agent:'):
                agent_val = line.split(':', 1)[1].strip()
                current_agent_matches = (agent_val == '*' or agent_val.lower() == user_agent.lower())
            elif current_agent_matches:
                if lower_line.startswith('disallow:') or lower_line.startswith('allow:'):
                    prefix = line.split(':', 1)[1].strip()
                    if prefix and test_path.startswith(prefix):
                        matching_lines.append(line)

        if matching_lines:
            # Last or most specific directive usually governs
            matched_rule = matching_lines[-1]

        reason = (
            f"Allowed by default (no blocking rules matched for '{user_agent}')"
            if can_fetch
            else f"Blocked by directive '{matched_rule or 'Disallow'}' for user-agent '{user_agent}'"
        )

        return {
            'allowed': can_fetch,
            'status': 'ALLOWED' if can_fetch else 'BLOCKED',
            'user_agent': user_agent,
            'test_path': test_path,
            'matched_rule': matched_rule,
            'reason': reason,
        }

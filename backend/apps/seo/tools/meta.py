import html
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


SUPPORTED_ROBOTS_DIRECTIVES = [
    'index, follow',
    'noindex, follow',
    'index, nofollow',
    'noindex, nofollow',
]


class MetaTagGenerator:
    """
    Deterministic HTML Meta Tag Generator.
    Generates semantic, valid, and HTML-escaped meta tags with SEO length guidance.
    """

    @classmethod
    def generate(
        cls,
        title: str,
        description: str,
        canonical_url: Optional[str] = None,
        robots: str = 'index, follow',
        author: Optional[str] = None,
        keywords: Optional[str] = None,
        viewport: str = 'width=device-width, initial-scale=1.0',
    ) -> Dict[str, Any]:
        """
        Validate inputs and assemble safe HTML tags.
        """
        title = (title or '').strip()
        description = (description or '').strip()
        canonical_url = (canonical_url or '').strip() or None
        robots = (robots or 'index, follow').strip().lower()
        author = (author or '').strip() or None
        keywords = (keywords or '').strip() or None
        viewport = (viewport or 'width=device-width, initial-scale=1.0').strip()

        # Validation
        if not title:
            raise ValueError("Page title is required.")
        if not description:
            raise ValueError("Meta description is required.")

        if robots not in SUPPORTED_ROBOTS_DIRECTIVES:
            raise ValueError(
                f"Unsupported robots directive '{robots}'. Must be one of: {', '.join(SUPPORTED_ROBOTS_DIRECTIVES)}"
            )

        if canonical_url:
            parsed = urlparse(canonical_url)
            if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise ValueError("Canonical URL must be a valid HTTP or HTTPS URL (e.g. https://example.com/page).")

        # HTML Escaping for safe attributes and content
        escaped_title = html.escape(title, quote=True)
        escaped_desc = html.escape(description, quote=True)
        escaped_robots = html.escape(robots, quote=True)
        escaped_viewport = html.escape(viewport, quote=True)
        escaped_canonical = html.escape(canonical_url, quote=True) if canonical_url else None
        escaped_author = html.escape(author, quote=True) if author else None
        escaped_keywords = html.escape(keywords, quote=True) if keywords else None

        # Build clean tags list
        tags: List[str] = [
            f'<title>{escaped_title}</title>',
            f'<meta name="description" content="{escaped_desc}">',
            f'<meta name="robots" content="{escaped_robots}">',
            f'<meta name="viewport" content="{escaped_viewport}">',
        ]

        if escaped_canonical:
            tags.append(f'<link rel="canonical" href="{escaped_canonical}">')
        if escaped_author:
            tags.append(f'<meta name="author" content="{escaped_author}">')
        if escaped_keywords:
            tags.append(f'<meta name="keywords" content="{escaped_keywords}">')

        html_output = "\n".join(tags)

        # Character length guidance & warnings
        warnings: List[str] = []
        title_len = len(title)
        desc_len = len(description)

        if title_len < 30:
            warnings.append(f"Title is short ({title_len} chars). Recommended: 50–60 characters for optimal SERP visibility.")
        elif title_len > 60:
            warnings.append(f"Title may be truncated on Google ({title_len} chars). Recommended: 50–60 characters.")

        if desc_len < 70:
            warnings.append(f"Meta description is short ({desc_len} chars). Recommended: 150–160 characters to maximize CTR.")
        elif desc_len > 160:
            warnings.append(f"Meta description exceeds standard SERP snippet length ({desc_len} chars). Recommended: 150–160 characters.")

        return {
            'html': html_output,
            'tags': tags,
            'metrics': {
                'title_length': title_len,
                'title_status': 'optimal' if 30 <= title_len <= 60 else ('too_short' if title_len < 30 else 'too_long'),
                'description_length': desc_len,
                'description_status': 'optimal' if 70 <= desc_len <= 160 else ('too_short' if desc_len < 70 else 'too_long'),
            },
            'warnings': warnings,
        }

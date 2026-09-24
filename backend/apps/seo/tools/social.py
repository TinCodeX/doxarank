import html
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


SUPPORTED_OG_TYPES = [
    'website',
    'article',
    'book',
    'profile',
]

SUPPORTED_TWITTER_CARDS = [
    'summary_large_image',
    'summary',
]


def _validate_url(url: Optional[str], field_name: str, required: bool = False) -> Optional[str]:
    url = (url or '').strip()
    if not url:
        if required:
            raise ValueError(f"'{field_name}' URL is required.")
        return None
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f"'{field_name}' must be a valid HTTP or HTTPS URL (e.g. https://example.com/image.jpg).")
    return url


class SocialPreviewGenerator:
    """
    Deterministic Open Graph and Twitter/X Card tag generator and preview model.
    SSRF-safe: strictly formats and validates provided metadata without external fetching.
    """

    @classmethod
    def generate(
        cls,
        title: str,
        description: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        site_name: Optional[str] = None,
        og_type: str = 'website',
        twitter_card: str = 'summary_large_image',
        twitter_site: Optional[str] = None,
        twitter_creator: Optional[str] = None,
    ) -> Dict[str, Any]:
        title = (title or '').strip()
        description = (description or '').strip()
        site_name = (site_name or '').strip() or None
        og_type = (og_type or 'website').strip().lower()
        twitter_card = (twitter_card or 'summary_large_image').strip().lower()
        twitter_site = (twitter_site or '').strip() or None
        twitter_creator = (twitter_creator or '').strip() or None

        # Validation
        if not title:
            raise ValueError("Title is required for social preview.")
        if not description:
            raise ValueError("Description is required for social preview.")

        if og_type not in SUPPORTED_OG_TYPES:
            raise ValueError(
                f"Unsupported Open Graph type '{og_type}'. Must be one of: {', '.join(SUPPORTED_OG_TYPES)}"
            )

        if twitter_card not in SUPPORTED_TWITTER_CARDS:
            raise ValueError(
                f"Unsupported Twitter card type '{twitter_card}'. Must be one of: {', '.join(SUPPORTED_TWITTER_CARDS)}"
            )

        validated_url = _validate_url(url, 'Target URL')
        validated_image_url = _validate_url(image_url, 'Image URL')

        # Clean twitter handles
        if twitter_site and not twitter_site.startswith('@'):
            twitter_site = f"@{twitter_site}"
        if twitter_creator and not twitter_creator.startswith('@'):
            twitter_creator = f"@{twitter_creator}"

        # Extract domain for display in cards
        domain = 'example.com'
        if validated_url:
            domain = urlparse(validated_url).netloc

        # HTML Escaping for meta tags
        esc_title = html.escape(title, quote=True)
        esc_desc = html.escape(description, quote=True)
        esc_og_type = html.escape(og_type, quote=True)
        esc_twitter_card = html.escape(twitter_card, quote=True)
        esc_url = html.escape(validated_url, quote=True) if validated_url else None
        esc_image = html.escape(validated_image_url, quote=True) if validated_image_url else None
        esc_site_name = html.escape(site_name, quote=True) if site_name else None
        esc_twitter_site = html.escape(twitter_site, quote=True) if twitter_site else None
        esc_twitter_creator = html.escape(twitter_creator, quote=True) if twitter_creator else None

        # Build Open Graph tags
        og_tags: List[str] = [
            f'<meta property="og:title" content="{esc_title}">',
            f'<meta property="og:description" content="{esc_desc}">',
            f'<meta property="og:type" content="{esc_og_type}">',
        ]
        if esc_url:
            og_tags.append(f'<meta property="og:url" content="{esc_url}">')
        if esc_image:
            og_tags.append(f'<meta property="og:image" content="{esc_image}">')
        if esc_site_name:
            og_tags.append(f'<meta property="og:site_name" content="{esc_site_name}">')

        # Build Twitter / X Card tags
        twitter_tags: List[str] = [
            f'<meta name="twitter:card" content="{esc_twitter_card}">',
            f'<meta name="twitter:title" content="{esc_title}">',
            f'<meta name="twitter:description" content="{esc_desc}">',
        ]
        if esc_image:
            twitter_tags.append(f'<meta name="twitter:image" content="{esc_image}">')
        if esc_twitter_site:
            twitter_tags.append(f'<meta name="twitter:site" content="{esc_twitter_site}">')
        if esc_twitter_creator:
            twitter_tags.append(f'<meta name="twitter:creator" content="{esc_twitter_creator}">')

        all_tags = og_tags + twitter_tags
        html_output = "\n".join(all_tags)

        # Guidance & warnings
        warnings: List[str] = []
        if len(title) > 60:
            warnings.append(f"Social title is {len(title)} chars (optimal is under 60-70 chars to prevent truncation).")
        if len(description) > 160:
            warnings.append(f"Social description is {len(description)} chars (optimal is under 150-160 chars).")
        if not validated_image_url:
            warnings.append("No image URL provided. Social platforms will display text-only or fallback to site icons.")

        return {
            'html': html_output,
            'tags': all_tags,
            'og_tags': og_tags,
            'twitter_tags': twitter_tags,
            'preview': {
                'title': title,
                'description': description,
                'url': validated_url or 'https://example.com/page',
                'domain': domain,
                'image_url': validated_image_url,
                'site_name': site_name or domain,
                'og_type': og_type,
                'twitter_card': twitter_card,
                'twitter_site': twitter_site,
            },
            'metrics': {
                'title_length': len(title),
                'description_length': len(description),
                'has_image': bool(validated_image_url),
                'has_url': bool(validated_url),
            },
            'warnings': warnings,
        }

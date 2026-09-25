"""
DoxaRank SERP Snippet Preview / Pixel-Length Checker (Tool 7).

Deterministic Google SERP preview simulator and pixel/character width counter.
Simulates desktop and mobile search snippet cards without making external requests.

Typography standards modeled:
- Google Desktop:
  * Title font: Arial 20px, line-height ~26px. Maximum cutoff width: ~600px.
  * Snippet font: Arial 14px, line-height ~20px. Maximum cutoff width: ~960px.
  * Guidance: Title ~30–60 characters; Description ~70–160 characters.
- Google Mobile:
  * Title display width: ~580px (~50–55 characters).
  * Description display width: ~680px (~120 characters).
"""

from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

# Deterministic character width map approximating Arial at 20px font-size.
# Standard character measurements in CSS pixels (approximate Google rendering):
# Narrow characters (i, l, |, etc.) ~4-6px
# Average lowercase ~8-12px
# Uppercase / digits ~12-16px
# Wide characters (M, W, @) ~17-20px
# Non-ASCII / Ge'ez / CJK standard fallback ~15px
ARIAL_20PX_WIDTHS: Dict[str, float] = {
    ' ': 5.5, '!': 5.5, '"': 7.1, '#': 11.1, '$': 11.1, '%': 17.8, '&': 13.3, "'": 3.9,
    '(': 6.7, ')': 6.7, '*': 7.8, '+': 11.7, ',': 5.5, '-': 6.7, '.': 5.5, '/': 5.5,
    '0': 11.1, '1': 11.1, '2': 11.1, '3': 11.1, '4': 11.1, '5': 11.1, '6': 11.1, '7': 11.1,
    '8': 11.1, '9': 11.1, ':': 5.5, ';': 5.5, '<': 11.7, '=': 11.7, '>': 11.7, '?': 11.1,
    '@': 20.3,
    'A': 13.3, 'B': 13.3, 'C': 14.4, 'D': 14.4, 'E': 13.3, 'F': 12.2, 'G': 15.5, 'H': 14.4,
    'I': 5.5, 'J': 10.0, 'K': 13.3, 'L': 11.1, 'M': 16.7, 'N': 14.4, 'O': 15.5, 'P': 13.3,
    'Q': 15.5, 'R': 14.4, 'S': 13.3, 'T': 12.2, 'U': 14.4, 'V': 13.3, 'W': 18.9, 'X': 13.3,
    'Y': 13.3, 'Z': 12.2, '[': 5.5, '\\': 5.5, ']': 5.5, '^': 11.7, '_': 11.1, '`': 6.7,
    'a': 11.1, 'b': 11.1, 'c': 10.0, 'd': 11.1, 'e': 11.1, 'f': 5.5, 'g': 11.1, 'h': 11.1,
    'i': 4.4, 'j': 4.4, 'k': 10.0, 'l': 4.4, 'm': 16.7, 'n': 11.1, 'o': 11.1, 'p': 11.1,
    'q': 11.1, 'r': 6.7, 's': 10.0, 't': 5.5, 'u': 11.1, 'v': 10.0, 'w': 14.4, 'x': 10.0,
    'y': 10.0, 'z': 10.0, '{': 6.7, '|': 5.5, '}': 6.7, '~': 11.7,
    '—': 19.0, '–': 11.1, '…': 16.5, '•': 7.0, '›': 6.0,
}

# Scale factor for Arial 14px (description font size vs 20px title font size)
DESC_SCALE_FACTOR: float = 14.0 / 20.0

# Device limits (CSS pixels)
LIMITS = {
    'desktop': {
        'title_max_px': 600.0,
        'title_min_chars': 30,
        'title_max_chars': 60,
        'desc_max_px': 960.0,
        'desc_min_chars': 70,
        'desc_max_chars': 160,
    },
    'mobile': {
        'title_max_px': 580.0,
        'title_min_chars': 25,
        'title_max_chars': 55,
        'desc_max_px': 680.0,
        'desc_min_chars': 60,
        'desc_max_chars': 120,
    }
}


def calculate_pixel_width(text: str, is_title: bool = True) -> float:
    """
    Deterministically computes approximate pixel width using Arial typography metrics.
    is_title=True uses Arial 20px metrics.
    is_title=False uses Arial 14px metrics (scaled by DESC_SCALE_FACTOR).
    """
    if not text:
        return 0.0

    scale = 1.0 if is_title else DESC_SCALE_FACTOR
    default_char_width = 11.0 * scale  # standard average character fallback

    total_px = 0.0
    for char in text:
        if char in ARIAL_20PX_WIDTHS:
            total_px += ARIAL_20PX_WIDTHS[char] * scale
        else:
            total_px += default_char_width

    return total_px


def truncate_to_pixels(text: str, max_px: float, is_title: bool = True) -> tuple[str, bool, float]:
    """
    Truncates text to fit within max_px, appending '...' if truncated.
    Returns: (rendered_text, is_truncated, final_pixel_width)
    """
    total_px = calculate_pixel_width(text, is_title=is_title)
    if total_px <= max_px:
        return text, False, total_px

    ellipsis = "..."
    ellipsis_px = calculate_pixel_width(ellipsis, is_title=is_title)

    truncated = ""
    current_px = 0.0
    for char in text:
        char_px = (ARIAL_20PX_WIDTHS.get(char, 11.0) * (1.0 if is_title else DESC_SCALE_FACTOR))
        if current_px + char_px + ellipsis_px > max_px:
            break
        truncated += char
        current_px += char_px

    rendered = truncated.rstrip() + ellipsis
    final_px = calculate_pixel_width(rendered, is_title=is_title)
    return rendered, True, final_px


def format_serp_breadcrumb(url: str) -> str:
    """Formats URL into realistic Google-style breadcrumbs (e.g. example.com › blog › post)."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        domain = parsed.netloc or parsed.path.split('/')[0]
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        if not path_parts:
            return f"https://{domain}" if domain else url
        return f"https://{domain} › " + " › ".join(path_parts)
    except Exception:
        return url


class SerpSnippetAnalyzer:
    """
    Domain service for Tool 7: SERP Snippet Preview / Pixel-Length Checker.
    Performs purely deterministic calculation of title/description pixel lengths and preview simulation.
    """

    @classmethod
    def analyze(
        cls,
        title: str,
        description: str,
        url: str,
        device: str = 'desktop'
    ) -> Dict[str, Any]:
        """
        Validates input and computes deterministic SERP preview metrics.
        """
        title = (title or '').strip()
        description = (description or '').strip()
        url = (url or '').strip()
        device = (device or 'desktop').lower().strip()

        if not title:
            raise ValueError("Page title is required for SERP snippet preview.")
        if not description:
            raise ValueError("Meta description is required for SERP snippet preview.")
        if not url:
            raise ValueError("Page URL is required for SERP snippet preview.")
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ('http', 'https'):
            raise ValueError(f"URL must have a valid 'http' or 'https' scheme (got '{parsed_url.scheme}').")
        if device not in ('desktop', 'mobile'):
            raise ValueError("Device must be either 'desktop' or 'mobile'.")

        cfg = LIMITS[device]

        # 1. Title analysis
        title_raw_px = calculate_pixel_width(title, is_title=True)
        rendered_title, title_truncated, title_final_px = truncate_to_pixels(
            title, cfg['title_max_px'], is_title=True
        )

        # 2. Description analysis
        desc_raw_px = calculate_pixel_width(description, is_title=False)
        rendered_desc, desc_truncated, desc_final_px = truncate_to_pixels(
            description, cfg['desc_max_px'], is_title=False
        )

        # 3. Breadcrumb
        breadcrumb = format_serp_breadcrumb(url)

        # 4. Warnings and guidance
        warnings: List[str] = []

        # Title evaluation
        title_len = len(title)
        if title_truncated or title_raw_px > cfg['title_max_px']:
            title_status = 'truncated'
            warnings.append(
                f"Title exceeds the approximate {int(cfg['title_max_px'])}px width limit for {device} "
                f"({round(title_raw_px, 1)}px, {title_len} chars) and will likely be truncated with an ellipsis on Google."
            )
        elif title_len < cfg['title_min_chars']:
            title_status = 'short'
            warnings.append(
                f"Title is short ({title_len} characters). Google recommends between "
                f"{cfg['title_min_chars']}–{cfg['title_max_chars']} characters to maximize CTR."
            )
        elif title_len > cfg['title_max_chars']:
            title_status = 'warning'
            warnings.append(
                f"Title has {title_len} characters (recommended: {cfg['title_min_chars']}–{cfg['title_max_chars']}). "
                f"While it fits in {cfg['title_max_px']}px, it is close to the cutoff."
            )
        else:
            title_status = 'optimal'

        # Description evaluation
        desc_len = len(description)
        if desc_truncated or desc_raw_px > cfg['desc_max_px']:
            desc_status = 'truncated'
            warnings.append(
                f"Description exceeds the approximate {int(cfg['desc_max_px'])}px width limit for {device} "
                f"({round(desc_raw_px, 1)}px, {desc_len} chars) and will be truncated on search results."
            )
        elif desc_len < cfg['desc_min_chars']:
            desc_status = 'short'
            warnings.append(
                f"Description is short ({desc_len} characters). Recommended length is "
                f"{cfg['desc_min_chars']}–{cfg['desc_max_chars']} characters for informative snippets."
            )
        elif desc_len > cfg['desc_max_chars']:
            desc_status = 'warning'
            warnings.append(
                f"Description has {desc_len} characters (recommended: {cfg['desc_min_chars']}–{cfg['desc_max_chars']})."
            )
        else:
            desc_status = 'optimal'

        return {
            'title': title,
            'rendered_title': rendered_title,
            'description': description,
            'rendered_description': rendered_desc,
            'url': url,
            'breadcrumb': breadcrumb,
            'url_breadcrumb_preview': breadcrumb,
            'device': device,
            'title_pixel_width': round(title_raw_px, 1),
            'description_pixel_width': round(desc_raw_px, 1),
            'rendered_title_pixel_width': round(title_final_px, 1),
            'rendered_description_pixel_width': round(desc_final_px, 1),
            'title_character_count': title_len,
            'description_character_count': desc_len,
            'title_truncated': title_truncated,
            'description_truncated': desc_truncated,
            'metrics': {
                'title_length': title_len,
                'title_pixel_width': round(title_raw_px, 1),
                'title_max_pixels': cfg['title_max_px'],
                'title_truncated': title_truncated,
                'title_status': title_status,
                'description_length': desc_len,
                'description_pixel_width': round(desc_raw_px, 1),
                'description_max_pixels': cfg['desc_max_px'],
                'description_truncated': desc_truncated,
                'description_status': desc_status,
            },
            'warnings': warnings,
        }

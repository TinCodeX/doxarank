import re
import html
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape


# Supported primary Ethiopian & international languages
COMMON_LANGUAGES = {
    'en': 'English',
    'am': 'Amharic (አማርኛ)',
    'om': 'Afaan Oromo (Oromoo)',
    'ti': 'Tigrinya (ትግርኛ)',
    'so': 'Somali (Soomaali)',
    'fr': 'French',
    'ar': 'Arabic',
    'x-default': 'Default / Global Fallback',
}

# ISO 639-1 (with optional ISO 3166-1 region or script, e.g. en-US, am-ET, om-ET) or 'x-default'
LANG_CODE_REGEX = re.compile(r'^(x-default|[a-z]{2,3}(-[A-Za-z0-9]{2,4})?)$', re.IGNORECASE)


def _validate_url(url: Optional[str], field_name: str) -> str:
    url = (url or '').strip()
    if not url:
        raise ValueError(f"'{field_name}' URL is required.")
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f"'{field_name}' must be a valid HTTP or HTTPS URL (got '{url}').")
    return url


def _validate_lang_code(code: str) -> str:
    code = (code or '').strip().lower()
    if not code:
        raise ValueError("Language code is required.")
    if not LANG_CODE_REGEX.match(code):
        raise ValueError(f"Invalid hreflang code '{code}'. Expected ISO 639-1 (e.g. 'en', 'am', 'om') or 'x-default'.")
    return code


class HreflangBuilder:
    """
    Deterministic hreflang Annotation Builder.
    Supports English, Amharic, Afaan Oromo, x-default, and standard multilingual clusters.
    Generates HTML link tags, XML sitemap extensions, and HTTP Response Headers.
    """

    @classmethod
    def generate(
        cls,
        entries: List[Dict[str, Any]],
        x_default: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not entries or not isinstance(entries, list):
            raise ValueError("hreflang builder requires at least one language/URL entry.")

        cleaned_entries: List[Dict[str, str]] = []
        seen_langs = set()
        warnings: List[str] = []

        for idx, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"Entry #{idx} must be an object with lang and url.")

            raw_lang = entry.get('lang') or entry.get('language') or entry.get('hreflang')
            raw_url = entry.get('url') or entry.get('href')

            lang = _validate_lang_code(raw_lang)
            url = _validate_url(raw_url, f"Language '{lang}'")

            if lang in seen_langs:
                raise ValueError(f"Duplicate language code '{lang}' detected. Each language in a cluster must have a unique URL.")
            seen_langs.add(lang)

            cleaned_entries.append({
                'lang': lang,
                'url': url,
                'language_label': COMMON_LANGUAGES.get(lang, lang.upper()),
            })

        # Process x-default if provided as separate argument or within entries
        if x_default and 'x-default' not in seen_langs:
            x_def_url = _validate_url(x_default, "x-default")
            cleaned_entries.append({
                'lang': 'x-default',
                'url': x_def_url,
                'language_label': COMMON_LANGUAGES['x-default'],
            })
            seen_langs.add('x-default')

        if 'x-default' not in seen_langs:
            warnings.append("No 'x-default' URL specified. It is recommended to include x-default as a global fallback for unmatched locales.")

        # Check Ethiopian language coverage
        has_en = any(e['lang'].startswith('en') for e in cleaned_entries)
        has_am = any(e['lang'].startswith('am') for e in cleaned_entries)
        has_om = any(e['lang'].startswith('om') for e in cleaned_entries)

        if not (has_en and (has_am or has_om)):
            warnings.append("For Ethiopian SEO, providing reciprocal English ('en') and Amharic ('am') or Afaan Oromo ('om') versions maximizes localized search visibility.")

        # 1. HTML Link Tags
        html_tags: List[str] = []
        for e in cleaned_entries:
            esc_url = html.escape(e['url'], quote=True)
            esc_lang = html.escape(e['lang'], quote=True)
            html_tags.append(f'<link rel="alternate" hreflang="{esc_lang}" href="{esc_url}" />')
        html_output = "\n".join(html_tags)

        # 2. XML Sitemap Tags (<xhtml:link>)
        xml_tags: List[str] = []
        for e in cleaned_entries:
            esc_url = xml_escape(e['url'])
            esc_lang = xml_escape(e['lang'])
            xml_tags.append(f'  <xhtml:link rel="alternate" hreflang="{esc_lang}" href="{esc_url}"/>')
        xml_output = "\n".join(xml_tags)

        # 3. HTTP Header Format
        header_parts: List[str] = []
        for e in cleaned_entries:
            header_parts.append(f'<{e["url"]}>; rel="alternate"; hreflang="{e["lang"]}"')
        http_header_output = f"Link: {', '.join(header_parts)}"

        return {
            'html': html_output,
            'html_tags': html_tags,
            'xml_snippet': xml_output,
            'http_header': http_header_output,
            'entries': cleaned_entries,
            'metrics': {
                'language_count': len(cleaned_entries),
                'has_x_default': 'x-default' in seen_langs,
                'has_english': has_en,
                'has_amharic': has_am,
                'has_oromo': has_om,
            },
            'warnings': warnings,
        }

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape


SUPPORTED_CHANGEFREQ = [
    'always',
    'hourly',
    'daily',
    'weekly',
    'monthly',
    'yearly',
    'never',
]

MAX_SITEMAP_URLS = 50000
MAX_SITEMAP_BYTES = 50 * 1024 * 1024  # 50MB


def _validate_url(url: Optional[str], field_name: str, required: bool = True) -> Optional[str]:
    url = (url or '').strip()
    if not url:
        if required:
            raise ValueError(f"'{field_name}' URL is required.")
        return None
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f"'{field_name}' must be a valid HTTP or HTTPS URL (got '{url}').")
    return url


def _validate_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    date_str = str(date_str).strip()
    # Try YYYY-MM-DD or ISO 8601
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S'):
        try:
            datetime.strptime(date_str, fmt)
            return date_str[:10]  # Standard YYYY-MM-DD
        except ValueError:
            pass
    # If already matches YYYY-MM-DD regex
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.")


def _validate_priority(priority: Optional[Any]) -> Optional[str]:
    if priority is None or str(priority).strip() == '':
        return None
    try:
        val = float(str(priority).strip())
    except ValueError:
        raise ValueError(f"Invalid priority '{priority}'. Must be a number between 0.0 and 1.0.")
    if not (0.0 <= val <= 1.0):
        raise ValueError(f"Priority {val} out of bounds. Must be between 0.0 and 1.0.")
    return f"{val:.1f}"


class XmlSitemapGenerator:
    """
    Deterministic XML Sitemap Generator adhering to the official Sitemaps.org protocol.
    Provides XML escaping, RFC-valid schemas, and size validation.
    """

    @classmethod
    def generate(cls, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not entries or not isinstance(entries, list):
            raise ValueError("Sitemap generator requires at least one URL entry.")

        if len(entries) > MAX_SITEMAP_URLS:
            raise ValueError(f"Sitemap exceeds maximum allowed URLs ({len(entries)} > {MAX_SITEMAP_URLS}).")

        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]

        cleaned_entries: List[Dict[str, Any]] = []

        for idx, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"Sitemap entry #{idx} must be an object.")

            raw_loc = entry.get('loc') or entry.get('url')
            loc = _validate_url(raw_loc, f"Entry #{idx} loc")

            lastmod = _validate_date(entry.get('lastmod'))
            changefreq = (entry.get('changefreq') or '').strip().lower() or None
            if changefreq and changefreq not in SUPPORTED_CHANGEFREQ:
                raise ValueError(
                    f"Entry #{idx} has invalid changefreq '{changefreq}'. Supported: {', '.join(SUPPORTED_CHANGEFREQ)}"
                )

            priority = _validate_priority(entry.get('priority'))

            # XML escaping for loc (e.g. & to &amp;)
            escaped_loc = xml_escape(loc)

            lines.append('  <url>')
            lines.append(f'    <loc>{escaped_loc}</loc>')
            if lastmod:
                lines.append(f'    <lastmod>{lastmod}</lastmod>')
            if changefreq:
                lines.append(f'    <changefreq>{changefreq}</changefreq>')
            if priority:
                lines.append(f'    <priority>{priority}</priority>')
            lines.append('  </url>')

            cleaned_entries.append({
                'loc': loc,
                'lastmod': lastmod,
                'changefreq': changefreq,
                'priority': priority,
            })

        lines.append('</urlset>')
        xml_content = "\n".join(lines)

        return {
            'xml': xml_content,
            'entries': cleaned_entries,
            'metrics': {
                'url_count': len(cleaned_entries),
                'byte_size': len(xml_content.encode('utf-8')),
            }
        }


class XmlSitemapValidator:
    """
    Local, SSRF-safe XML Sitemap Validator.
    Parses and validates sitemap XML without outbound network requests or external entity risks.
    """

    @classmethod
    def validate(cls, xml_content: str) -> Dict[str, Any]:
        xml_content = (xml_content or '').strip()
        if not xml_content:
            raise ValueError("XML sitemap content is required for validation.")

        errors: List[str] = []
        warnings: List[str] = []
        urls: List[Dict[str, Any]] = []

        # Parse XML safely
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            return {
                'is_valid': False,
                'errors': [f"XML Parsing Error: {str(e)}"],
                'warnings': [],
                'url_count': 0,
                'urls': [],
            }

        # Check root element
        tag_name = root.tag.split('}')[-1] if '}' in root.tag else root.tag
        if tag_name not in ('urlset', 'sitemapindex'):
            errors.append(f"Invalid root element <{tag_name}>. Expected <urlset> or <sitemapindex>.")

        # Check namespace
        if 'http://www.sitemaps.org/schemas/sitemap/0.9' not in root.tag:
            warnings.append("Root element is missing the standard namespace xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'.")

        # Iterate entries
        for idx, child in enumerate(root, start=1):
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if child_tag not in ('url', 'sitemap'):
                warnings.append(f"Unexpected child element <{child_tag}> at index #{idx}.")
                continue

            loc_elem = child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if loc_elem is None:
                loc_elem = child.find('loc')

            if loc_elem is None or not loc_elem.text or not loc_elem.text.strip():
                errors.append(f"Entry #{idx} is missing required <loc> tag.")
                continue

            loc_val = loc_elem.text.strip()
            parsed = urlparse(loc_val)
            if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
                errors.append(f"Entry #{idx} contains invalid URL in <loc>: '{loc_val}'.")

            # Validate lastmod
            lastmod_elem = child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod') or child.find('lastmod')
            lastmod_val = lastmod_elem.text.strip() if (lastmod_elem is not None and lastmod_elem.text) else None
            if lastmod_val:
                try:
                    _validate_date(lastmod_val)
                except ValueError:
                    errors.append(f"Entry #{idx} contains invalid <lastmod> format: '{lastmod_val}'.")

            # Validate changefreq
            cf_elem = child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}changefreq') or child.find('changefreq')
            cf_val = cf_elem.text.strip().lower() if (cf_elem is not None and cf_elem.text) else None
            if cf_val and cf_val not in SUPPORTED_CHANGEFREQ:
                errors.append(f"Entry #{idx} has invalid <changefreq>: '{cf_val}'. Must be one of: {', '.join(SUPPORTED_CHANGEFREQ)}")

            # Validate priority
            p_elem = child.find('{http://www.sitemaps.org/schemas/sitemap/0.9}priority') or child.find('priority')
            p_val = p_elem.text.strip() if (p_elem is not None and p_elem.text) else None
            if p_val is not None:
                try:
                    _validate_priority(p_val)
                except ValueError as pe:
                    errors.append(f"Entry #{idx}: {str(pe)}")

            urls.append({
                'loc': loc_val,
                'lastmod': lastmod_val,
                'changefreq': cf_val,
                'priority': p_val,
            })

        is_valid = len(errors) == 0

        return {
            'is_valid': is_valid,
            'root_tag': tag_name,
            'url_count': len(urls),
            'errors': errors,
            'warnings': warnings,
            'urls': urls[:100],  # Return up to first 100 for display
        }

import json
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


SUPPORTED_SCHEMA_TYPES = [
    'LocalBusiness',
    'Article',
    'Product',
    'FAQ',
    'BreadcrumbList',
]


def _validate_url(url: Optional[str], field_name: str, required: bool = False) -> Optional[str]:
    url = (url or '').strip()
    if not url:
        if required:
            raise ValueError(f"'{field_name}' URL is required.")
        return None
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(f"'{field_name}' must be a valid HTTP or HTTPS URL (got '{url}').")
    return url


class SchemaGenerator:
    """
    Deterministic Schema.org JSON-LD Generator.
    Supports explicitly vetted schema types:
    - LocalBusiness
    - Article
    - Product
    - FAQ (FAQPage)
    - BreadcrumbList
    """

    @classmethod
    def generate(cls, schema_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate schema type and data, generate canonical Schema.org JSON-LD dict and formatted script tag.
        """
        if not schema_type or schema_type not in SUPPORTED_SCHEMA_TYPES:
            raise ValueError(
                f"Unsupported schema type '{schema_type}'. Supported types: {', '.join(SUPPORTED_SCHEMA_TYPES)}"
            )

        if not isinstance(data, dict):
            raise ValueError("Schema data must be an object/dictionary.")

        builder_map = {
            'LocalBusiness': cls._build_local_business,
            'Article': cls._build_article,
            'Product': cls._build_product,
            'FAQ': cls._build_faq,
            'BreadcrumbList': cls._build_breadcrumbs,
        }

        schema_obj = builder_map[schema_type](data)
        
        # Serialize to clean, human-readable JSON-LD
        json_ld_str = json.dumps(schema_obj, indent=2, ensure_ascii=False)
        script_tag = f'<script type="application/ld+json">\n{json_ld_str}\n</script>'

        return {
            'schema_type': schema_type,
            'json_ld': schema_obj,
            'formatted_json': json_ld_str,
            'script_tag': script_tag,
        }

    @classmethod
    def _build_local_business(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        name = (d.get('name') or '').strip()
        if not name:
            raise ValueError("LocalBusiness requires 'name'.")

        url = _validate_url(d.get('url'), 'url')
        telephone = (d.get('telephone') or '').strip() or None
        price_range = (d.get('priceRange') or '').strip() or None
        image = _validate_url(d.get('image'), 'image')

        # Address handling
        address_raw = d.get('address') or {}
        address_obj = None
        if isinstance(address_raw, dict) and any(address_raw.values()):
            address_obj = {
                "@type": "PostalAddress",
            }
            if address_raw.get('streetAddress'):
                address_obj['streetAddress'] = str(address_raw['streetAddress']).strip()
            if address_raw.get('addressLocality'):
                address_obj['addressLocality'] = str(address_raw['addressLocality']).strip()
            if address_raw.get('addressRegion'):
                address_obj['addressRegion'] = str(address_raw['addressRegion']).strip()
            if address_raw.get('postalCode'):
                address_obj['postalCode'] = str(address_raw['postalCode']).strip()
            if address_raw.get('addressCountry'):
                address_obj['addressCountry'] = str(address_raw['addressCountry']).strip()

        schema: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": name,
        }

        if url:
            schema["url"] = url
        if telephone:
            schema["telephone"] = telephone
        if price_range:
            schema["priceRange"] = price_range
        if image:
            schema["image"] = image
        if address_obj:
            schema["address"] = address_obj
        if d.get('openingHours'):
            if isinstance(d['openingHours'], list):
                schema['openingHours'] = [str(h).strip() for h in d['openingHours'] if str(h).strip()]
            elif isinstance(d['openingHours'], str) and d['openingHours'].strip():
                schema['openingHours'] = [d['openingHours'].strip()]

        return schema

    @classmethod
    def _build_article(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        headline = (d.get('headline') or '').strip()
        if not headline:
            raise ValueError("Article requires 'headline'.")

        author_name = (d.get('author') or d.get('author_name') or '').strip()
        date_published = (d.get('datePublished') or '').strip() or None
        date_modified = (d.get('dateModified') or '').strip() or None
        description = (d.get('description') or '').strip() or None
        image = _validate_url(d.get('image'), 'image')
        url = _validate_url(d.get('url'), 'url')

        schema: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": headline,
        }

        if author_name:
            schema["author"] = {
                "@type": "Person",
                "name": author_name,
            }
        if date_published:
            schema["datePublished"] = date_published
        if date_modified:
            schema["dateModified"] = date_modified
        if description:
            schema["description"] = description
        if image:
            schema["image"] = image
        if url:
            schema["mainEntityOfPage"] = {
                "@type": "WebPage",
                "@id": url,
            }

        # Publisher
        pub_name = (d.get('publisherName') or d.get('publisher_name') or '').strip()
        if pub_name:
            pub_obj: Dict[str, Any] = {
                "@type": "Organization",
                "name": pub_name,
            }
            pub_logo = _validate_url(d.get('publisherLogo') or d.get('publisher_logo'), 'publisherLogo')
            if pub_logo:
                pub_obj["logo"] = {
                    "@type": "ImageObject",
                    "url": pub_logo,
                }
            schema["publisher"] = pub_obj

        return schema

    @classmethod
    def _build_product(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        name = (d.get('name') or '').strip()
        if not name:
            raise ValueError("Product requires 'name'.")

        description = (d.get('description') or '').strip() or None
        image = _validate_url(d.get('image'), 'image')
        sku = (d.get('sku') or '').strip() or None
        brand_name = (d.get('brand') or '').strip() or None

        schema: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
        }

        if description:
            schema["description"] = description
        if image:
            schema["image"] = image
        if sku:
            schema["sku"] = sku
        if brand_name:
            schema["brand"] = {
                "@type": "Brand",
                "name": brand_name,
            }

        # Offer
        price = d.get('price')
        price_currency = (d.get('priceCurrency') or 'USD').strip().upper()
        if price is not None and str(price).strip() != '':
            try:
                price_val = float(str(price).strip().replace(',', ''))
            except ValueError:
                raise ValueError(f"Invalid price value: '{price}'. Must be a number.")
            
            offer: Dict[str, Any] = {
                "@type": "Offer",
                "price": f"{price_val:.2f}",
                "priceCurrency": price_currency,
                "availability": d.get('availability', 'https://schema.org/InStock'),
            }
            offer_url = _validate_url(d.get('offerUrl') or d.get('url'), 'offerUrl')
            if offer_url:
                offer["url"] = offer_url
            schema["offers"] = offer

        return schema

    @classmethod
    def _build_faq(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        items = d.get('items') or d.get('questions') or []
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError("FAQ requires at least one question and answer pair.")

        main_entity: List[Dict[str, Any]] = []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"FAQ item #{idx} must be an object with question and answer.")
            q = (item.get('question') or item.get('name') or '').strip()
            a = (item.get('answer') or item.get('text') or '').strip()
            if not q:
                raise ValueError(f"FAQ item #{idx} is missing a question.")
            if not a:
                raise ValueError(f"FAQ item #{idx} is missing an answer.")

            main_entity.append({
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": a,
                },
            })

        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": main_entity,
        }

    @classmethod
    def _build_breadcrumbs(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        items = d.get('items') or d.get('breadcrumbs') or []
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError("BreadcrumbList requires at least one breadcrumb item.")

        elements: List[Dict[str, Any]] = []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Breadcrumb item #{idx} must be an object with name and item URL.")
            name = (item.get('name') or '').strip()
            url = (item.get('item') or item.get('url') or '').strip()
            if not name:
                raise ValueError(f"Breadcrumb item #{idx} is missing 'name'.")
            if not url:
                raise ValueError(f"Breadcrumb item #{idx} is missing 'item' (URL).")
            validated_url = _validate_url(url, f"Breadcrumb #{idx} url", required=True)

            elements.append({
                "@type": "ListItem",
                "position": idx,
                "name": name,
                "item": validated_url,
            })

        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": elements,
        }

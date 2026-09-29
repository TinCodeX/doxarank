"""
Keyword Intelligence Provider Architecture for DoxaRank.

Provides clean provider abstractions, safe unconfigured handling, deterministic mock
testing provider, and production DataForSEO integration for Google Ethiopia (google.com.et).
"""

import base64
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class KeywordMetricsResult:
    """
    Structured outcome representing keyword intelligence metrics returned by a provider.
    """
    search_volume: Optional[int] = None
    cpc: Optional[Decimal] = None
    currency: str = "USD"
    competition: Optional[str] = None  # 'LOW', 'MEDIUM', 'HIGH'
    competition_index: Optional[float] = None  # 0.0 - 1.0
    difficulty: Optional[int] = None  # 0 - 100
    intent: Optional[str] = None  # 'informational', 'commercial', 'transactional', 'navigational'
    source: str = "unconfigured"
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'search_volume': self.search_volume,
            'cpc': str(self.cpc) if self.cpc is not None else None,
            'currency': self.currency,
            'competition': self.competition,
            'competition_index': self.competition_index,
            'difficulty': self.difficulty,
            'intent': self.intent,
            'source': self.source,
            'raw_metadata': self.raw_metadata,
            'success': self.success,
            'error_message': self.error_message,
        }


class BaseKeywordIntelligenceProvider(ABC):
    """
    Abstract interface for keyword metrics providers.
    """
    provider_name: str = "base"

    @abstractmethod
    def get_keyword_metrics(
        self,
        keyword: str,
        country: str = "ET",
        language: str = "en",
        search_domain: str = "google.com.et",
        device: str = "desktop"
    ) -> KeywordMetricsResult:
        """
        Fetch intelligence metrics (volume, CPC, competition) for a single query.
        """
        pass

    def get_batch_keyword_metrics(
        self,
        keywords: List[str],
        country: str = "ET",
        language: str = "en",
        search_domain: str = "google.com.et",
        device: str = "desktop"
    ) -> Dict[str, KeywordMetricsResult]:
        """
        Fetch intelligence metrics for a batch of queries. Default iterates single queries.
        """
        results = {}
        for kw in keywords:
            results[kw] = self.get_keyword_metrics(
                keyword=kw,
                country=country,
                language=language,
                search_domain=search_domain,
                device=device
            )
        return results


class UnconfiguredProvider(BaseKeywordIntelligenceProvider):
    """
    Default safe provider when no third-party API credentials are configured.
    Never fabricates random data or throws unhandled crashes.
    Reports UNAVAILABLE status with clear instructions.
    """
    provider_name: str = "unconfigured"

    def get_keyword_metrics(
        self,
        keyword: str,
        country: str = "ET",
        language: str = "en",
        search_domain: str = "google.com.et",
        device: str = "desktop"
    ) -> KeywordMetricsResult:
        logger.info(
            f"[KeywordIntelligence] External provider unconfigured. "
            f"Query: '{keyword}', Country: {country}, Lang: {language}."
        )
        return KeywordMetricsResult(
            search_volume=None,
            cpc=None,
            currency="USD",
            competition=None,
            competition_index=None,
            difficulty=None,
            intent=None,
            source=self.provider_name,
            raw_metadata={'configured': False},
            success=False,
            error_message=(
                "Keyword intelligence provider is not configured. "
                "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD or enable mock provider for testing."
            )
        )


class MockKeywordIntelligenceProvider(BaseKeywordIntelligenceProvider):
    """
    Mock provider for automated unit/integration tests and local development.
    Distinctly labeled with source='mock' so it is never confused with live provider data.
    Provides deterministic values for Amharic, Oromo, and English test queries.
    """
    provider_name: str = "mock"

    # Known curated fixtures for testing
    FIXTURES: Dict[str, Dict[str, Any]] = {
        # Amharic queries
        "የአዲስ አበባ ሆቴል": {
            "search_volume": 2400, "cpc": Decimal("0.3500"), "competition": "MEDIUM",
            "competition_index": 0.45, "difficulty": 28, "intent": "commercial"
        },
        "የኢትዮጵያ ሆቴሎች": {
            "search_volume": 1900, "cpc": Decimal("0.4000"), "competition": "MEDIUM",
            "competition_index": 0.50, "difficulty": 32, "intent": "commercial"
        },
        "ቡና መግዛት": {
            "search_volume": 850, "cpc": Decimal("0.2800"), "competition": "HIGH",
            "competition_index": 0.75, "difficulty": 40, "intent": "transactional"
        },
        # Oromo queries
        "hoteelaa finfinnee": {
            "search_volume": 880, "cpc": Decimal("0.2500"), "competition": "LOW",
            "competition_index": 0.22, "difficulty": 18, "intent": "commercial"
        },
        "buna bituu": {
            "search_volume": 420, "cpc": Decimal("0.2000"), "competition": "MEDIUM",
            "competition_index": 0.38, "difficulty": 15, "intent": "transactional"
        },
        # English queries
        "seo": {
            "search_volume": 9900, "cpc": Decimal("2.4500"), "competition": "HIGH",
            "competition_index": 0.88, "difficulty": 68, "intent": "informational"
        },
        "best hotels in addis ababa": {
            "search_volume": 5400, "cpc": Decimal("0.8500"), "competition": "HIGH",
            "competition_index": 0.78, "difficulty": 45, "intent": "commercial"
        },
        "seo agency ethiopia": {
            "search_volume": 720, "cpc": Decimal("1.2000"), "competition": "HIGH",
            "competition_index": 0.82, "difficulty": 52, "intent": "commercial"
        },
        "buy coffee online ethiopia": {
            "search_volume": 1300, "cpc": Decimal("0.6500"), "competition": "HIGH",
            "competition_index": 0.70, "difficulty": 38, "intent": "transactional"
        },
        "how to start business in ethiopia": {
            "search_volume": 3600, "cpc": Decimal("0.1500"), "competition": "LOW",
            "competition_index": 0.15, "difficulty": 22, "intent": "informational"
        },
    }

    def get_keyword_metrics(
        self,
        keyword: str,
        country: str = "ET",
        language: str = "en",
        search_domain: str = "google.com.et",
        device: str = "desktop"
    ) -> KeywordMetricsResult:
        clean_kw = keyword.strip()
        lower_kw = clean_kw.lower()

        # Check fixtures
        matched = self.FIXTURES.get(clean_kw) or self.FIXTURES.get(lower_kw)
        if matched:
            return KeywordMetricsResult(
                search_volume=matched["search_volume"],
                cpc=matched["cpc"],
                currency="USD",
                competition=matched["competition"],
                competition_index=matched["competition_index"],
                difficulty=matched.get("difficulty"),
                intent=matched.get("intent"),
                source=self.provider_name,
                raw_metadata={'mock_fixture': True, 'query': clean_kw},
                success=True,
                error_message=""
            )

        # Deterministic generation for any arbitrary test query based on hash
        digest = int(hashlib.md5(clean_kw.encode('utf-8')).hexdigest(), 16)
        volume = 100 + (digest % 5000)
        cpc_val = Decimal(str(round(0.10 + ((digest % 200) / 100.0), 4)))
        comp_levels = ["LOW", "MEDIUM", "HIGH"]
        comp = comp_levels[digest % 3]
        comp_idx = round(0.1 + ((digest % 90) / 100.0), 2)
        diff = 10 + (digest % 80)

        return KeywordMetricsResult(
            search_volume=volume,
            cpc=cpc_val,
            currency="USD",
            competition=comp,
            competition_index=comp_idx,
            difficulty=diff,
            intent=None,  # will be classified deterministically by intent classifier
            source=self.provider_name,
            raw_metadata={'mock_deterministic': True, 'query': clean_kw},
            success=True,
            error_message=""
        )


class DataForSEOProvider(BaseKeywordIntelligenceProvider):
    """
    Production-ready keyword intelligence provider integrating with DataForSEO Google Ads API.
    DataForSEO provides live search volume, CPC, and competition for country ET (location_code: 2231).
    """
    provider_name: str = "dataforseo"

    # DataForSEO Location code for Ethiopia
    LOCATION_CODE_ETHIOPIA = 2231

    # Language code mappings for DataForSEO
    LANGUAGE_CODES = {
        'en': 'en',
        'am': 'am',
        'om': 'om',
    }

    def __init__(
        self,
        login: Optional[str] = None,
        password: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout: int = 15
    ):
        self.login = login or getattr(settings, 'DATAFORSEO_LOGIN', '')
        self.password = password or getattr(settings, 'DATAFORSEO_PASSWORD', '')
        self.api_url = (api_url or getattr(settings, 'DATAFORSEO_API_URL', 'https://api.dataforseo.com/v3')).rstrip('/')
        self.timeout = timeout

    def _get_auth_header(self) -> Dict[str, str]:
        auth_str = f"{self.login}:{self.password}"
        encoded = base64.b64encode(auth_str.encode('utf-8')).decode('ascii')
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json',
            'User-Agent': 'DoxaRank-KeywordIntelligence/1.0',
        }

    def get_keyword_metrics(
        self,
        keyword: str,
        country: str = "ET",
        language: str = "en",
        search_domain: str = "google.com.et",
        device: str = "desktop"
    ) -> KeywordMetricsResult:
        if not self.login or not self.password:
            logger.error("[DataForSEO] Missing login or password credentials.")
            return KeywordMetricsResult(
                search_volume=None,
                cpc=None,
                currency="USD",
                competition=None,
                competition_index=None,
                difficulty=None,
                intent=None,
                source=self.provider_name,
                raw_metadata={},
                success=False,
                error_message="DataForSEO credentials are not configured on the server."
            )

        import requests

        url = f"{self.api_url}/keywords_data/google_ads/search_volume/live"
        post_data = [
            {
                "keywords": [keyword],
                "location_code": self.LOCATION_CODE_ETHIOPIA if country == "ET" else None,
                "location_name": "Ethiopia" if country == "ET" else country,
                "language_code": self.LANGUAGE_CODES.get(language, "en"),
            }
        ]

        try:
            response = requests.post(
                url,
                headers=self._get_auth_header(),
                json=post_data,
                timeout=self.timeout
            )

            if response.status_code == 401 or response.status_code == 403:
                logger.error(f"[DataForSEO] Authentication failed: HTTP {response.status_code}")
                return KeywordMetricsResult(
                    source=self.provider_name,
                    success=False,
                    error_message=f"DataForSEO authentication failure (HTTP {response.status_code})."
                )

            if response.status_code == 429:
                logger.warning("[DataForSEO] Rate limit exceeded (HTTP 429).")
                return KeywordMetricsResult(
                    source=self.provider_name,
                    success=False,
                    error_message="DataForSEO rate limit exceeded. Please try again later."
                )

            if not response.ok:
                logger.error(f"[DataForSEO] Request failed with HTTP {response.status_code}: {response.text[:200]}")
                return KeywordMetricsResult(
                    source=self.provider_name,
                    success=False,
                    error_message=f"DataForSEO provider returned HTTP error {response.status_code}."
                )

            data = response.json()
            tasks = data.get('tasks')
            if not tasks or not isinstance(tasks, list):
                return KeywordMetricsResult(
                    source=self.provider_name,
                    success=False,
                    error_message="Malformed response structure from DataForSEO."
                )

            task = tasks[0]
            if task.get('status_code') not in (20000, 200):
                error_msg = task.get('status_message', 'Unknown DataForSEO task error')
                return KeywordMetricsResult(
                    source=self.provider_name,
                    success=False,
                    error_message=f"DataForSEO task failed: {error_msg}"
                )

            result_list = task.get('result') or []
            if not result_list:
                return KeywordMetricsResult(
                    search_volume=None,
                    cpc=None,
                    competition=None,
                    competition_index=None,
                    source=self.provider_name,
                    raw_metadata={'response': task},
                    success=True,
                    error_message="No search volume data returned for query."
                )

            item = result_list[0]
            raw_vol = item.get('search_volume')
            search_volume = int(raw_vol) if raw_vol is not None else None

            raw_cpc = item.get('cpc')
            cpc_val = Decimal(str(round(float(raw_cpc), 4))) if raw_cpc is not None else None

            raw_comp = item.get('competition')
            competition = str(raw_comp).upper() if raw_comp in ('LOW', 'MEDIUM', 'HIGH', 'low', 'medium', 'high') else None

            raw_comp_index = item.get('competition_index')
            comp_index = float(raw_comp_index) if raw_comp_index is not None else None

            return KeywordMetricsResult(
                search_volume=search_volume,
                cpc=cpc_val,
                currency="USD",
                competition=competition,
                competition_index=comp_index,
                difficulty=None,  # Google Ads API does not provide SEO difficulty
                intent=None,  # Intent is classified by DoxaRank deterministic classifier
                source=self.provider_name,
                raw_metadata={
                    'monthly_searches': item.get('monthly_searches', []),
                    'low_top_of_page_bid': item.get('low_top_of_page_bid'),
                    'high_top_of_page_bid': item.get('high_top_of_page_bid'),
                },
                success=True,
                error_message=""
            )

        except requests.exceptions.Timeout:
            logger.error(f"[DataForSEO] Timeout contacting API after {self.timeout}s.")
            return KeywordMetricsResult(
                source=self.provider_name,
                success=False,
                error_message="Timeout connecting to keyword data provider."
            )
        except requests.exceptions.RequestException as req_err:
            logger.error(f"[DataForSEO] Network/HTTP exception: {req_err}")
            return KeywordMetricsResult(
                source=self.provider_name,
                success=False,
                error_message=f"Network error connecting to keyword data provider: {str(req_err)}"
            )
        except Exception as e:
            logger.error(f"[DataForSEO] Unexpected parsing error: {e}", exc_info=True)
            return KeywordMetricsResult(
                source=self.provider_name,
                success=False,
                error_message="Unexpected error processing keyword intelligence data."
            )


def get_keyword_intelligence_provider() -> BaseKeywordIntelligenceProvider:
    """
    Factory function returning the configured KeywordIntelligenceProvider.
    """
    provider_name = getattr(settings, 'KEYWORD_INTELLIGENCE_PROVIDER', 'unconfigured').strip().lower()

    if provider_name == 'mock':
        return MockKeywordIntelligenceProvider()
    elif provider_name == 'dataforseo':
        login = getattr(settings, 'DATAFORSEO_LOGIN', '')
        password = getattr(settings, 'DATAFORSEO_PASSWORD', '')
        if login and password:
            return DataForSEOProvider(login=login, password=password)
        logger.warning("[KeywordIntelligence] DataForSEO selected but credentials missing; using UnconfiguredProvider.")
        return UnconfiguredProvider()
    else:
        return UnconfiguredProvider()

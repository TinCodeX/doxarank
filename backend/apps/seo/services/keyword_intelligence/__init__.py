"""
Keyword Intelligence Service Package for DoxaRank (Original SRS: Search Volume & CPC).

Provides provider abstraction, multilingual deterministic search intent classification,
caching, snapshot history, and Ethiopia-first keyword metrics.
"""

from .provider import (
    BaseKeywordIntelligenceProvider,
    KeywordMetricsResult,
    UnconfiguredProvider,
    MockKeywordIntelligenceProvider,
    DataForSEOProvider,
    get_keyword_intelligence_provider,
)
from .intent_classifier import classify_search_intent
from .service import KeywordIntelligenceService

__all__ = [
    'BaseKeywordIntelligenceProvider',
    'KeywordMetricsResult',
    'UnconfiguredProvider',
    'MockKeywordIntelligenceProvider',
    'DataForSEOProvider',
    'get_keyword_intelligence_provider',
    'classify_search_intent',
    'KeywordIntelligenceService',
]

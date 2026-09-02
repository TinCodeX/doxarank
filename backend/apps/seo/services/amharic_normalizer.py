"""
DoxaRank Amharic & Ge'ez Script Normalization Service (Phase 4.9.1).

Essential for an Ethiopia-first SEO SaaS targeting google.com.et and local search engines.
Solves phonetic homophone divergence across Ethiopian search queries:
1. Ha series: (ሀ, ሐ, ኀ, ኃ, ኻ) -> ሀ
2. Se series: (ሰ, ሠ) -> ሰ
3. A series:  (አ, ዓ, ዐ) -> አ
4. Tse series: (ጸ, ፀ) -> ጸ
5. Punctuation: Strips Ethiopian word separators (፡, ።, ፣, ፤, ፥, ፦, ፧, ፨).
"""

import re
from typing import Dict, Optional

# Complete character replacement mapping across all orders (1st to 7th orders)
GEEZ_HOMOPHONE_MAP: Dict[str, str] = {
    # --- Ha Series ---
    'ሐ': 'ሀ', 'ኀ': 'ሀ', 'ኃ': 'ሀ', 'ኻ': 'ሀ',
    'ሑ': 'ሁ', 'ኁ': 'ሁ', 'ዅ': 'ሁ',
    'ሒ': 'ሂ', 'ኂ': 'ሂ', 'ኺ': 'ሂ',
    'ሓ': 'ሃ', 'ኃ': 'ሃ', 'ኻ': 'ሃ',
    'ሔ': 'ሄ', 'ኄ': 'ሄ', 'ኼ': 'ሄ',
    'ሕ': 'ህ', 'ኅ': 'ህ', 'ኽ': 'ህ',
    'ሖ': 'ሆ', 'ኆ': 'ሆ', 'ኾ': 'ሆ',

    # --- Se Series ---
    'ሠ': 'ሰ',
    'ሡ': 'ሱ',
    'ሢ': 'ሲ',
    'ሣ': 'ሳ',
    'ሤ': 'ሴ',
    'ሥ': 'ስ',
    'ሦ': 'ሶ',

    # --- A Series ---
    'ዓ': 'አ', 'ዐ': 'አ',
    'ዑ': 'ኡ',
    'ዒ': 'ኢ',
    'ኣ': 'አ',
    'ዔ': 'ኤ',
    'ዕ': 'እ',
    'ዖ': 'ኦ',

    # --- Tse Series ---
    'ፀ': 'ጸ',
    'ፁ': 'ጹ',
    'ፂ': 'ጺ',
    'ፃ': 'ጻ',
    'ፄ': 'ጼ',
    'ፅ': 'ጽ',
    'ፆ': 'ጾ',
}

# Ethiopian punctuation marks
ETHIOPIC_PUNCTUATION = {
    '፡': ' ',   # Word space
    '።': ' ',   # Full stop
    '፣': '',    # Comma
    '፤': '',    # Semicolon
    '፥': '',    # Colon
    '፦': '',    # Preface colon
    '፧': '',    # Question mark
    '፨': '',    # Paragraph separator
}


def normalize_amharic_query(query: Optional[str]) -> str:
    """
    Normalizes Amharic / Ge'ez search query or keyword for canonical matching.
    Collapses homophones, replaces Ethiopic separators, strips punctuation,
    and returns a clean lowercase string.
    """
    if not query:
        return ""

    text = str(query).strip()

    # 1. Replace Ethiopic punctuation
    for punct, repl in ETHIOPIC_PUNCTUATION.items():
        text = text.replace(punct, repl)

    # 2. Canonicalize homophones
    canonical_chars = []
    for char in text:
        canonical_chars.append(GEEZ_HOMOPHONE_MAP.get(char, char))
    text = "".join(canonical_chars)

    # 3. Collapse whitespace and lowercase (for mixed English/Amharic queries)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def are_keywords_equivalent(kw1: Optional[str], kw2: Optional[str]) -> bool:
    """
    Compares two keywords for semantic equivalence under Fidel homophone normalization.
    Example: 'አዲስ አበባ' == 'ዐዲስ አበባ' -> True
             'ሰዓት' == 'ሠዓት' -> True
    """
    norm1 = normalize_amharic_query(kw1)
    norm2 = normalize_amharic_query(kw2)
    return bool(norm1 and norm1 == norm2)

"""
DoxaRank Amharic Fidel Keyword Normalizer Tool (Tool 10).

Wraps the canonical DoxaRank Amharic & Ge'ez script normalization engine
(apps.seo.services.amharic_normalizer) as a standalone interactive SEO tool.

Capabilities:
- Ge'ez script homophone canonicalization across Ha, Se, A, and Tse series (1st-7th orders).
- Punctuation normalization / word separator collapsing.
- Transformation tracking (substitutions count, specific character mappings detected).
- Keyword semantic equivalence evaluation between two input variants.
"""

from typing import Dict, Any, List, Optional, Tuple
from apps.seo.services.amharic_normalizer import (
    normalize_amharic_query,
    are_keywords_equivalent,
    GEEZ_HOMOPHONE_MAP,
    ETHIOPIC_PUNCTUATION,
)

# Character series classification for detailed diagnostic feedback
SERIES_MAP = {
    # Ha series
    'ሐ': 'Ha', 'ኀ': 'Ha', 'ኃ': 'Ha', 'ኻ': 'Ha',
    'ሑ': 'Ha', 'ኁ': 'Ha', 'ዅ': 'Ha',
    'ሒ': 'Ha', 'ኂ': 'Ha', 'ኺ': 'Ha',
    'ሓ': 'Ha', 'ሔ': 'Ha', 'ኄ': 'Ha', 'ኼ': 'Ha',
    'ሕ': 'Ha', 'ኅ': 'Ha', 'ኽ': 'Ha',
    'ሖ': 'Ha', 'ኆ': 'Ha', 'ኾ': 'Ha',
    # Se series
    'ሠ': 'Se', 'ሡ': 'Se', 'ሢ': 'Se', 'ሣ': 'Se', 'ሤ': 'Se', 'ሥ': 'Se', 'ሦ': 'Se',
    # A series
    'ዓ': 'A', 'ዐ': 'A', 'ዑ': 'A', 'ዒ': 'A', 'ኣ': 'A', 'ዔ': 'A', 'ዕ': 'A', 'ዖ': 'A',
    # Tse series
    'ፀ': 'Tse', 'ፁ': 'Tse', 'ፂ': 'Tse', 'ፃ': 'Tse', 'ፄ': 'Tse', 'ፅ': 'Tse', 'ፆ': 'Tse',
}


def contains_amharic_script(text: str) -> bool:
    """Checks whether the text contains any Ge'ez / Ethiopic Unicode characters."""
    if not text:
        return False
    # Ethiopic Unicode block: U+1200 to U+137F, plus Ethiopic Supplement / Extended
    for char in text:
        cp = ord(char)
        if (0x1200 <= cp <= 0x137F) or (0x1380 <= cp <= 0x139F) or (0x2D80 <= cp <= 0x2DDF):
            return True
    return False


def detect_transformations(text: str) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Analyzes an input string against canonical Ge'ez homophone and punctuation mappings.
    Returns: (modifications_count, transformations_applied_list)
    """
    if not text:
        return 0, []

    transformations: List[Dict[str, Any]] = []
    mod_count = 0

    for idx, char in enumerate(text):
        if char in GEEZ_HOMOPHONE_MAP:
            mod_count += 1
            replacement = GEEZ_HOMOPHONE_MAP[char]
            series = SERIES_MAP.get(char, "Homophone")
            transformations.append({
                'position': idx,
                'original': char,
                'replacement': replacement,
                'type': f'{series} Series Homophone',
                'description': f"Collapsed '{char}' to canonical '{replacement}' ({series} series)",
            })
        elif char in ETHIOPIC_PUNCTUATION:
            mod_count += 1
            replacement = ETHIOPIC_PUNCTUATION[char]
            rep_label = "[space]" if replacement == " " else "[stripped]"
            transformations.append({
                'position': idx,
                'original': char,
                'replacement': rep_label,
                'type': 'Ethiopic Punctuation',
                'description': f"Normalized word separator '{char}' to '{rep_label}'",
            })

    return mod_count, transformations


class AmharicNormalizerTool:
    """
    Domain service for Tool 10: Amharic Fidel Keyword Normalizer.
    """

    @classmethod
    def normalize(
        cls,
        text: str,
        comparison_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes text using canonical Amharic normalization.
        Detects specific transformations and optionally evaluates equivalence with a comparison term.
        """
        text = (text or '').strip()
        if not text:
            raise ValueError("Input Amharic keyword or text is required for normalization.")

        has_amharic = contains_amharic_script(text)
        mod_count, transformations = detect_transformations(text)
        normalized = normalize_amharic_query(text)

        # Comparison handling
        normalized_comparison = None
        is_equivalent = None
        has_comparison = bool(comparison_text and comparison_text.strip())

        if has_comparison:
            comp_clean = comparison_text.strip()
            normalized_comparison = normalize_amharic_query(comp_clean)
            is_equivalent = are_keywords_equivalent(text, comp_clean)

        return {
            'original_text': text,
            'normalized_text': normalized,
            'has_amharic_script': has_amharic,
            'modifications_count': mod_count,
            'transformations_applied': transformations,
            'comparison_text': comparison_text.strip() if has_comparison else None,
            'normalized_comparison': normalized_comparison,
            'is_equivalent': is_equivalent,
            'metrics': {
                'original_length': len(text),
                'normalized_length': len(normalized),
                'original_words': len(text.split()),
                'normalized_words': len(normalized.split()) if normalized else 0,
            }
        }

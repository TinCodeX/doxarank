"""
Deterministic Multilingual Search Intent Classifier for DoxaRank.

Supports English, Amharic (አማርኛ), and Oromo (Afaan Oromoo) with full Unicode preservation.
Strictly rule-based and deterministic — does NOT claim or use LLM/AI.
Follows standard SEO intent taxonomy:
- transactional
- commercial
- navigational
- informational
"""

import re
from typing import Optional, List, Set


# Intent Trigger Dictionaries across English, Amharic, and Oromo

TRANSACTIONAL_TRIGGERS: Set[str] = {
    # English
    "buy", "purchase", "order", "cheap", "price", "pricing", "discount", "coupon",
    "quote", "cost", "booking", "book", "reserve", "hire", "shop", "store", "sale",
    # Amharic
    "ግዛ", "መግዛት", "ሽያጭ", "ዋጋ", "ክፈያ", "ትዕዛዝ", "ኪራይ", "አከራይ", "ቦታ ማስያዝ", "መሸጫ",
    # Oromo
    "bituu", "bitaa", "gurgurtaa", "gatii", "kaffaltii", "ajaja", "kireeffachuu", "kireessuu",
}

COMMERCIAL_TRIGGERS: Set[str] = {
    # English
    "best", "top", "review", "reviews", "vs", "compare", "alternative", "alternatives",
    "comparison", "provider", "agency", "service", "services", "company", "firm",
    "hotel", "hotels", "software", "tool", "features", "packages",
    # Amharic
    "ምርጥ", "ደረጃ", "አወዳድር", "ንጽጽር", "ግምገማ", "ድርጅት", "አገልግሎት", "ኤጀንሲ", "ሆቴል", "ሆቴሎች",
    # Oromo
    "filatamaa", "caalaa", "madaallii", "daldala", "tajaajila", "dhaabbata", "hoteela", "hoteelaa",
}

NAVIGATIONAL_TRIGGERS: Set[str] = {
    # English
    "login", "sign in", "log in", "sign up", "signin", "signup", "portal", "app",
    "official", "download", "website", "account", "doxarank",
    # Amharic
    "ግባ", "መግቢያ", "ድህረ ገጽ", "ድህረገጽ", "መተግበሪያ", "ይፋዊ",
    # Oromo
    "seensaa", "seeni", "marsariitii", "appilikeeshinii",
}

INFORMATIONAL_TRIGGERS: Set[str] = {
    # English
    "how", "what", "why", "when", "where", "who", "guide", "tutorial", "tips",
    "definition", "meaning", "examples", "ideas", "learn", "info", "explanation",
    # Amharic
    "እንዴት", "ምንድን", "ምንድነው", "ለምን", "መቼ", "የት", "መመሪያ", "ትምህርት", "ምንነት", "መረጃ",
    # Oromo
    "akkamiin", "maal", "maaliif", "yoom", "eessa", "qajeelfama", "barumsa", "odeeffannoo",
}


def _tokenize_query(query: str) -> List[str]:
    """
    Split search query into clean tokens preserving Ge'ez/Amharic and Latin characters.
    Splits on whitespace, common punctuation, and Ethiopian word separators (፡ ፣ ፤).
    """
    # Replace Ethiopian word separator '፡' and punctuation with space
    clean = re.sub(r'[\s፡፣፤፦!\?,\.\-_/\\()\[\]"\'«»]+', ' ', query)
    tokens = [t.strip().lower() for t in clean.split() if t.strip()]
    return tokens


def classify_search_intent(keyword: str, language: str = 'en') -> Optional[str]:
    """
    Classify the search intent of a query deterministically using pattern matching.

    Hierarchy:
    1. Transactional triggers (clear purchasing / hiring / booking intent)
    2. Commercial investigation triggers (evaluating options, providers, reviews, best of)
    3. Navigational triggers (looking for specific login / portal / website)
    4. Informational triggers (question words, tutorials, guides)

    Returns:
        'transactional', 'commercial', 'navigational', 'informational', or None if ambiguous.
    """
    if not keyword or not keyword.strip():
        return None

    raw_query = keyword.strip()
    lower_query = raw_query.lower()
    tokens = _tokenize_query(raw_query)

    # 0. Interrogative question starters and tutorial markers (strictly Informational)
    question_starters = {
        "how", "what", "why", "when", "where", "who",
        "እንዴት", "ለምን", "ምን", "ምንድን", "ምንድነው", "የት", "መቼ",
        "akkamiin", "maal", "maaliif", "yoom", "eessa"
    }
    if tokens and tokens[0] in question_starters:
        return "informational"
    if any(m in tokens for m in ["tutorial", "guide", "tips", "መመሪያ", "qajeelfama"]):
        return "informational"

    # 1. Transactional check
    for trigger in TRANSACTIONAL_TRIGGERS:
        if trigger in tokens or (len(trigger) > 3 and trigger in lower_query):
            return "transactional"

    # 2. Commercial check
    for trigger in COMMERCIAL_TRIGGERS:
        if trigger in tokens or (len(trigger) > 3 and trigger in lower_query):
            return "commercial"

    # 3. Navigational check
    for trigger in NAVIGATIONAL_TRIGGERS:
        if trigger in tokens or (len(trigger) > 3 and trigger in lower_query):
            return "navigational"

    # 4. Informational check
    for trigger in INFORMATIONAL_TRIGGERS:
        if trigger in tokens or (len(trigger) > 3 and trigger in lower_query):
            return "informational"

    # Default heuristic: if query starts with question patterns or is a single conceptual head term
    if len(tokens) == 1 and len(tokens[0]) >= 3:
        # Single head terms like "SEO", "marketing", "coffee" usually represent informational searches
        return "informational"

    return "informational"

from functools import lru_cache

import numpy as np
import re

from core.schemas import RouteTarget

# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING-BASED ROUTER (Primary)
# ══════════════════════════════════════════════════════════════════════════════

ROUTE_DESCRIPTIONS = {
    RouteTarget.SQL.value: """
        Database queries, SQL, calculations, aggregations, averages, sums, counts,
        correlations, filtering data, grouping, ranking, trends in CSV data,
        mathematical operations on tables, data analysis, statistics
    """,
    RouteTarget.FINANCE.value: """
        Stock prices, market data, ticker symbols, earnings reports, balance sheets,
        cash flow, analyst ratings, PE ratios, market cap, dividends, financial metrics,
        company financials, real-time quotes, stock history
    """,
    RouteTarget.WEB_SEARCH.value: """
        Current news, latest information, recent events, web search, general knowledge,
        what is happening, today's news, external information, internet search
    """,
    RouteTarget.MODEL.value: """
        PDF documents, Word files, semantic search in documents, lookup by ID,
        account numbers, customer information, greetings, thanks, casual conversation,
        file search, document retrieval
    """
}

_embedding_model = None
_embedding_setup_failed = False
_route_embeddings: dict[str, np.ndarray] = {}


def get_embedding_model():
    global _embedding_model, _embedding_setup_failed

    if _embedding_model is not None:
        return _embedding_model

    if _embedding_setup_failed:
        return None

    try:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        return _embedding_model
    except Exception:
        _embedding_setup_failed = True
        return None


def get_route_embeddings() -> dict[str, np.ndarray]:
    global _route_embeddings

    if _route_embeddings:
        return _route_embeddings

    model = get_embedding_model()
    if model is None:
        return {}

    _route_embeddings = {
        route: model.encode(desc, convert_to_tensor=False)
        for route, desc in ROUTE_DESCRIPTIONS.items()
    }
    return _route_embeddings


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


@lru_cache(maxsize=512)
def route_with_embeddings(query: str) -> str:
    """
    Route query using sentence transformer embeddings.
    Fast (~50ms) and accurate for most queries.
    """
    model = get_embedding_model()
    route_embeddings = get_route_embeddings()
    if model is None or not route_embeddings:
        return route_with_keywords(query)

    query_embedding = model.encode(query, convert_to_tensor=False)

    similarities = {
        route: cosine_similarity(query_embedding, route_emb)
        for route, route_emb in route_embeddings.items()
    }
    
    best_route = max(similarities, key=similarities.get)
    confidence = similarities[best_route]
    
    
    if confidence < 0.3:
        return route_with_keywords(query)
    
    return best_route


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD FALLBACK 
# ══════════════════════════════════════════════════════════════════════════════

SQL_KEYWORDS = frozenset([
    "average", "sum", "count", "total", "calculate", "correlation", "corr",
    "group", "filter", "where", "top", "bottom", "rank", "trend", "aggregate",
    "query", "table", "database", "csv", "mean", "median", "std", "variance",
    "join", "merge", "pivot", "compare", "analysis", "statistics",
    "pm25", "pm10", "pm2.5", "air quality", "pollution", "sensor", "parameter",
    "location", "datetime", "value", "units", "measurement"
])

FINANCE_KEYWORDS = frozenset([
    "stock", "stocks", "price", "market", "ticker", "earnings", "revenue", "profit",
    "analyst", "rating", "quote", "dividend", "ratio", "balance", "cash flow",
    "aapl", "tsla", "msft", "googl", "amzn", "meta", "nvda", "financial"
])

WEB_KEYWORDS = frozenset([
    "news", "latest", "current", "today", "search", "recent", "happening",
    "update", "article", "web", "internet", "online"
])

MODEL_KEYWORDS = frozenset([
    "document", "pdf", "file", "lookup", "find", "search", "account",
    "customer", "id", "hello", "hi", "thanks", "thank", "help", "please"
])


FINANCE_PRIORITY_PATTERNS = (
    r"\bstock\b",
    r"\bstocks\b",
    r"\bticker\b",
    r"\bshare price\b",
    r"\bshares\b",
    r"\bmarket cap\b",
    r"\bquote\b",
    r"\bgoogl\b",
    r"\bgoog\b",
    r"\bgoogle stock\b",
    r"\bgoogle stocks\b",
    r"\balphabet stock\b",
    r"\baapl\b",
    r"\bmsft\b",
    r"\btsla\b",
    r"\bnvda\b",
)


SQL_PRIORITY_PATTERNS = (
    r"\baverage\b",
    r"\bsum\b",
    r"\bcount\b",
    r"\bcorrelation\b",
    r"\bcorr\b",
    r"\bgroup by\b",
    r"\btop \d+\b",
    r"\bdatabase\b",
    r"\bsql\b",
)


def route_with_rules(query: str) -> str | None:
    """
    Hard rules for high-signal intents that should not be left to embeddings.
    """
    query_lower = query.lower()

    if any(re.search(pattern, query_lower) for pattern in FINANCE_PRIORITY_PATTERNS):
        return RouteTarget.FINANCE.value

    if any(re.search(pattern, query_lower) for pattern in SQL_PRIORITY_PATTERNS):
        return RouteTarget.SQL.value

    return None


def route_with_keywords(query: str) -> str:
    """
    Fallback keyword-based routing.
    Used when embedding confidence is low.
    """
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    # Count keyword matches
    scores = {
        RouteTarget.SQL.value: len(query_words & SQL_KEYWORDS),
        RouteTarget.FINANCE.value: len(query_words & FINANCE_KEYWORDS),
        RouteTarget.WEB_SEARCH.value: len(query_words & WEB_KEYWORDS),
        RouteTarget.MODEL.value: len(query_words & MODEL_KEYWORDS),
    }
    
    max_score = max(scores.values())
    
   
    if max_score == 0:
        return RouteTarget.MODEL.value
    
    return max(scores, key=scores.get)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def fast_route(query: str) -> str:
    """
    Main routing function.
    Uses embeddings first (accurate + fast), keywords as fallback.
    """
    rule_result = route_with_rules(query)
    if rule_result is not None:
        return rule_result
    return route_with_embeddings(query)

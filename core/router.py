from functools import lru_cache
import re
import numpy as np
from core.schemas import RouteTarget

# ==============================================================================
# ROUTE DESCRIPTIONS (Used for Embedding Similarity)
# ==============================================================================

ROUTE_DESCRIPTIONS = {
    RouteTarget.SQL.value: """
        Internal business database queries, SQL on CSV spreadsheets, sales data, monthly sales trends,
        customer transactions in database, calculations, aggregations, averages, sums, counts,
        correlations, filtering data, grouping, ranking, plotting charts from internal financial tables,
        listing database tables and columns, schema inspection
    """,
    RouteTarget.FINANCE.value: """
        Public stock market quotes, share prices, ticker symbols, Wall Street analyst ratings,
        PE ratios, market capitalization, dividends, public company quarterly earnings reports,
        balance sheets, cash flow from Yahoo Finance or Twelve Data, historical stock charts
    """,
    RouteTarget.WEB_SEARCH.value: """
        Current news, breaking headlines, latest updates, recent global events, presidential elections,
        Federal Reserve interest rate decisions, external internet search, public information
    """,
    RouteTarget.MODEL.value: """
        Semantic search in uploaded PDF and Word documents, risk disclosures in annual reports,
        exact lookup by customer ID or account number, listing uploaded files in system,
        casual greetings, hello, hi, how are you, thanks, conversational chat
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
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


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


# ==============================================================================
# KEYWORDS & PATTERNS
# ==============================================================================

SQL_KEYWORDS = frozenset([
    "average", "sum", "count", "total", "calculate", "correlation", "corr",
    "group", "filter", "where", "top", "bottom", "rank", "aggregate",
    "query", "table", "tables", "database", "csv", "mean", "median", "std", "variance",
    "join", "merge", "pivot", "statistics", "sales", "revenue by",
    "pm25", "pm10", "pm2.5", "air quality", "pollution", "sensor", "parameter",
    "location", "datetime", "value", "units", "measurement"
])

FINANCE_KEYWORDS = frozenset([
    "stock", "stocks", "price", "market", "ticker", "earnings", "profit",
    "analyst", "rating", "ratings", "quote", "dividend", "dividends", "ratio", "pe ratio",
    "balance sheet", "cash flow", "market cap",
    "aapl", "tsla", "msft", "googl", "goog", "google", "alphabet", "amzn", "meta",
    "nvda", "nifty", "sensex", "reliance"
])

WEB_KEYWORDS = frozenset([
    "news", "latest news", "search", "happening",
    "article", "web", "internet", "online", "election", "federal reserve",
    "fed", "interest rate", "president", "presidential"
])

MODEL_KEYWORDS = frozenset([
    "document", "documents", "pdf", "file", "files", "lookup", "find", "search", "account",
    "customer", "id", "hello", "hi", "hey", "how are you", "thanks", "thank", "help", "please",
    "annual report", "risk factors"
])

PUBLIC_COMPANIES = (
    r"\baapl\b", r"\btsla\b", r"\bmsft\b", r"\bnvda\b", r"\bgoogl?\b",
    r"\bgoogle\b", r"\balphabet\b", r"\bamzn\b", r"\bmeta\b", r"\breliance\b",
    r"\bnifty\b", r"\bsensex\b", r"\bapple\b", r"\btesla\b", r"\bmicrosoft\b",
    r"\bnvidia\b", r"\bamazon\b"
)


def route_with_rules(query: str) -> str | None:
    """
    High-signal deterministic rules that bypass embedding ambiguity.
    """
    query_lower = query.strip().lower()

    # 1. Greetings & conversational chat -> MODEL
    if re.search(r"\b(hello|hi|hey|how\s+are\s+you|good\s+(morning|afternoon|evening)|greetings|thanks|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do)\b", query_lower):
        if not any(re.search(pat, query_lower) for pat in (r"\bstock\b", r"\btable\b", r"\bdatabase\b", r"\bsales\b")):
            return RouteTarget.MODEL.value

    # 2. File / Document / Customer ID Lookups -> MODEL
    if re.search(r"\b(customer\s+id|account\s+(number|id)|id\s+\d+|file(s)?\s+(available|uploaded)|what\s+files|uploaded\s+document(s)?|annual\s+report|in\s+our\s+document(s)?|risk\s+factors)\b", query_lower):
        return RouteTarget.MODEL.value

    # 3. Web search & general breaking news / non-stock world events -> WEB_SEARCH
    if re.search(r"\b(who\s+won|presidential\s+election|federal\s+reserve|interest\s+rate\s+decision|latest\s+(news|updates)|today'?s\s+news|recent\s+news|breaking\s+news)\b", query_lower):
        if not any(re.search(pat, query_lower) for pat in (r"\bstock\b", r"\bshares\b", r"\bticker\b")):
            return RouteTarget.WEB_SEARCH.value

    # 4. Internal Database & SQL queries (Tables, sales, data aggregations, CSV queries) -> SQL
    is_internal_data = any(re.search(pat, query_lower) for pat in (
        r"\b(our\s+(financial\s+)?data|our\s+sales|internal\s+data|in\s+our\s+database|in\s+the\s+database)\b",
        r"\b(table(s)?\s+(in|available)|database\s+table|list\s+table(s)?|what\s+tables|columns?\s+do\s+they\s+have)\b",
        r"\b(sales\s+trend|monthly\s+sales|sales\s+data|revenue\s+per\s+customer)\b",
        r"\b(group\s+by|grouped\s+by|correlation\s+between|corr\(|top\s+\d+\s+month)\b",
        r"\b(average|avg|sum|count|median|stddev)\b.*\b(per|by|from|in|grouped)\b",
    ))
    if is_internal_data:
        return RouteTarget.SQL.value

    # 5. Public market, stocks, tickers, analyst ratings, public company comparisons -> FINANCE
    has_company = any(re.search(pat, query_lower) for pat in PUBLIC_COMPANIES)
    has_finance_terms = any(re.search(pat, query_lower) for pat in (
        r"\b(stock(s)?|share(s)?|ticker|market\s+cap|pe\s+ratio|p/e\s+ratio|dividend(s)?)\b",
        r"\b(earnings|analyst\s+rating(s)?|stock\s+price|price\s+of|stock\s+performance)\b",
    ))
    if has_company or has_finance_terms:
        return RouteTarget.FINANCE.value

    # 6. Fallback SQL signals
    if any(re.search(pat, query_lower) for pat in (r"\baverage\b", r"\bsum\b", r"\bcount\b", r"\bcorrelation\b", r"\bcorr\b", r"\bdatabase\b", r"\bsql\b")):
        return RouteTarget.SQL.value

    return None


def route_with_keywords(query: str) -> str:
    """
    Fallback keyword-based routing.
    Used when embedding confidence is low.
    """
    query_lower = query.lower()
    query_words = set(re.findall(r"\b\w+\b", query_lower))
    
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


def fast_route(query: str) -> str:
    """
    Main routing function.
    Deterministic rules first -> sentence embeddings -> keyword fallback.
    """
    rule_result = route_with_rules(query)
    if rule_result is not None:
        return rule_result
    return route_with_embeddings(query)

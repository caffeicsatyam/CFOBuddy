from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


MAX_CHAT_MESSAGE_CHARS = 8_000
MAX_SQL_RESULT_ROWS = 200
DEFAULT_SQL_LIMIT = 50


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    reason_code: str = "allowed"
    message: str = ""
    content: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action != GuardrailAction.BLOCK


BLOCKED_CHAT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(ignore|bypass|override)\b.{0,80}\b(system|developer|previous)\b.{0,80}\b(instruction|prompt|message)s?\b", "prompt_injection"),
    (r"\b(system|developer)\s+prompt\b", "system_prompt_request"),
    (r"\b(show|print|reveal|leak|dump|exfiltrate)\b.{0,80}\b(env|environment|secret|api[_ -]?key|token|password|credential|database_url)\b", "secret_request"),
    (r"\b(database_url|mongodb_url|groq_api_key|twelve_data_api_key|cfo_buddy_api_key|jwt_secret)\b", "secret_request"),
)

# CFO Buddy is intentionally a financial analysis assistant. Keep general
# software-development prompts out of the agent so they cannot be routed to
# database or web tools as unrelated queries.
BLOCKED_NON_FINANCE_PATTERNS: tuple[str, ...] = (
    r"\b(?:write|generate|create|provide|show|give|help(?:\s+me)?\s+(?:write|build))\b.{0,120}\b(?:code|function|script|program|algorithm|implementation)\b",
    r"\b(?:reverse|implement|build|debug|fix|code)\b.{0,120}\b(?:linked\s+list|binary\s+tree|array|stack|queue|leetcode|python|javascript|typescript|java|c\+\+)\b",
)

IN_SCOPE_CHAT_PATTERNS: tuple[str, ...] = (
    # Core finance, accounting & corporate terms
    r"\b(?:finance|financial|cfo|accounting|revenue|sales|income|expense|profit(?:ability|able)?|loss|p&l|pnl|ebitda|ebit|cash(?:\s+flow)?|balance\s+sheet|asset|liabilit(?:y|ies)|equity|budget(?:ing)?|forecast(?:ing)?|tax(?:es)?|invoice|vendor|customer|accounts?\s+(?:payable|receivable)|transaction|payment|spend|cost(?:s)?|payroll|audit|ledger|trial\s+balance|depreciation|amortization|working\s+capital|liquidity|solvency)\b",
    # Markets, stocks, trading & investment
    r"\b(?:stock|share(?:s)?|market|ticker|price|earnings|dividend|valuation|portfolio|investment|investor|return(?:s)?|loan|debt|interest|credit|bank(?:ing)?|currency|exchange\s+rate|financial\s+ratio|kpi|quarter|fiscal|annual\s+report|ipo|listing|delisting|public\s+offering|buyback|split|merger|acquisition|m&a|takeover|divestiture|spinoff|spin[\s-]?off)\b",
    # Mutual funds, ETFs, indices, crypto
    r"\b(?:mutual\s+fund|etf|index|indices|nifty|sensex|nasdaq|s&p|dow\s+jones|ftse|benchmark|nav|aum|sip|crypto|bitcoin|btc|ethereum|eth|blockchain|defi|nft)\b",
    # Economic & macro terms
    r"\b(?:gdp|inflation|deflation|recession|monetary\s+policy|fiscal\s+policy|interest\s+rate|fed|rbi|central\s+bank|cpi|ppi|unemployment|trade\s+deficit|surplus|subsidy|tariff|bond|yield|treasury|sovereign|forex|commodity|crude\s+oil|gold|silver|copper)\b",
    # Company/sector analysis keywords
    r"\b(?:sector|industry|compan(?:y|ies)|startup|unicorn|conglomerate|subsidiary|holding\s+company|blue\s+chip|mid[\s-]?cap|small[\s-]?cap|large[\s-]?cap|penny\s+stock|growth\s+stock|value\s+stock|analyst|rating|target\s+price|consensus|guidance|outlook|forecast|estimate|quarterly|annual|yoy|y-o-y|qoq|q-o-q|cagr|margin|ratio|pe|p/e|p/b|roe|roa|roce|eps|book\s+value|face\s+value|market\s+cap|enterprise\s+value)\b",
    # File/data/upload references
    r"\b(?:uploaded|upload|file|files|document|documents|dataset|data(?:set)?|csv|xlsx|excel|pdf|docx|table|tables|column|columns|row|rows|schema|chart|graph|visuali[sz]e|plot)\b",
    # General financial question patterns — "when will X IPO", "how is Y performing", etc.
    r"(?:when|what|how|will|is|are|should|can|could|does|did|which)\b.{0,60}\b(?:ipo|list(?:ing|ed)?|stock|share|price|revenue|profit|valuation|market|earning|quarter|annual|grow(?:th|ing)?|perform(?:ance|ing)?|invest|fund|return|acqui(?:re|sition)|merg(?:e|er|ing)|split|dividend|buyback|debt|loan|bond|rate|inflation|gdp|forecast|outlook|financ(?:e|ial|ials)|report|result|analys(?:is|e)|trade|trad(?:e|ing)|buy|sell|hold|rally|crash|correction|bull|bear)\b",
)

IN_SCOPE_CONVERSATIONAL_MESSAGES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "help",
        "what can you do",
    }
)
FINANCIAL_ADVICE_PATTERNS: tuple[str, ...] = (
    r"\bguarantee(?:d)?\b.{0,80}\b(return|profit|gain|performance)\b",
    r"\bwhat should i buy\b",
    r"\btell me what to invest in\b",
)

INTERNAL_OUTPUT_PATTERNS: tuple[str, ...] = (
    r"(?is)system prompt:",
    r"(?is)developer message:",
    r"(?is)CFO_BUDDY_[A-Z0-9_]+",
    r"(?is)DATABASE_URL\s*=",
    r"(?is)MONGODB_URL\s*=",
)

BLOCKED_SQL_PATTERN = re.compile(
    r"""
    \b(
        alter|analyze|attach|begin|call|comment|commit|copy|create|delete|detach|
        drop|execute|grant|insert|listen|lock|merge|notify|reindex|reset|revoke|
        rollback|set|truncate|unlisten|update|vacuum
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

SQL_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/)")


def is_in_scope_chat_request(content: str) -> bool:
    normalized = re.sub(r"\s+", " ", content.strip().lower()).strip(" .!?")
    if normalized in IN_SCOPE_CONVERSATIONAL_MESSAGES:
        return True
    return any(re.search(pattern, content, re.IGNORECASE | re.DOTALL) for pattern in IN_SCOPE_CHAT_PATTERNS)

def validate_chat_input(message: str | None) -> GuardrailResult:
    content = (message or "").strip()
    if not content:
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "empty_message",
            "Please enter a message before sending.",
        )

    if len(content) > MAX_CHAT_MESSAGE_CHARS:
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "message_too_large",
            f"Please keep messages under {MAX_CHAT_MESSAGE_CHARS:,} characters.",
        )

    for pattern, reason_code in BLOCKED_CHAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            return GuardrailResult(
                GuardrailAction.BLOCK,
                reason_code,
                "I cannot help reveal hidden instructions, credentials, secrets, or internal configuration.",
            )

    if any(re.search(pattern, content, re.IGNORECASE | re.DOTALL) for pattern in BLOCKED_NON_FINANCE_PATTERNS):
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "out_of_scope_programming_request",
            "CFO Buddy focuses on financial analysis and cannot assist with software development requests.",
        )

    financial_advice_request = any(
        re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        for pattern in FINANCIAL_ADVICE_PATTERNS
    )

    if financial_advice_request:
        return GuardrailResult(
            GuardrailAction.MODIFY,
            "financial_advice_caveat",
            content=content,
        )

    return GuardrailResult(GuardrailAction.ALLOW, content=content)


def sanitize_response(content: str) -> str:
    sanitized = remove_chart_payload(content or "")
    for pattern in INTERNAL_OUTPUT_PATTERNS:
        sanitized = re.sub(pattern, "[redacted]", sanitized)
    return sanitized.strip()


def remove_chart_payload(content: str) -> str:
    clean = content or ""
    for marker in ("CHART_JSON:", "CHART_DATA:"):
        if marker in clean:
            clean = clean.split(marker, maxsplit=1)[0]
    return clean.strip()


def validate_sql(sql: str, allowed_tables: set[str] | None = None) -> GuardrailResult:
    raw_sql = (sql or "").strip()
    if not raw_sql:
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "empty_sql",
            "SQL query is empty.",
        )

    if SQL_COMMENT_PATTERN.search(raw_sql):
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "sql_comments_blocked",
            "SQL comments are not allowed in tool queries.",
        )

    statements = [part.strip() for part in raw_sql.split(";") if part.strip()]
    if len(statements) != 1:
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "multiple_sql_statements",
            "Only one read-only SQL statement is allowed.",
        )

    statement = statements[0]
    normalized = statement.lstrip(" \t\r\n(").upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "non_readonly_sql",
            "Only SELECT or WITH queries are allowed.",
        )

    if BLOCKED_SQL_PATTERN.search(statement):
        return GuardrailResult(
            GuardrailAction.BLOCK,
            "unsafe_sql_keyword",
            "Only read-only SQL queries are allowed.",
        )

    if allowed_tables is not None:
        referenced_tables = extract_referenced_tables(statement)
        disallowed = sorted(referenced_tables - allowed_tables)
        if disallowed:
            return GuardrailResult(
                GuardrailAction.BLOCK,
                "unauthorized_table",
                f"Query references unavailable or unauthorized table(s): {', '.join(disallowed)}.",
            )

    guarded_sql = ensure_select_limit(statement)
    if guarded_sql != statement:
        return GuardrailResult(
            GuardrailAction.MODIFY,
            "limit_added",
            content=guarded_sql,
        )

    return GuardrailResult(GuardrailAction.ALLOW, content=statement)


def extract_referenced_tables(sql: str) -> set[str]:
    references: set[str] = set()
    cte_names = {
        match.group(1).strip('"')
        for match in re.finditer(
            r"(?:with|,)\s+([a-zA-Z_][\w$]*|\"[^\"]+\")\s+as\s*\(",
            sql,
            re.IGNORECASE,
        )
    }
    for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][\w$]*|\"[^\"]+\")", sql, re.IGNORECASE):
        table = match.group(1).strip('"')
        if table.lower() not in {"select"} and table not in cte_names:
            references.add(table)
    return references


def ensure_select_limit(sql: str) -> str:
    if re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE):
        return sql
    if not re.match(r"^\s*select\b", sql, re.IGNORECASE):
        return sql
    return f"{sql.rstrip()} LIMIT {DEFAULT_SQL_LIMIT}"


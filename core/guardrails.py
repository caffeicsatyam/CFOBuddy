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

    if any(re.search(pattern, content, re.IGNORECASE | re.DOTALL) for pattern in FINANCIAL_ADVICE_PATTERNS):
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


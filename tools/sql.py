import os
import json
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text, inspect
from load_data import ensure_csv_tables_loaded, engine, user_table_prefix

load_dotenv()
INTERNAL_TABLE_PREFIXES = ("checkpoint",)
INTERNAL_TABLE_NAMES = {"charts"}

def get_schema_context(username: str = "admin") -> str:
    """Return schema info for LLM context."""
    tables = get_available_tables(username)
    context = "Database Schema:\n"
    for table, cols in tables.items():
        context += f"  {table}: {', '.join(cols)}\n"
    return context


def get_available_tables(username: str = "admin") -> dict:
    """Get all tables and their columns from Neon."""
    ensure_csv_tables_loaded(username)
    inspector = inspect(engine)
    tables = {}
    prefix = f"{user_table_prefix(username)}_"
    for table_name in inspector.get_table_names():
        if (
            "embed" in table_name
            or "vector" in table_name
            or "llamaindex" in table_name
            or table_name in INTERNAL_TABLE_NAMES
            or table_name.startswith(INTERNAL_TABLE_PREFIXES)
        ):
            continue
        if table_name.startswith(prefix):
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            tables[table_name] = columns
    return tables


def format_results(rows, columns) -> str:
    """Format SQL results as readable table."""
    if not rows:
        return "No results found."

    col_widths = [
        max(len(str(col)), max((len(str(row[i])) for row in rows), default=0))
        for i, col in enumerate(columns)
    ]
    header = " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
    separator = "-+-".join("-" * w for w in col_widths)
    lines = [header, separator]

    for row in rows[:50]:
        lines.append(" | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)))

    if len(rows) > 50:
        lines.append(f"... ({len(rows) - 50} more rows)")

    return "\n".join(lines)


def get_sql_hints(error_message: str) -> str:
    """Provide helpful hints based on common SQL errors."""
    hints = []

    if "CORR" in error_message.upper() or "function corr" in error_message.lower():
        hints.append("""
CORR() Function Hint:
   - Requires TWO arguments: CORR(column1, column2)
   - Use CASE statements to pivot categorical data first

   Example for correlating PM10 and PM25:
   WITH pivoted AS (
     SELECT
       datetime,
       MAX(CASE WHEN parameter = 'pm10' THEN value END) AS pm10_value,
       MAX(CASE WHEN parameter = 'pm25' THEN value END) AS pm25_value
     FROM air_quality_data_set
     WHERE parameter IN ('pm10', 'pm25')
     GROUP BY datetime
   )
   SELECT CORR(pm10_value, pm25_value) FROM pivoted
   WHERE pm10_value IS NOT NULL AND pm25_value IS NOT NULL
""")

    if "does not exist" in error_message.lower() and "column" in error_message.lower():
        hints.append("Column doesn't exist. Check spelling and use list_tables() to verify column names.")
        hints.append("If you use CTEs or LAG/LEAD, carry forward every derived column you need later, such as total_sales.")

    if "group by" in error_message.lower():
        hints.append("All non-aggregated columns in SELECT must be in GROUP BY clause.")

    if "syntax error" in error_message.lower():
        hints.append("Check for missing commas, parentheses, or quotes in your query.")

    if "syntax error at or near \"as\"" in error_message.lower():
        hints.append("PostgreSQL cast syntax is CAST(expression AS NUMERIC). Close REPLACE(...) before AS.")

    return "\n".join(hints) if hints else ""


@tool
def sql_query(sql: str, config: RunnableConfig) -> str:
    """
    Execute a SELECT query on the PostgreSQL (Neon) database.

    DATABASE: PostgreSQL (Neon)

    CRITICAL SYNTAX RULES:
    - CORR(x, y): Requires TWO arguments, not one
    - Pivot categorical data with CASE before correlating
    - Use WITH (CTE) for multi-step transformations
    - All non-aggregated SELECT columns must be in GROUP BY

    CORRELATION PATTERN (most common mistake):
    WRONG: SELECT CORR(value) FROM table WHERE category IN ('A', 'B')
    RIGHT:
        WITH pivoted AS (
          SELECT
            datetime,
            MAX(CASE WHEN category = 'A' THEN value END) AS a_value,
            MAX(CASE WHEN category = 'B' THEN value END) AS b_value
          FROM table
          WHERE category IN ('A', 'B')
          GROUP BY datetime
        )
        SELECT CORR(a_value, b_value) FROM pivoted
        WHERE a_value IS NOT NULL AND b_value IS NOT NULL

    If you are unsure what tables or columns exist, call list_tables() first.
    """

    sql_clean = sql.strip().upper()
    if not sql_clean.startswith("SELECT") and not sql_clean.startswith("WITH"):
        return "Only SELECT queries are allowed for safety."

    username = config.get("configurable", {}).get("username", "admin")

    try:
        # FIX: call ensure_csv_tables_loaded() once here; removed the redundant
        # second call that was happening inside the error handler via get_available_tables().
        ensure_csv_tables_loaded(username)
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())
            return f"Query: {sql}\n\nResults ({len(rows)} rows):\n\n{format_results(rows, columns)}"

    except Exception as e:
        error_str = str(e)
        hints = get_sql_hints(error_str)

        # Re-use already-loaded table info — don't call ensure_csv_tables_loaded() again.
        try:
            tables = get_available_tables(username)
            table_info = "\n".join([f"  - {t}: {', '.join(cols)}" for t, cols in tables.items()])
        except Exception:
            table_info = "(could not retrieve table list)"

        error_response = f"SQL Error: {error_str}\n\n"
        if hints:
            error_response += f"{hints}\n\n"
        error_response += f"Available tables:\n{table_info}"

        return error_response


@tool
def list_tables(config: RunnableConfig) -> str:
    """
    List all available database tables and their columns.
    Use this when you need to know what structured data is available for SQL queries.
    """
    try:
        username = config.get("configurable", {}).get("username", "admin")
        tables = get_available_tables(username)
        if not tables:
            return "No tables found. Run: python load_data.py"

        result = ["Available tables in Neon DB:\n"]
        for table_name, columns in tables.items():
            result.append(f"  {table_name}")
            result.append(f"   Columns: {', '.join(columns)}\n")

        return "\n".join(result)

    except Exception as e:
        return f"Error listing tables: {e}"


@tool
def get_sql_examples() -> str:
    """
    Get example SQL query patterns for common analytical tasks.
    Use this when you need guidance on complex query structures.
    """
    examples = """
SQL Query Pattern Examples:

1. CORRELATION between categorical values:
WITH pivoted AS (
  SELECT
    grouping_column,
    MAX(CASE WHEN category = 'A' THEN value END) AS value_a,
    MAX(CASE WHEN category = 'B' THEN value END) AS value_b
  FROM table_name
  WHERE category IN ('A', 'B')
  GROUP BY grouping_column
)
SELECT CORR(value_a, value_b) FROM pivoted
WHERE value_a IS NOT NULL AND value_b IS NOT NULL;

2. RANKING with window functions:
SELECT
  company,
  revenue,
  RANK() OVER (ORDER BY revenue DESC) as rank
FROM financialstatements
WHERE year = 2022;

3. MOVING AVERAGE (time series):
SELECT
  datetime,
  value,
  AVG(value) OVER (ORDER BY datetime ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg_7day
FROM air_quality_data_set
WHERE parameter = 'pm25';

4. PERCENTILE calculations:
SELECT
  parameter,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as median,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as p95
FROM air_quality_data_set
GROUP BY parameter;

5. MONTH-OVER-MONTH decline with LAG():
WITH monthly_sales AS (
  SELECT month_number, SUM(sales) AS total_sales
  FROM financials
  GROUP BY month_number
),
sales_with_lag AS (
  SELECT
    month_number,
    total_sales,
    LAG(total_sales) OVER (ORDER BY month_number) AS prev_month_sales
  FROM monthly_sales
)
SELECT month_number, total_sales, prev_month_sales
FROM sales_with_lag
WHERE total_sales < prev_month_sales
ORDER BY month_number;
"""
    return examples

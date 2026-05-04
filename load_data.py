import os
import glob
import pandas as pd
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
from cfobuddy_logging import configure_logging
from langsmith import traceable

load_dotenv()
logger = configure_logging()

DATABASE_URL = os.getenv("DATABASE_URL")
DATA_FOLDER = "data"
engine = create_engine(
    DATABASE_URL,
    pool_size=3,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
)


def sanitize_table_name(filename: str) -> str:
    """Convert filename to valid PostgreSQL table name."""
    name = os.path.splitext(filename)[0]
    name = name.lower()
    name = name.replace(" ", "_").replace("-", "_").replace(".", "_")
    return name


def maybe_coerce_numeric(series: pd.Series) -> pd.Series:
    """Convert currency-like/object columns to numeric when most values are parseable."""
    if series.dtype != object:
        return series

    raw = series.astype(str).str.strip()
    normalized = raw.replace(
        {
            "": None,
            "-": "0",
            "$-": "0",
            "N/A": None,
            "n/a": None,
        }
    )
    normalized = normalized.str.replace(r"[\$,]", "", regex=True)
    numeric = pd.to_numeric(normalized, errors="coerce")

    non_null_count = series.notna().sum()
    if non_null_count == 0:
        return series

    conversion_ratio = numeric.notna().sum() / non_null_count
    if conversion_ratio < 0.8:
        return series

    return numeric

@traceable(name="load_csvs_to_neon")
def load_csvs_to_neon(csv_paths: list[str] | None = None, force_reload: bool = False):
    csv_files = csv_paths or glob.glob(os.path.join(DATA_FOLDER, "*.csv"))

    if not csv_files:
        logger.warning("No CSV files found in '%s/'", DATA_FOLDER)
        return []

    logger.info("Found %d CSV files", len(csv_files))
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    loaded_tables = []

    for filepath in csv_files:
        filename = os.path.basename(filepath)
        table_name = sanitize_table_name(filename)

        if not force_reload and table_name in existing_tables:
            continue

        try:
            df = pd.read_csv(filepath)

            # Clean column names
            df.columns = (
                df.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
                .str.replace(r"[^\w]", "_", regex=True)
            )

            # Clean currency values before loading
            for col in df.columns:
                df[col] = maybe_coerce_numeric(df[col])

            df.to_sql(
                table_name,
                engine,
                if_exists="replace",
                index=False
            )

            loaded_tables.append(table_name)
            existing_tables.add(table_name)
            logger.info(
                "Loaded '%s' → table '%s' | rows=%d | cols=%s",
                filename, table_name, len(df), ', '.join(df.columns.tolist())
            )

        except Exception as e:
            logger.error("Failed to load '%s' | error=%s", filename, str(e))

    logger.info("Loaded %d tables into Neon: %s", len(loaded_tables), loaded_tables)
    logger.info("CFOBuddy can now run exact SQL queries on your data")
    return loaded_tables


_tables_loaded = False


def ensure_csv_tables_loaded() -> list[str]:
    """Ensure CSV files in data/ are available as Neon tables for SQL tools."""
    global _tables_loaded
    if _tables_loaded:
        return []
    try:
        result = load_csvs_to_neon(force_reload=False)
        _tables_loaded = True
        return result
    except Exception as exc:
        logger.error("Failed to ensure CSV tables are loaded: %s", exc)
        return []


if __name__ == "__main__":
    load_csvs_to_neon(force_reload=True)

import os
import glob
import pandas as pd
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from cfobuddy_logging import configure_logging
from core.user_scope import user_storage_key

logger = configure_logging()

DATA_FOLDER = "data"
SUPPORTED_EXTENSIONS = {".csv", ".pdf", ".xlsx", ".xls", ".docx"}


def _username_from_config(config: RunnableConfig | None) -> str:
    if not config:
        return "admin"
    return str(config.get("configurable", {}).get("username", "admin"))


def _user_folder(username: str) -> str:
    return os.path.join(DATA_FOLDER, user_storage_key(username))


def load_dataframes(folder="data"):
    dataframes = {}
    for filepath in glob.glob(os.path.join(folder, "*.csv")):
        filename = os.path.basename(filepath)
        try:
            df = pd.read_csv(filepath)
            df.columns = df.columns.str.strip().str.lower()
            dataframes[filename] = df
        except Exception as e:
            logger.warning("Could not load %s: %s", filename, e)
    return dataframes

dataframes = load_dataframes()

@tool
def exact_lookup(file_name: str, column: str, value: str, config: RunnableConfig) -> str:
    """
    Perform an exact lookup in a CSV file by matching a column to a value.
    Use this for specific ID lookups, account numbers, card numbers, client IDs etc.

    Args:
        file_name: CSV filename e.g. 'cards_data.csv'
        column: column name to search in e.g. 'client_id', 'id', 'card_number'
        value: exact value to match e.g. '825'


    ALWAYS:
    - If file is NOT tabular, use search_financial_docs instead.
    - EXCEPT TABULAR FILES, DONT SEARCH FOR VALUES AND COLUMNS.
    """
    username = _username_from_config(config)
    user_dataframes = load_dataframes(_user_folder(username))

    if file_name not in user_dataframes:
        available = ", ".join(user_dataframes.keys())
        return f"File '{file_name}' not found. Available files: {available}"

    df = user_dataframes[file_name]
    col = column.strip().lower()

    if col not in df.columns:
        available = ", ".join(df.columns.tolist())
        return f"Column '{column}' not found in {file_name}. Available columns: {available}"

    matches = df[df[col].astype(str).str.strip() == str(value).strip()]

    if matches.empty:
        return f"No records found in {file_name} where {column} = {value}"

    results = [row.to_string() for _, row in matches.iterrows()]
    return f"[Source: {file_name}]\nFound {len(matches)} record(s):\n\n" + "\n\n---\n\n".join(results)


@tool  
def list_available_files(config: RunnableConfig) -> str:
    """List all available files in the data folder including CSVs, PDFs, Excel and Word docs.
    IMPORTANT: Call this tool ONLY ONCE per conversation. After receiving the file list,
    use the information to answer the user's question directly. Do NOT call this tool again.
    """
    username = _username_from_config(config)
    user_folder = _user_folder(username)
    result = []

    if not os.path.isdir(user_folder):
        return "No files found in data folder."

    user_dataframes = load_dataframes(user_folder)
    all_files = sorted(
        f for f in os.listdir(user_folder)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    )

    if not all_files:
        return "No files found in data folder."

    for filename in all_files:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".csv":
            if filename in user_dataframes:
                cols = ", ".join(user_dataframes[filename].columns.tolist())
                result.append(f"CSV: {filename} — columns: {cols}")
            else:
                result.append(f"CSV: {filename} — (not loaded)")
        elif ext == ".pdf":
            result.append(f"PDF: {filename} — use search_financial_docs to query")
        elif ext in {".xlsx", ".xls"}:
            result.append(f"Excel: {filename} — use search_financial_docs to query")
        elif ext == ".docx":
            result.append(f"Word: {filename} — use search_financial_docs to query")

    return "\n".join(result)

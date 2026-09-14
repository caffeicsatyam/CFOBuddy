import json
from pathlib import Path
import pytest
from core.router import fast_route

DATASET_PATH = Path(__file__).resolve().parent.parent / "evals" / "dataset.json"

def load_dataset():
    if not DATASET_PATH.exists():
        return []
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

DATASET = load_dataset()

@pytest.mark.parametrize("item", DATASET, ids=[item["id"] for item in DATASET])
def test_dataset_routing(item):
    query = item["query"]
    expected = item["expected_route"]
    actual = fast_route(query)
    assert actual == expected, f"Query: '{query}' -> Expected '{expected}', got '{actual}'"

@pytest.mark.parametrize("query,expected", [
    ("What is Microsoft's P/E ratio and stock price today?", "finance_node"),
    ("Show me the sales trend across all regions in our database", "sql_node"),
    ("Search our uploaded documents for risk disclosures", "model"),
    ("Find customer with ID 98765", "model"),
    ("What are the latest updates on the tech industry today?", "web_search_node"),
    ("Hi, good morning!", "model"),
    ("Which tables exist in PostgreSQL?", "sql_node"),
])
def test_custom_edge_cases(query, expected):
    actual = fast_route(query)
    assert actual == expected, f"Query: '{query}' -> Expected '{expected}', got '{actual}'"

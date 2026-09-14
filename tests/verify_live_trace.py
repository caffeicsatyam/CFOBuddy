import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.main import app

def test_live_chat_and_trace():
    client = TestClient(app)
    api_key = os.getenv("CFO_BUDDY_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"}

    print("Sending chat query...")
    chat_payload = {"message": "What is the current stock price and market capitalization of AAPL?", "thread_id": "test_session_live"}
    res = client.post("/chat", json=chat_payload, headers=headers)
    print(f"Chat response status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Chat response: {data.get('response')[:100]}...")

    # Check that trace was recorded
    stats_res = client.get("/api/admin/observability/stats")
    stats = stats_res.json()
    print(f"Total queries in stats: {stats.get('total_queries')}")
    print(f"Total tokens in stats: {stats.get('total_tokens')}")
    print(f"Total cost ($): {stats.get('total_cost_usd')}")

    queries_res = client.get("/api/admin/observability/queries?limit=5")
    traces = queries_res.json()
    print(f"Traces count: {len(traces)}")
    if traces:
        latest = traces[0]
        print(f"Latest trace query: {latest.get('query')}")
        print(f"Latest trace route: {latest.get('routing', {}).get('target')}")
        print(f"Latest trace tokens: {latest.get('tokens')}")
        print(f"Latest trace cost: ${latest.get('cost_usd')}")
        print(f"Latest trace latencies: {latest.get('latency_breakdown_ms')}")

    assert stats.get("total_queries", 0) > 0
    print("[PASS] Live chat and trace verification successful!")

if __name__ == "__main__":
    test_live_chat_and_trace()

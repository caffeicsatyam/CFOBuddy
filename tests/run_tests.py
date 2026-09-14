import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from core.observability import (
    calculate_llm_cost,
    ObservabilityCallbackHandler,
    record_query_telemetry,
    get_observability_summary,
    get_recent_traces,
    get_session_metrics,
)
from api.main import app

def test_cost_calculation():
    cost = calculate_llm_cost("llama-3.3-70b-versatile", 1000, 500)
    expected = (1000 / 1_000_000 * 0.59) + (500 / 1_000_000 * 0.79)
    assert round(cost, 6) == round(expected, 6), f"Cost mismatch: {cost} vs {expected}"
    assert cost > 0
    print("[PASS] test_cost_calculation passed")

def test_callback_handler_tool_and_llm():
    handler = ObservabilityCallbackHandler()
    handler.on_llm_start({"name": "ChatGroq"}, ["Hello"], run_id="run-1")
    
    class FakeMessage:
        usage_metadata = {"input_tokens": 50, "output_tokens": 20, "total_tokens": 70}

    class FakeGen:
        message = FakeMessage()

    class FakeLLMResult:
        llm_output = {"token_usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}}
        generations = [[FakeGen()]]

    handler.on_llm_end(FakeLLMResult(), run_id="run-1")
    assert handler.prompt_tokens == 50
    assert handler.completion_tokens == 20
    assert handler.total_tokens == 70

    handler.on_tool_start({"name": "sql_query"}, "SELECT * FROM sales", run_id="tool-1")
    handler.on_tool_end("Found 5 rows", run_id="tool-1", name="sql_query")
    assert len(handler.tool_calls) == 1
    assert handler.tool_calls[0]["tool"] == "sql_query"
    assert handler.tool_calls[0]["status"] == "success"
    print("[PASS] test_callback_handler_tool_and_llm passed")

async def test_telemetry_recording_and_aggregations():
    handler = ObservabilityCallbackHandler()
    handler.prompt_tokens = 200
    handler.completion_tokens = 80
    handler.total_tokens = 280
    handler.total_llm_latency_ms = 450.0
    handler.tool_calls = [{"tool": "sql_query", "latency_ms": 120.0, "status": "success"}]

    trace = await record_query_telemetry(
        user_id="test_user",
        session_id="session_123",
        query="What are total sales by quarter?",
        response_preview="Total sales were $1.2M",
        routing_target="sql_node",
        routing_latency_ms=15.0,
        guardrails_latency_ms=5.0,
        total_latency_ms=590.0,
        callback_handler=handler,
    )

    assert trace["tokens"]["total_tokens"] == 280
    assert trace["cost_usd"] > 0
    assert trace["routing"]["target"] == "sql_node"
    assert len(trace["tool_calls"]) == 1

    summary = await get_observability_summary(user_id="test_user")
    assert summary["total_queries"] >= 1
    assert summary["total_tokens"] >= 280
    assert summary["total_cost_usd"] > 0
    assert "sql_node" in summary["routes"]

    sessions = await get_session_metrics(user_id="test_user")
    assert any(s["session_id"] == "session_123" for s in sessions)
    print("[PASS] test_telemetry_recording_and_aggregations passed")

def test_api_endpoints():
    client = TestClient(app)
    
    # 1. Stats endpoint
    res_stats = client.get("/api/admin/observability/stats")
    assert res_stats.status_code == 200, f"Stats failed: {res_stats.text}"
    data = res_stats.json()
    assert "total_queries" in data
    assert "total_tokens" in data
    assert "total_cost_usd" in data
    assert "avg_latency_ms" in data

    # 2. Queries endpoint
    res_queries = client.get("/api/admin/observability/queries?limit=10")
    assert res_queries.status_code == 200
    assert isinstance(res_queries.json(), list)

    # 3. Tools endpoint
    res_tools = client.get("/api/admin/observability/tools")
    assert res_tools.status_code == 200
    assert isinstance(res_tools.json(), list)

    # 4. Sessions endpoint
    res_sessions = client.get("/api/admin/observability/sessions")
    assert res_sessions.status_code == 200
    assert isinstance(res_sessions.json(), list)

    # 5. HTML Dashboard endpoint
    res_dash = client.get("/admin/observability")
    assert res_dash.status_code == 200
    assert "text/html" in res_dash.headers.get("content-type", "")
    assert "CFOBuddy Observability" in res_dash.text
    print("[PASS] test_api_endpoints passed")

async def main():
    test_cost_calculation()
    test_callback_handler_tool_and_llm()
    await test_telemetry_recording_and_aggregations()
    test_api_endpoints()
    print("\nALL OBSERVABILITY & TRACING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())

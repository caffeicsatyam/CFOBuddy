from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# Ensure standard LangChain/LangSmith environment variables are aligned
if os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1") or os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if not os.getenv("LANGSMITH_PROJECT"):
        os.environ["LANGSMITH_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "CFOBuddy")

# Pricing per 1,000,000 tokens (USD)
PRICING_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "openai/gpt-oss-120b": {"input": 0.59, "output": 0.79},
    "openai/gpt-oss-20b": {"input": 0.15, "output": 0.20},
    "qwen/qwen3.8-27b": {"input": 0.20, "output": 0.30},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "gemma2-9b-it": {"input": 0.20, "output": 0.20},
    "default": {"input": 0.59, "output": 0.79},
}

# In-memory buffer fallback (retains last 500 queries)
_in_memory_traces: list[dict[str, Any]] = []
MAX_IN_MEMORY_TRACES = 500


def calculate_llm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate LLM cost based on input/output tokens and model pricing."""
    rates = PRICING_PER_1M_TOKENS.get(model_name.lower()) or PRICING_PER_1M_TOKENS["default"]
    prompt_cost = (prompt_tokens / 1_000_000.0) * rates["input"]
    comp_cost = (completion_tokens / 1_000_000.0) * rates["output"]
    return round(prompt_cost + comp_cost, 6)


class ObservabilityCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler to capture token usage, tool latency,
    and LLM invocation durations per query turn.
    """

    def __init__(self):
        super().__init__()
        self.tool_calls: list[dict[str, Any]] = []
        self._tool_start_times: dict[str, float] = {}
        self._llm_start_times: dict[str, float] = {}
        self.llm_calls: list[dict[str, Any]] = []

        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_llm_latency_ms: float = 0.0
        self.model_name: str = os.getenv("LLM_MODEL_NAME", "llama-3.3-70b-versatile")

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: Any, **kwargs: Any
    ) -> None:
        self._llm_start_times[str(run_id)] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: Any, **kwargs: Any) -> None:
        duration_ms = 0.0
        start_time = self._llm_start_times.pop(str(run_id), None)
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.total_llm_latency_ms += duration_ms

        p_tokens = 0
        c_tokens = 0
        t_tokens = 0
        model = self.model_name

        if response.llm_output:
            token_usage = response.llm_output.get("token_usage") or {}
            p_tokens = token_usage.get("prompt_tokens", 0)
            c_tokens = token_usage.get("completion_tokens", 0)
            t_tokens = token_usage.get("total_tokens", p_tokens + c_tokens)
            model = response.llm_output.get("model_name", model)

        if t_tokens == 0 and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    if msg:
                        usage = getattr(msg, "usage_metadata", None) or getattr(msg, "response_metadata", {}).get("token_usage")
                        if isinstance(usage, dict):
                            p_tokens += usage.get("input_tokens", usage.get("prompt_tokens", 0))
                            c_tokens += usage.get("output_tokens", usage.get("completion_tokens", 0))
                            t_tokens += usage.get("total_tokens", p_tokens + c_tokens)

        if t_tokens == 0:
            prompt_text_len = sum(len(p) for p in (kwargs.get("prompts") or []))
            output_text_len = 0
            for gen_list in response.generations:
                for gen in gen_list:
                    output_text_len += len(getattr(gen, "text", "") or "")
            p_tokens = max(1, prompt_text_len // 4)
            c_tokens = max(1, output_text_len // 4)
            t_tokens = p_tokens + c_tokens

        self.prompt_tokens += p_tokens
        self.completion_tokens += c_tokens
        self.total_tokens += t_tokens
        self.model_name = model

        self.llm_calls.append({
            "run_id": str(run_id),
            "model_name": model,
            "latency_ms": round(duration_ms, 2),
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": t_tokens,
        })

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        start_time = self._llm_start_times.pop(str(run_id), None)
        if start_time:
            self.total_llm_latency_ms += (time.perf_counter() - start_time) * 1000.0

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: Any, **kwargs: Any
    ) -> None:
        self._tool_start_times[str(run_id)] = time.perf_counter()

    def on_tool_end(self, output: Any, *, run_id: Any, **kwargs: Any) -> None:
        duration_ms = 0.0
        start_time = self._tool_start_times.pop(str(run_id), None)
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

        tool_name = kwargs.get("name")
        if not tool_name:
            tool_name = (kwargs.get("serialized") or {}).get("name") or "tool"

        preview = str(output)[:150] if output is not None else ""
        self.tool_calls.append({
            "run_id": str(run_id),
            "tool": tool_name or "tool",
            "latency_ms": round(duration_ms, 2),
            "status": "success",
            "output_preview": preview,
        })

    def on_tool_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        duration_ms = 0.0
        start_time = self._tool_start_times.pop(str(run_id), None)
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

        tool_name = kwargs.get("name") or "unknown_tool"
        self.tool_calls.append({
            "run_id": str(run_id),
            "tool": tool_name,
            "latency_ms": round(duration_ms, 2),
            "status": "error",
            "error": str(error)[:150],
        })


async def record_query_telemetry(
    *,
    user_id: str,
    session_id: str,
    query: str,
    response_preview: str,
    routing_target: str,
    routing_latency_ms: float = 0.0,
    routing_method: str = "fast_route",
    guardrails_latency_ms: float = 0.0,
    total_latency_ms: float = 0.0,
    callback_handler: Optional[ObservabilityCallbackHandler] = None,
) -> dict[str, Any]:
    """
    Construct and persist a telemetry trace for a single query.
    Saves to MongoDB and the in-memory fallback list.
    """
    p_tokens = callback_handler.prompt_tokens if callback_handler else 0
    c_tokens = callback_handler.completion_tokens if callback_handler else 0
    t_tokens = callback_handler.total_tokens if callback_handler else 0
    model = callback_handler.model_name if callback_handler else os.getenv("LLM_MODEL_NAME", "llama-3.3-70b-versatile")
    llm_latency_ms = round(callback_handler.total_llm_latency_ms, 2) if callback_handler else 0.0
    tool_calls = callback_handler.tool_calls if callback_handler else []
    total_tool_latency_ms = round(sum(t.get("latency_ms", 0.0) for t in tool_calls), 2)

    cost_usd = calculate_llm_cost(model, p_tokens, c_tokens)

    trace = {
        "trace_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "session_id": session_id,
        "query": query,
        "response_preview": response_preview[:200] if response_preview else "",
        "routing": {
            "target": routing_target,
            "method": routing_method,
            "latency_ms": round(routing_latency_ms, 2),
        },
        "tokens": {
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": t_tokens,
        },
        "model_name": model,
        "cost_usd": cost_usd,
        "tool_calls": tool_calls,
        "tool_call_count": len(tool_calls),
        "latency_breakdown_ms": {
            "total": round(total_latency_ms, 2),
            "guardrails": round(guardrails_latency_ms, 2),
            "routing": round(routing_latency_ms, 2),
            "llm": llm_latency_ms,
            "tools": total_tool_latency_ms,
        },
    }

    # Add to in-memory store
    _in_memory_traces.insert(0, trace)
    if len(_in_memory_traces) > MAX_IN_MEMORY_TRACES:
        _in_memory_traces.pop()

    # Persist to MongoDB if available
    try:
        from core.database import get_db
        db = get_db()
        if db is not None:
            await db["telemetry_traces"].insert_one(dict(trace))
    except Exception:
        pass

    return trace


async def get_recent_traces(
    limit: int = 50,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve recent query telemetry traces."""
    try:
        from core.database import get_db
        db = get_db()
        if db is not None:
            query_filter: dict[str, Any] = {}
            if user_id:
                query_filter["user_id"] = user_id
            if session_id:
                query_filter["session_id"] = session_id

            cursor = db["telemetry_traces"].find(query_filter, {"_id": 0}).sort("timestamp", -1).limit(limit)
            traces = await cursor.to_list(length=limit)
            if traces:
                return traces
    except Exception:
        pass

    results = _in_memory_traces
    if user_id:
        results = [t for t in results if t.get("user_id") == user_id]
    if session_id:
        results = [t for t in results if t.get("session_id") == session_id]
    return results[:limit]


async def get_observability_summary(user_id: Optional[str] = None) -> dict[str, Any]:
    """Aggregate high-level observability stats."""
    traces = await get_recent_traces(limit=MAX_IN_MEMORY_TRACES, user_id=user_id)

    total_queries = len(traces)
    total_prompt_tokens = sum(t.get("tokens", {}).get("prompt_tokens", 0) for t in traces)
    total_completion_tokens = sum(t.get("tokens", {}).get("completion_tokens", 0) for t in traces)
    total_tokens = total_prompt_tokens + total_completion_tokens
    total_cost_usd = round(sum(t.get("cost_usd", 0.0) for t in traces), 6)
    avg_latency = round(sum(t.get("latency_breakdown_ms", {}).get("total", 0.0) for t in traces) / total_queries, 2) if total_queries > 0 else 0.0
    avg_cost = round(total_cost_usd / total_queries, 6) if total_queries > 0 else 0.0

    routes: dict[str, int] = {}
    for t in traces:
        target = t.get("routing", {}).get("target", "unknown")
        routes[target] = routes.get(target, 0) + 1

    tools_map: dict[str, dict[str, Any]] = {}
    for t in traces:
        for tc in t.get("tool_calls", []):
            name = tc.get("tool", "unknown")
            if name not in tools_map:
                tools_map[name] = {"count": 0, "total_latency_ms": 0.0, "errors": 0}
            tools_map[name]["count"] += 1
            tools_map[name]["total_latency_ms"] += tc.get("latency_ms", 0.0)
            if tc.get("status") == "error":
                tools_map[name]["errors"] += 1

    tool_stats = [
        {
            "tool": name,
            "call_count": stats["count"],
            "avg_latency_ms": round(stats["total_latency_ms"] / stats["count"], 2),
            "total_latency_ms": round(stats["total_latency_ms"], 2),
            "error_rate": round(stats["errors"] / stats["count"], 4),
        }
        for name, stats in tools_map.items()
    ]
    tool_stats.sort(key=lambda x: x["call_count"], reverse=True)

    return {
        "total_queries": total_queries,
        "total_tokens": total_tokens,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_cost_usd": total_cost_usd,
        "avg_latency_ms": avg_latency,
        "avg_cost_per_query_usd": avg_cost,
        "routes": routes,
        "tools": tool_stats,
        "langsmith": {
            "enabled": os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1"),
            "project": os.getenv("LANGSMITH_PROJECT", "CFOBuddy"),
            "endpoint": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        }
    }


async def get_session_metrics(user_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Aggregate telemetry per user session / thread."""
    traces = await get_recent_traces(limit=MAX_IN_MEMORY_TRACES, user_id=user_id)
    sessions: dict[str, dict[str, Any]] = {}

    for t in traces:
        s_id = t.get("session_id", "default")
        u_id = t.get("user_id", "admin")
        if s_id not in sessions:
            sessions[s_id] = {
                "session_id": s_id,
                "user_id": u_id,
                "query_count": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "total_latency_ms": 0.0,
                "tool_calls_count": 0,
                "last_active": t.get("timestamp"),
            }
        sessions[s_id]["query_count"] += 1
        sessions[s_id]["total_tokens"] += t.get("tokens", {}).get("total_tokens", 0)
        sessions[s_id]["total_cost_usd"] = round(sessions[s_id]["total_cost_usd"] + t.get("cost_usd", 0.0), 6)
        sessions[s_id]["total_latency_ms"] += t.get("latency_breakdown_ms", {}).get("total", 0.0)
        sessions[s_id]["tool_calls_count"] += t.get("tool_call_count", 0)

    result = list(sessions.values())
    for s in result:
        s["avg_latency_ms"] = round(s["total_latency_ms"] / s["query_count"], 2) if s["query_count"] > 0 else 0.0
    result.sort(key=lambda x: x["last_active"] or "", reverse=True)
    return result

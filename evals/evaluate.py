"""
CFO Buddy — Multi-Agent Evaluation Framework
===============================================
Evaluates the LangGraph multi-agent system across 4 agent modes using
RAGAS-style metrics adapted for agentic tool-calling pipelines.

Agent Modes:
  model         → document search, file listings, greetings, lookups
  sql_node      → SQL queries on structured CSV/DB data
  finance_node  → live stock/market data via APIs
  web_search_node → external web search

Metrics:
  ── Routing ──
  Routing Accuracy      — did the fast_route send it to the correct expert?

  ── Tool Selection ──
  Tool Precision        — of tools called, how many were truly needed?
  Tool Recall           — of tools needed, how many were actually called?
  Tool F1 Score         — harmonic mean of precision and recall

  ── Response Quality (LLM-as-Judge via Groq) ──
  Faithfulness          — does the answer stick to tool/context results?
  Answer Relevancy      — does the answer actually address the question?

  ── Operational ──
  Completion Rate       — % of queries that finished without error
  Avg / Min / Max Latency — end-to-end timing per query

  ── Per-Agent Breakdown ──
  Metrics broken down by agent mode (sql, finance, web, model)

Evaluation Flow:
  1. Load dataset.json with test questions + expected routes/tools/references
  2. Run each query through the fast_route router (routing accuracy)
  3. Invoke the full CFOBuddy graph pipeline (tool selection + response)
  4. Score with LLM-as-Judge for Faithfulness and Answer Relevancy
  5. Aggregate and save results to evals/eval_store/results.json

Run:
  python evals/evaluate.py
  python evals/evaluate.py --skip-invoke    # routing-only (fast, no LLM calls)
"""

import json
import time
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Ensure we can import from the project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import HumanMessage
from core.graph import CFOBuddy
from core.router import fast_route
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

EVAL_STORE = Path(__file__).resolve().parent / "eval_store"


# ══════════════════════════════════════════════════════════════════════════════
# METRIC HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def calc_precision_recall_f1(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def extract_tool_calls(state: dict) -> list[str]:
    """Extract all tool names called from the graph state messages."""
    tools = []
    for msg in state.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tools.append(tc["name"])
    return tools


def extract_tool_results(state: dict) -> list[str]:
    """Extract tool result content from ToolMessages."""
    results = []
    for msg in state.get("messages", []):
        if getattr(msg, "type", "") == "tool":
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            results.append(content[:500])  # truncate to avoid token overflow
    return results


def extract_final_answer(state: dict) -> str:
    """Get the last AI message content as the final answer."""
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "type", "") == "ai":
            content = msg.content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict):
                        parts.append(block.get("text", "") or block.get("content", ""))
                return "\n".join(parts)
            return str(content) if content else ""
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# LLM-AS-JUDGE (Faithfulness + Answer Relevancy)
# ══════════════════════════════════════════════════════════════════════════════

def llm_judge(prompt: str) -> str:
    """Call Groq LLM for evaluation scoring with retries."""
    import time
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return "N/A"
        client = Groq(api_key=api_key)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.0,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    if attempt < max_retries - 1:
                        time.sleep(5 * (attempt + 1))
                        continue
                return f"ERROR: {e}"
        return "ERROR: Max retries exceeded"
    except Exception as e:
        return f"ERROR: {e}"


def score_faithfulness(question: str, answer: str, context: str) -> float:
    """
    Faithfulness — does the answer stick to the retrieved context?
    Score 0.0 to 1.0
    """
    if not answer or not context or answer.startswith("[Error"):
        return 0.0

    prompt = f"""You are an evaluation judge. Score the FAITHFULNESS of the answer.
Faithfulness means: does the answer ONLY contain information supported by the context?
If the answer makes claims not in the context, score lower.

QUESTION: {question}
CONTEXT: {context[:1500]}
ANSWER: {answer[:1000]}

Respond with ONLY a number between 0.0 and 1.0 (e.g. 0.85). Nothing else."""

    result = llm_judge(prompt)
    try:
        score = float(result.strip())
        return max(0.0, min(1.0, score))
    except (ValueError, TypeError):
        return 0.0


def score_answer_relevancy(question: str, answer: str) -> float:
    """
    Answer Relevancy — does the answer actually address the question?
    Score 0.0 to 1.0
    """
    if not answer or answer.startswith("[Error"):
        return 0.0

    prompt = f"""You are an evaluation judge. Score the ANSWER RELEVANCY.
Answer Relevancy means: does the answer directly and completely address the question?
A perfect score means the answer fully addresses what was asked.

QUESTION: {question}
ANSWER: {answer[:1000]}

Respond with ONLY a number between 0.0 and 1.0 (e.g. 0.85). Nothing else."""

    result = llm_judge(prompt)
    try:
        score = float(result.strip())
        return max(0.0, min(1.0, score))
    except (ValueError, TypeError):
        return 0.0


def score_context_precision(expected_tools: list, called_tools: list) -> float:
    """
    Context Precision — of tools called, how many were truly relevant?
    Adapted: uses tool selection as a proxy for context precision.
    """
    if not called_tools:
        return 1.0 if not expected_tools else 0.0
    expected_set = set(expected_tools)
    called_set = set(called_tools)
    relevant = len(called_set & expected_set)
    return round(relevant / len(called_set), 4) if called_set else 0.0


def score_context_recall(expected_tools: list, called_tools: list) -> float:
    """
    Context Recall — did retrieval surface ALL info needed?
    Adapted: did the agent call ALL the expected tools?
    """
    if not expected_tools:
        return 1.0
    expected_set = set(expected_tools)
    called_set = set(called_tools)
    recalled = len(expected_set & called_set)
    return round(recalled / len(expected_set), 4)


# ══════════════════════════════════════════════════════════════════════════════
# PER-AGENT METRICS AGGREGATOR
# ══════════════════════════════════════════════════════════════════════════════

class AgentMetrics:
    """Collects and aggregates metrics per agent mode."""

    def __init__(self):
        self.data = defaultdict(lambda: {
            "total": 0, "routing_correct": 0, "completed": 0, "errored": 0,
            "tp": 0, "fp": 0, "fn": 0,
            "latencies": [],
            "faithfulness_scores": [],
            "relevancy_scores": [],
            "context_precision_scores": [],
            "context_recall_scores": [],
        })

    def record(self, agent: str, routing_correct: bool, completed: bool,
               tp: int, fp: int, fn: int, latency: float,
               faithfulness: float, relevancy: float,
               ctx_precision: float, ctx_recall: float):
        d = self.data[agent]
        d["total"] += 1
        d["routing_correct"] += int(routing_correct)
        d["completed"] += int(completed)
        d["errored"] += int(not completed)
        d["tp"] += tp
        d["fp"] += fp
        d["fn"] += fn
        d["latencies"].append(latency)
        d["faithfulness_scores"].append(faithfulness)
        d["relevancy_scores"].append(relevancy)
        d["context_precision_scores"].append(ctx_precision)
        d["context_recall_scores"].append(ctx_recall)

    def summary(self) -> dict:
        out = {}
        for agent, d in self.data.items():
            n = d["total"]
            tool_scores = calc_precision_recall_f1(d["tp"], d["fp"], d["fn"])
            lats = d["latencies"]
            out[agent] = {
                "total_queries": n,
                "routing_accuracy": round(d["routing_correct"] / n, 4) if n else 0,
                "completion_rate": round(d["completed"] / n, 4) if n else 0,
                "tool_precision": tool_scores["precision"],
                "tool_recall": tool_scores["recall"],
                "tool_f1": tool_scores["f1"],
                "avg_latency": round(sum(lats) / len(lats), 2) if lats else 0,
                "min_latency": round(min(lats), 2) if lats else 0,
                "max_latency": round(max(lats), 2) if lats else 0,
                "avg_faithfulness": round(sum(d["faithfulness_scores"]) / n, 4) if n else 0,
                "avg_relevancy": round(sum(d["relevancy_scores"]) / n, 4) if n else 0,
                "avg_context_precision": round(sum(d["context_precision_scores"]) / n, 4) if n else 0,
                "avg_context_recall": round(sum(d["context_recall_scores"]) / n, 4) if n else 0,
            }
        return out


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def run_evaluation(skip_invoke: bool = False):
    EVAL_STORE.mkdir(parents=True, exist_ok=True)

    evals_dir = Path(__file__).resolve().parent
    dataset_path = evals_dir / "dataset.json"

    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    total_queries = len(dataset)
    results = []
    agent_metrics = AgentMetrics()

    # Global accumulators
    routing_correct = 0
    total_tp, total_fp, total_fn = 0, 0, 0
    completed_count = 0
    all_latencies = []
    all_faithfulness = []
    all_relevancy = []
    all_ctx_precision = []
    all_ctx_recall = []

    start_time = time.time()

    print(f"""
{'='*62}
  CFO Buddy — Multi-Agent Evaluation Framework
{'='*62}
  Model:      llama-3.1-8b-instant (Groq)
  Questions:  {total_queries}
  Modes:      model | sql_node | finance_node | web_search_node
  Metrics:    Routing Accuracy, Tool F1, Faithfulness,
              Answer Relevancy, Context Precision/Recall,
              Completion Rate, Latency
{'='*62}
""", flush=True)

    for i, item in enumerate(dataset):
        query = item["query"]
        qid = item["id"]
        qtype = item["type"]
        expected_route = item["expected_route"]
        expected_tools = set(item["expected_tools"])
        reference = item.get("reference_answer", "")

        # ── 1. Router Test ────────────────────────────────────────────────
        actual_route = fast_route(query)
        is_route_correct = actual_route == expected_route
        if is_route_correct:
            routing_correct += 1

        # ── 2. Full Pipeline (optional) ──────────────────────────────────
        called_tools_list = []
        final_answer = ""
        tool_context = ""
        latency = 0.0
        completed = True

        if not skip_invoke:
            config = {
                "configurable": {"thread_id": f"eval_{qid}_{int(time.time())}"},
                "recursion_limit": 25,
            }
            q_start = time.time()
            
            # Retry loop for rate limits
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt == 0:
                        print(f"  [{i+1}/{total_queries}] {qtype:13s} | {qid} -> {actual_route:16s} | {query[:50]}...", flush=True)
                    else:
                        print(f"    ↻ Retrying... (Attempt {attempt+1}/{max_retries})", flush=True)
                        
                    state = CFOBuddy.invoke(
                        {"messages": [HumanMessage(content=query)]},
                        config=config,
                    )
                    called_tools_list = extract_tool_calls(state)
                    final_answer = extract_final_answer(state)
                    tool_results = extract_tool_results(state)
                    tool_context = "\n".join(tool_results)
                    completed = True
                    break  # Success
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    if "rate limit" in error_msg or "429" in error_msg:
                        print(f"    ⚠ Rate limit hit: {e}", flush=True)
                        if attempt < max_retries - 1:
                            sleep_time = 15 * (attempt + 1)
                            print(f"      Sleeping for {sleep_time}s...", flush=True)
                            time.sleep(sleep_time)
                            continue
                    
                    print(f"    ✗ ERROR: {e}", flush=True)
                    completed = False
                    final_answer = f"[Error: {e}]"
                    break

            latency = time.time() - q_start
        else:
            print(f"  [{i+1}/{total_queries}] {qtype:13s} | {qid} -> route={actual_route:16s} (expected={expected_route})", flush=True)

        # ── 3. Tool Selection Metrics ────────────────────────────────────
        called_set = set(called_tools_list)
        tp = len(expected_tools & called_set)
        fp = len(called_set - expected_tools)
        fn = len(expected_tools - called_set)
        total_tp += tp
        total_fp += fp
        total_fn += fn

        ctx_precision = score_context_precision(list(expected_tools), called_tools_list)
        ctx_recall = score_context_recall(list(expected_tools), called_tools_list)

        # ── 4. LLM-as-Judge Scoring ──────────────────────────────────────
        faithfulness = 0.0
        relevancy = 0.0
        if not skip_invoke and completed and final_answer:
            faithfulness = score_faithfulness(query, final_answer, tool_context)
            relevancy = score_answer_relevancy(query, final_answer)
            time.sleep(0.3)  # rate limit buffer

        # ── 5. Accumulate ────────────────────────────────────────────────
        if completed:
            completed_count += 1
        all_latencies.append(latency)
        all_faithfulness.append(faithfulness)
        all_relevancy.append(relevancy)
        all_ctx_precision.append(ctx_precision)
        all_ctx_recall.append(ctx_recall)

        agent_metrics.record(
            agent=expected_route,
            routing_correct=is_route_correct,
            completed=completed,
            tp=tp, fp=fp, fn=fn,
            latency=latency,
            faithfulness=faithfulness,
            relevancy=relevancy,
            ctx_precision=ctx_precision,
            ctx_recall=ctx_recall,
        )

        results.append({
            "id": qid,
            "type": qtype,
            "query": query,
            "expected_route": expected_route,
            "actual_route": actual_route,
            "routing_correct": is_route_correct,
            "expected_tools": list(expected_tools),
            "called_tools": called_tools_list,
            "completed": completed,
            "latency_s": round(latency, 2),
            "faithfulness": round(faithfulness, 4),
            "answer_relevancy": round(relevancy, 4),
            "context_precision": round(ctx_precision, 4),
            "context_recall": round(ctx_recall, 4),
            "answer_preview": final_answer[:200] if final_answer else "",
        })

    total_time = time.time() - start_time

    # ── AGGREGATE SCORES ─────────────────────────────────────────────────────
    tool_scores = calc_precision_recall_f1(total_tp, total_fp, total_fn)
    n = total_queries

    overall = {
        "routing_accuracy": round(routing_correct / n, 4),
        "completion_rate": round(completed_count / n, 4),
        "tool_precision": tool_scores["precision"],
        "tool_recall": tool_scores["recall"],
        "tool_f1": tool_scores["f1"],
        "avg_faithfulness": round(sum(all_faithfulness) / n, 4) if not skip_invoke else "N/A",
        "avg_answer_relevancy": round(sum(all_relevancy) / n, 4) if not skip_invoke else "N/A",
        "avg_context_precision": round(sum(all_ctx_precision) / n, 4),
        "avg_context_recall": round(sum(all_ctx_recall) / n, 4),
        "avg_latency_s": round(sum(all_latencies) / n, 2) if all_latencies else 0,
        "min_latency_s": round(min(all_latencies), 2) if all_latencies else 0,
        "max_latency_s": round(max(all_latencies), 2) if all_latencies else 0,
        "total_time_s": round(total_time, 2),
    }

    per_agent = agent_metrics.summary()

    # ── SAVE ─────────────────────────────────────────────────────────────────
    output = {
        "metadata": {
            "model": "llama-3.1-8b-instant",
            "provider": "groq",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_questions": n,
            "skip_invoke": skip_invoke,
        },
        "overall": overall,
        "per_agent": per_agent,
        "per_question": results,
    }
    out_path = EVAL_STORE / "results.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    # ── PRINT REPORT ─────────────────────────────────────────────────────────
    print(f"""
{'='*62}
  CFO Buddy — Evaluation Report
{'='*62}
  Total Queries:    {n}
  Total Time:       {total_time:.2f}s
  Avg Latency:      {overall['avg_latency_s']}s/query
{'─'*62}

  ROUTING & COMPLETION
  ────────────────────
  Routing Accuracy:    {overall['routing_accuracy']*100:.0f}%
  Completion Rate:     {overall['completion_rate']*100:.0f}%

  TOOL SELECTION (Precision / Recall / F1)
  ────────────────────────────────────────
  Precision:           {overall['tool_precision']:.4f}
  Recall:              {overall['tool_recall']:.4f}
  F1 Score:            {overall['tool_f1']:.4f}

  RESPONSE QUALITY (LLM-as-Judge)
  ───────────────────────────────
  Faithfulness:        {overall['avg_faithfulness']}
  Answer Relevancy:    {overall['avg_answer_relevancy']}

  CONTEXT (Tool-Based Proxy)
  ──────────────────────────
  Context Precision:   {overall['avg_context_precision']:.4f}
  Context Recall:      {overall['avg_context_recall']:.4f}
{'='*62}

  PER-AGENT BREAKDOWN
{'='*62}""", flush=True)

    header = f"  {'Agent':<18} {'Acc':>5} {'Comp':>5} {'F1':>6} {'Faith':>6} {'Rel':>6} {'Lat':>7}"
    print(header)
    print(f"  {'─'*55}")
    for agent, s in per_agent.items():
        agent_short = agent.replace("_node", "").replace("web_search", "web")
        print(f"  {agent_short:<18} {s['routing_accuracy']*100:4.0f}% {s['completion_rate']*100:4.0f}% {s['tool_f1']:6.3f} {s['avg_faithfulness']:6.3f} {s['avg_relevancy']:6.3f} {s['avg_latency']:6.1f}s")

    print(f"\n{'='*62}")
    print(f"  Results saved -> {out_path}")
    print(f"{'='*62}\n")

    return output


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CFO Buddy — Multi-Agent Evaluation Framework"
    )
    parser.add_argument(
        "--skip-invoke", action="store_true",
        help="Skip full pipeline invocation. Only test routing accuracy (fast)."
    )
    args = parser.parse_args()

    run_evaluation(skip_invoke=args.skip_invoke)

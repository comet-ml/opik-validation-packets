"""
Real Microsoft Agent Framework sub-agents for the demand-forecasting
orchestrator: forecast_agent, inventory_agent, anomaly_agent.

Each is a real `agent_framework.Agent` backed by a real OpenAI chat
completion (`agent_framework.openai.OpenAIChatClient`). No manual OTel
span-wrapping here: agent_framework's own auto-instrumentation (enabled in
otel_setup.py) emits a full span tree for every `Agent.run()` call with zero
extra code.

anomaly_agent is the one specialist with real RAG: alongside anomaly_lookup
(a structured yes/no + one-line reason), it also has search_incident_reports
— a keyword-overlap retriever (same technique as genai-gateway-persona-poc's
tools.py) over data_store.py's INCIDENT_REPORTS corpus — so it can ground its
explanation in an actual retrieved document rather than just restating the
structured flag. `_retrieved_context` captures the retrieved text so
orchestrator.py can surface it on the trace for Step 02's rag-groundedness
online eval rule to score.

Retry-on-failure is real, not hand-rolled: FLAKY_SKUS makes the underlying
tool raise once per (tool, sku). agent_framework's function-invocation loop
catches that exception itself, feeds an error message back to the model, and
each agent's instructions tell it to retry the tool once on failure — the
MODEL decides to retry (verified live: the tool was called twice within one
`agent.run()`, which returned normally). This shows up in the trace as two
`execute_tool` spans, the first carrying the error.

TODO(SE): swap for real agent endpoints/tool calls once the customer's actual
Microsoft Agent Framework agent registrations are known.
"""
import re

import otel_setup  # noqa: F401  side-effecting: registers the OTel -> Opik bridge

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient

from data_store import DEMAND_RECORDS, INCIDENT_REPORTS

FLAKY_SKUS = {"SKU-004"}
_failure_seen = set()

# Populated by search_incident_reports; read (and cleared per-query) by
# orchestrator.py so the retrieved text can be surfaced on the trace output.
_retrieved_context: dict = {}


def _lookup(sku: str) -> dict:
    for record in DEMAND_RECORDS:
        if record["sku"] == sku:
            return record
    raise ValueError(f"Unknown SKU: {sku!r}")


def _maybe_fail(tool_name: str, sku: str) -> None:
    key = (tool_name, sku)
    if sku in FLAKY_SKUS and key not in _failure_seen:
        _failure_seen.add(key)
        raise RuntimeError(f"{tool_name} timed out calling its upstream service for {sku!r}")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _keyword_overlap_score(query: str, text: str) -> float:
    """Fraction of query tokens also present in `text`. Deterministic, no embeddings."""
    q, t = _tokens(query), _tokens(text)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


@tool
def forecast_lookup(sku: str) -> str:
    """Look up the demand forecast for a SKU."""
    _maybe_fail("forecast_lookup", sku)
    r = _lookup(sku)
    return f"{sku}: forecast_next_period={r['forecast_next_period']}, trend={r['forecast_trend']}"


@tool
def inventory_lookup(sku: str) -> str:
    """Look up current inventory for a SKU."""
    _maybe_fail("inventory_lookup", sku)
    r = _lookup(sku)
    below = r["current_stock"] < r["reorder_point"]
    return (
        f"{sku}: current_stock={r['current_stock']}, reorder_point={r['reorder_point']}, "
        f"below_reorder_point={below}"
    )


@tool
def anomaly_lookup(sku: str) -> str:
    """Look up whether a recent demand anomaly was detected for a SKU, and why."""
    _maybe_fail("anomaly_lookup", sku)
    r = _lookup(sku)
    if not r["anomaly"]["detected"]:
        return f"{sku}: no anomaly detected."
    return f"{sku}: anomaly detected — {r['anomaly']['description']}"


@tool
def search_incident_reports(query: str, top_k: int = 2) -> str:
    """Search historical incident reports for the root-cause detail behind a demand anomaly."""
    scored = sorted(
        INCIDENT_REPORTS,
        key=lambda d: _keyword_overlap_score(query, d["title"] + " " + d["content"]),
        reverse=True,
    )
    top = [d for d in scored[:top_k] if _keyword_overlap_score(query, d["title"] + " " + d["content"]) > 0]
    if not top:
        # Always ground on *something* — mirrors genai-gateway-persona-poc's
        # tools.py non-empty fallback rather than an empty-context path.
        top = scored[:1]
    context_text = "\n".join(f"[{d['id']}] {d['title']}: {d['content']}" for d in top)
    _retrieved_context["anomaly"] = context_text
    return context_text


_RETRY_INSTRUCTION = " If your tool call fails, try it again exactly once before giving up."
_client = OpenAIChatClient(model="gpt-4o-mini")  # TODO(SE): real model

forecast_agent = Agent(
    _client, name="forecast_agent",
    instructions="You are the demand-forecast specialist. Answer using ONLY forecast_lookup." + _RETRY_INSTRUCTION,
    tools=forecast_lookup,
)
inventory_agent = Agent(
    _client, name="inventory_agent",
    instructions="You are the inventory specialist. Answer using ONLY inventory_lookup." + _RETRY_INSTRUCTION,
    tools=inventory_lookup,
)
anomaly_agent = Agent(
    _client, name="anomaly_agent",
    instructions=(
        "You are the demand-anomaly specialist. First call anomaly_lookup to check whether an "
        "anomaly is on record for the SKU. If one is detected, also call search_incident_reports "
        "with a description of the anomaly to retrieve the underlying incident report, and ground "
        "your explanation in it — cite the report id (e.g. [INC-2031])." + _RETRY_INSTRUCTION
    ),
    tools=[anomaly_lookup, search_incident_reports],
)

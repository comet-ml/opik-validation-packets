"""
copilot_session.py — GitHub Copilot Chat Spec-Kit session harness.

Stands in for a real pilot: GitHub Copilot in VS Code, driven by GitHub's own
Spec-Kit (/specify -> /plan -> /tasks -> /implement slash commands operating
over markdown files), specs tracked in Jira (spec_kit_artifacts.TICKETS),
source in GitHub Enterprise. Copilot itself is closed-source — nothing to
instrument directly — but as of mid-2026 GitHub ships enterprise-managed
OpenTelemetry export for Copilot Chat, emitting real, documented spans in
exactly the shape built here by hand (otel_setup.TRACER). Turn CONTENT (the
actual spec/plan/tasks/implementation-summary text) is real — a real OpenAI
call per step.

There is no Opik SDK trace-boundary usage anywhere in this file: a customer
cannot modify Copilot's own closed-source code, so `_run_turn` is a plain
function built only against `otel_setup.TRACER` (raw opentelemetry-sdk
calls). It never attaches a `team`, `developer`, or other custom per-span
tag — Copilot's own instrumentation decides what attributes exist, and none
of those exist in its schema. `opik.Opik()` (the query client) is still used
elsewhere (01_session_tracing.py, 02_oversight_tracking.py, etc.) to read
data back out of Opik — that's unrelated and unaffected.

Two things worth restating here (full write-up in the README):

  1. Thread grouping does not require the Opik SDK at all. Opik's OTLP
     ingestion reads `gen_ai.conversation.id` off a trace's root span (the
     span with no parent) and writes it into that trace's `thread_id`.
  2. Developer identity has no real path into Opik. OTel resource-level
     attributes are ignored entirely by Opik's ingestion pipeline — only
     span-level attributes are ever read — so even resource-attribute
     injection (the one theoretical GitHub-side lever) wouldn't work.

Span tree per turn (one Spec-Kit slash command):

    invoke_agent                   <- ONLY real, documented Copilot attributes:
                                       gen_ai.operation.name=invoke_agent,
                                       gen_ai.agent.name=copilot,
                                       gen_ai.conversation.id=thread_id (drives
                                       Opik thread grouping, see (1) above),
                                       gen_ai.usage.input_tokens/output_tokens
                                       (turn totals), github.copilot.git.*,
                                       github.copilot.github.org.
                                       NEVER: team, developer, ticket_id,
                                       workflow_step, slash_command, tags —
                                       none of these exist in real Copilot's
                                       schema and there is no real mechanism
                                       for a customer to inject them.
      execute_tool (0-2x, before)   <- gen_ai.tool.name, github.copilot.tool.parameters.*
      chat                         <- gen_ai.request.model, gen_ai.usage.input_tokens/output_tokens
      execute_hook (0-1x)           <- github.copilot.hook.decision (allow/block/ask) — /implement only
      execute_tool (0-2x, after)    <- /implement: applyPatch, runTests
      execute_hook (0-1x)           <- Stop hook, end of turn

One Opik THREAD == one Spec-Kit SESSION (`gen_ai.conversation.id`, a ticket
going through /specify -> /plan -> /tasks -> /implement, possibly with human
back-and-forth). One Opik TRACE == one TURN (one slash command) — there is no
explicit "open a trace" call anywhere below: a trace is simply whatever
Opik's OTLP ingestion reconstructs from the root span of each `invoke_agent`
OTel subtree. Every span is built by hand directly against the raw
opentelemetry-sdk tracer API (`otel_setup.TRACER.start_as_current_span(...)`)
— there is no auto-instrumenting framework in the loop here.

GOTCHA 1 — Opik's OTLP ingest endpoint only implements the traces endpoint,
not metrics or logs, so token counts, edit acceptance, and thumbs feedback
are all represented as span attributes (`gen_ai.usage.*`,
`github.copilot.edit.accepted`, `github.copilot.feedback.vote`) instead of
OTel metric instruments. See the README's ingestion-gotcha section.

GOTCHA 2 — content is gated behind `capture_content`, modeling the real
`captureContent` setting (off by default, since prompt/response/tool-argument
text can contain proprietary code or secrets). When False (Steps 01/02),
spans carry only structural attributes. When True (Steps 03/04), spans
additionally carry `gen_ai.prompt`/`gen_ai.completion` (chat) and
`gen_ai.tool.call.arguments`/`gen_ai.tool.call.result` (execute_tool).

GOTCHA 3 — `invoke_agent`'s own usage attributes are set (matching the real
documented schema) but never persist server-side: Opik's backend nulls a
span's usage whenever it's the direct parent of a usage-bearing child, and
`invoke_agent` is always the parent of `chat` here. Don't rely on
`invoke_agent`'s usage for a turn-level rollup — sum the turn's `chat`
span(s) instead, which is exactly what `run_copilot_session`'s returned
`input_tokens`/`output_tokens` already do (computed from the real OpenAI
response, independent of this backend behavior).

Once the customer's specifics are known: swap OpenAI for their real model
routing, swap the synthetic tool stand-ins (readFile/grep/applyPatch/
runTests) for their actual Copilot tool inventory, and swap
`github.copilot.github.org` for the real GHE org slug.
"""
import json
import random
import time
import uuid
from typing import Dict, List, Optional

from openai import OpenAI

import otel_setup  # noqa: F401  side-effecting: builds + registers the OTel exporter
from otel_setup import TRACER, OPIK_PROJECT_NAME  # noqa: F401  OPIK_PROJECT_NAME re-exported for step scripts
from spec_kit_artifacts import get_ticket

_client = OpenAI()
MODEL = "gpt-4o-mini"  # swap for the real model routing once known

STEP_ORDER = ["specify", "plan", "tasks", "implement"]
SLASH_COMMAND = {"specify": "/specify", "plan": "/plan", "tasks": "/tasks", "implement": "/implement"}

STEP_PROMPTS = {  # swap for the real Spec-Kit prompt templates once known
    "specify": (
        "You are GitHub Copilot running the Spec-Kit /specify command for this ticket:\n"
        "Ticket {ticket_id}: {title}\n{description}\n\n"
        "Write a short feature specification (spec.md) covering the problem statement, goals, "
        "and 2-3 acceptance criteria. Keep it under 150 words."
    ),
    "plan": (
        "You are GitHub Copilot running the Spec-Kit /plan command. Here is the approved "
        "specification (spec.md):\n{spec}\n\n"
        "Write a short technical implementation plan (plan.md) — which components/files change "
        "and the overall approach. Keep it under 150 words."
    ),
    "tasks": (
        "You are GitHub Copilot running the Spec-Kit /tasks command. Here is the implementation "
        "plan (plan.md):\n{plan}\n\n"
        "Break it into a numbered task list (tasks.md), 4-6 tasks. Keep it under 120 words."
    ),
    "implement": (
        "You are GitHub Copilot running the Spec-Kit /implement command. Here is the task list "
        "(tasks.md):\n{tasks}\n\n"
        "Write a brief implementation summary (as if summarizing a code diff) describing what "
        "changed across 1-3 files. Keep it under 120 words."
    ),
}

# Structural, always-present tool-call stand-ins per step — light, not real
# pytest/filesystem calls (no fixture repo in this packet; see README for why
# this stays lighter than forge_sdlc_agents-style real tool execution).
TOOL_CALLS_BEFORE_CHAT = {
    "specify": [("readFile", {"path": "README.md"}), ("grep", {"pattern": "TODO"})],
    "plan": [("readFile", {"path": "spec.md"})],
    "tasks": [("readFile", {"path": "plan.md"})],
    "implement": [],
}
TOOL_CALLS_AFTER_CHAT = {
    "specify": [],
    "plan": [],
    "tasks": [],
    "implement": [("applyPatch", {"file": "src/main.py"}), ("runTests", {"suite": "unit"})],
}
_SYNTHETIC_TOOL_RESULTS = {
    "readFile": "<file contents omitted — synthetic stand-in>",
    "grep": "3 matches",
    "applyPatch": "patch applied cleanly",
    "runTests": "12 passed, 0 failed",
}


def _run_tool_call(tool_name: str, params: dict, capture_content: bool, rng: random.Random) -> None:
    with TRACER.start_as_current_span("execute_tool") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", tool_name)
        for key, value in params.items():
            span.set_attribute(f"github.copilot.tool.parameters.{key}", str(value))

        result = _SYNTHETIC_TOOL_RESULTS.get(tool_name, "ok")
        if capture_content:
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(params))
            span.set_attribute("gen_ai.tool.call.result", result)

        if tool_name == "applyPatch":
            # Real accept/reject signal represented as a span attribute, not
            # an OTel metric counter — see GOTCHA 1 above.
            span.set_attribute("github.copilot.edit.accepted", rng.random() < 0.8)

        time.sleep(0.01)  # negligible synthetic tool latency


def _run_hook(hook_name: str, decision: str) -> None:
    with TRACER.start_as_current_span("execute_hook") as span:
        span.set_attribute("github.copilot.hook.name", hook_name)
        span.set_attribute("github.copilot.hook.decision", decision)


def _run_chat(prompt: str, capture_content: bool, rng: random.Random) -> tuple:
    with TRACER.start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", MODEL)
        if capture_content:
            span.set_attribute("gen_ai.prompt", prompt)

        response = _client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        text = (response.choices[0].message.content or "").strip()

        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)

        if capture_content:
            span.set_attribute("gen_ai.completion", text)

        # Real thumbs-up/down feedback represented as a span attribute, not
        # an OTel metric counter — see GOTCHA 1 above.
        if rng.random() < 0.4:
            span.set_attribute("github.copilot.feedback.vote", rng.choice(["up", "down"]))

        return text, input_tokens, output_tokens


def _run_turn(
    step: str,
    thread_id: str,
    ticket: dict,
    repository: str,
    history: Dict[str, str],
    capture_content: bool,
    rng: random.Random,
) -> dict:
    """
    Emit one turn's OTel span tree directly via `otel_setup.TRACER` — NO Opik
    SDK call of any kind, by design (see module docstring). This function only
    ever sets attributes that are part of GitHub Copilot Chat's own real,
    documented OTel schema. It deliberately does NOT take a `developer` or
    `team` or `ticket_id`-as-an-attribute parameter: real Copilot's own
    instrumentation code has no way to know or emit any of that either, so
    this function — which stands in for that instrumentation — must not be
    able to either. (`ticket` is used only to generate this turn's prompt
    CONTENT and a synthetic branch/commit value; it is never itself set as a
    span attribute.)
    """
    prompt = STEP_PROMPTS[step].format(
        ticket_id=ticket["ticket_id"],
        title=ticket["title"],
        description=ticket["description"],
        spec=history.get("specify", ""),
        plan=history.get("plan", ""),
        tasks=history.get("tasks", ""),
    )

    commit_sha = uuid.uuid5(uuid.NAMESPACE_DNS, f"{ticket['ticket_id']}:{step}").hex[:12]
    total_input = 0
    total_output = 0
    text = ""

    with TRACER.start_as_current_span("invoke_agent") as agent_span:
        # ONLY real, documented GitHub Copilot Chat OTel schema attributes
        # below — nothing else. Deliberately absent: team, developer,
        # ticket_id, workflow_step, slash_command, tags. None of those exist
        # in real Copilot's schema, and there is no real mechanism for a
        # customer to inject them (see module docstring + README).
        agent_span.set_attribute("gen_ai.operation.name", "invoke_agent")
        agent_span.set_attribute("gen_ai.agent.name", "copilot")
        # This single attribute is what drives Opik thread grouping, via an
        # unconditional OTLP-ingestion mapping rule — no Opik SDK involved.
        agent_span.set_attribute("gen_ai.conversation.id", thread_id)
        agent_span.set_attribute("github.copilot.git.repository", repository)
        agent_span.set_attribute("github.copilot.git.branch", f"feature/{ticket['ticket_id'].lower()}")
        agent_span.set_attribute("github.copilot.git.commit_sha", commit_sha)
        agent_span.set_attribute("github.copilot.github.org", "example-org")  # swap for the real GHE org slug

        for tool_name, params in TOOL_CALLS_BEFORE_CHAT[step]:
            _run_tool_call(tool_name, params, capture_content, rng)

        text, input_tokens, output_tokens = _run_chat(prompt, capture_content, rng)
        total_input += input_tokens
        total_output += output_tokens

        if step == "implement":
            _run_hook("PreToolUse", "allow")

        for tool_name, params in TOOL_CALLS_AFTER_CHAT[step]:
            _run_tool_call(tool_name, params, capture_content, rng)

        if rng.random() < 0.3:
            _run_hook("Stop", rng.choice(["allow", "ask"]))

        # GOTCHA 3 — still set (matches the real documented schema and the
        # OTLP payload genuinely carries it), but won't persist server-side
        # due to the parent/child usage dedup. See module docstring.
        agent_span.set_attribute("gen_ai.usage.input_tokens", total_input)
        agent_span.set_attribute("gen_ai.usage.output_tokens", total_output)

    history[step] = text
    return {
        "step": step,
        "text": text,
        "input_tokens": total_input,
        "output_tokens": total_output,
    }


async def run_copilot_session(
    ticket_id: str,
    developer: str,
    team: str,
    repository: str,
    steps: Optional[List[str]] = None,
    capture_content: bool = False,
) -> dict:
    """
    Run one Spec-Kit session (one Opik thread, `gen_ai.conversation.id`) end
    to end through `steps` (default: the full
    /specify -> /plan -> /tasks -> /implement sequence).

    Each step is one Opik trace within the thread — reconstructed purely
    server-side from the raw OTLP payload of a hand-built
    invoke_agent/chat/execute_tool/execute_hook OTel span tree (see module
    docstring). There is no Opik SDK call anywhere in this function or in
    `_run_turn`.

    `developer` / `team` / `ticket_id` here are harness bookkeeping only —
    passed straight into this function's return value and never forwarded to
    `_run_turn`, so they never become an Opik trace/span attribute, tag, or
    metadata key. See the README for the full "what's real vs modeled"
    accounting.
    """
    ticket = get_ticket(ticket_id)
    steps = steps or list(STEP_ORDER)
    thread_id = f"sess-{ticket_id.lower()}-{uuid.uuid4().hex[:8]}"
    rng = random.Random(thread_id)

    history: Dict[str, str] = {}
    total_input = 0
    total_output = 0

    for step in steps:
        result = _run_turn(step, thread_id, ticket, repository, history, capture_content, rng)
        total_input += result["input_tokens"]
        total_output += result["output_tokens"]

    return {
        "thread_id": thread_id,
        # --- everything below is harness bookkeeping, not knowable from
        # real Copilot telemetry (see docstring above) ---
        "ticket_id": ticket_id,
        "developer": developer,
        "team": team,
        "repository": repository,
        "steps_run": steps,
        "input_tokens": total_input,
        "output_tokens": total_output,
    }


def flush() -> None:
    """Flush any buffered OTel spans — call at the end of any standalone script.

    No Opik SDK message queue to flush anymore: nothing in this harness ever
    goes through the Opik SDK (see module docstring) — this is pure OTLP.
    """
    otel_setup.flush_otel()

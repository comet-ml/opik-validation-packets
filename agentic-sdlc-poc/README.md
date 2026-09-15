# Agentic SDLC PoC — Opik Validation Scripts

Validation scripts for an AI-assisted software delivery lifecycle: GitHub Copilot Chat in VS Code,
driven by GitHub's own Spec-Kit (`/specify -> /plan -> /tasks -> /implement` slash commands over
markdown files), with specs tracked in Jira and source in GitHub Enterprise.

Four steps are built: session tracing, human oversight tracking, governance/risk monitoring, and
cost visibility. An optimization-signal step and a dashboard step are out of scope for this build.

## What's real vs. modeled

GitHub Copilot itself is closed-source, so there's nothing to instrument directly. As of mid-2026,
GitHub ships **enterprise-managed OpenTelemetry export** for Copilot Chat — real, documented spans.
This packet's harness (`copilot_session.py`) builds spans in that exact schema by hand, directly
against the raw `opentelemetry-sdk` API, and ships them to Opik's OTLP endpoint. **Nothing in this
packet goes through the Opik SDK — it's 100% raw OTLP**, the same as a real Copilot deployment,
since Copilot's own managed exporter never touches the Opik SDK either.

- **Real:** every turn's actual content (the spec/plan/tasks/implementation-summary text) comes from
  a real OpenAI call, and token usage on every span is the real usage from that call.
- **Modeled:** the surrounding Spec-Kit session/ticket data (`spec_kit_artifacts.py`), the git/org/
  tool-parameter attributes (`copilot_session.py`), and lightweight tool-call stand-ins
  (`readFile`/`grep`/`applyPatch`/`runTests` — no real filesystem/test execution behind them).

A customer cannot modify GitHub Copilot's own closed-source code — the only levers a real org admin
has are the OTLP endpoint/protocol, exporter headers, the `captureContent` on/off toggle, and OTel
resource attributes. So this harness never opens its own Opik SDK trace or attaches custom tags/
metadata; it only emits attributes that are part of Copilot's real, documented schema.

## The OTel schema

Span tree per Copilot Chat turn (one Spec-Kit slash command):

| Span | Parent | Key attributes |
|---|---|---|
| `invoke_agent` | (root of the turn) | `gen_ai.agent.name`, `gen_ai.conversation.id`, `gen_ai.usage.input_tokens`/`output_tokens`, `github.copilot.git.repository`/`.branch`/`.commit_sha`, `github.copilot.github.org` |
| `chat` | `invoke_agent` | `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens` |
| `execute_tool` | `invoke_agent` | `gen_ai.tool.name`, `github.copilot.tool.parameters.*` |
| `execute_hook` | `invoke_agent` | `github.copilot.hook.name`, `github.copilot.hook.decision` (`allow`/`block`/`ask`) |

One Opik **thread** = one Spec-Kit session (`gen_ai.conversation.id` == `thread_id`) — a ticket going
through `/specify -> /plan -> /tasks -> /implement`, possibly with human back-and-forth. One Opik
**trace** = one turn (one slash command). Opik reconstructs both purely server-side from the raw OTLP
payload: whichever span in a batch has no parent becomes the trace root, and the root span's
`gen_ai.conversation.id` becomes the trace's `thread_id` — no Opik SDK call involved at any point.

**Content capture is gated.** Real Copilot OTel export only captures prompt/response/tool-argument
text when the enterprise `captureContent` setting is explicitly turned on — off by default, since
that text can contain proprietary code or secrets. Steps 01–02 run with `capture_content=False`
(spans carry only structural attributes: which tool ran, token counts, hook decisions). Step 03 turns
it on for the first time to demonstrate a sensitive-data scan — see that step's own docs for why this
is framed as a discussion point, not a recommendation.

## Project layout

| File | Role |
|---|---|
| `otel_setup.py` | Builds a plain `TracerProvider` and points a hand-built `OTLPSpanExporter` at Opik's OTLP endpoint; exposes the shared `TRACER`. No Opik SDK object anywhere in this file. |
| `copilot_session.py` | The harness. `run_copilot_session(...)` runs one Spec-Kit session (one thread) through its steps; each step builds an `invoke_agent`/`chat`/`execute_tool`/`execute_hook` span tree via `otel_setup.TRACER`, with a real OpenAI call generating that step's content. |
| `repo_team_map.py` | `REPOSITORY_TO_TEAM` — a plain dict standing in for a mapping a real customer already has (CODEOWNERS, org chart), joined against the real `github.copilot.git.repository` attribute. |
| `spec_kit_artifacts.py` | Synthetic Jira-tickets-linked-to-Spec-Kit-features corpus (`TICKETS`), plus a generic `DEVELOPERS` list. |
| `risk_patterns.py` | One worked risk-category detector: a regex-based sensitive-data-in-prompt scanner (API keys, emails, credit-card-like digit runs). Used by Step 03. |
| `01_session_tracing/` | Step 01 — adoption/usage tracking. |
| `02_oversight_tracking/` | Step 02 — human oversight tracking + an online-evaluation rule. |
| `03_risk_governance/` | Step 03 — sensitive-data detection + an online-evaluation rule. |
| `04_cost_roi/` | Step 04 — cost and ROI visibility. |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in COMET_API_KEY / OPIK_WORKSPACE / OPENAI_API_KEY in .env
```

`.env` holds secrets only. The shared credentials file stores the key under `COMET_API_KEY`, and
every entrypoint aliases it to `OPIK_API_KEY` (the only name the SDK reads) at import time in
`otel_setup.py`. Every other project-specific value (project name, model, prompts, tool stand-ins) is
a plain constant directly in whichever file uses it — there's no shared `config.py`.

## Running

Run each step in order:

```bash
python 01_session_tracing/01_session_tracing.py
python 02_oversight_tracking/02_oversight_tracking.py
python 03_risk_governance/03_risk_governance.py
python 04_cost_roi/04_cost_roi.py
```

| Step | What it validates |
|------|--------------------|
| **01 — Session Tracing** | Runs ~12 synthetic Spec-Kit sessions (mixed developers/teams/repositories/workflows) purely over raw OTLP, then confirms thread/trace grouping works and queries back a repository breakdown (real) and a team breakdown (repository joined against `repo_team_map.py`) for adoption tracking. |
| **02 — Human Oversight Tracking** | Re-runs the same sessions, then queries every turn's spans to identify accept/reject, thumbs feedback, hook-confirmation, and rerun signals per session. Also deploys a live `edit-accepted` online-evaluation rule that scores every future turn's trace on whether its edits were accepted. |
| **03 — Governance & Risk Monitoring** | Turns `capture_content=True` on for the first time in this packet, runs one deliberately-injected risk scenario plus 3 normal sessions as a false-positive check, and scans the real captured content for sensitive data. Also deploys a live `sensitive-data-in-prompt` online-evaluation rule on `chat` spans. |
| **04 — Cost & ROI Visibility** | Queries real token usage off each turn's `chat` span (the span type where usage reliably persists) and rolls it up by repository and team, converting to an approximate dollar figure using `gpt-4o-mini`'s published per-token rate. Proposes the shape of an ROI metric without fabricating the missing return-signal half. |

Each step folder also has a `.md` checklist for verifying results in the Opik UI.

## Before running with a real customer

- Swap the synthetic tool stand-ins (`readFile`/`grep`/`applyPatch`/`runTests`) in `copilot_session.py`
  for the customer's actual Copilot tool inventory once known.
- Swap the OpenAI model routing in `copilot_session.py` for the customer's real model routing.
- Swap `github.copilot.github.org` in `copilot_session.py` for the real GHE org slug.
- Swap `spec_kit_artifacts.py`'s synthetic tickets for a redacted/generalized sample of the customer's
  real Jira backlog, same shape.
- Once the customer's real GitHub Enterprise-managed OTel export endpoint/headers are known, only the
  exporter target in `otel_setup.py` changes.
- Step 03's risk detector covers exactly one category (sensitive data in prompts). The full risk
  taxonomy a customer's governance/security team cares about needs a dedicated working session with
  that team to define — this packet does not attempt to guess the rest of it.
- A full ROI metric needs Step 04's cost data joined against delivery-outcome data (PR merge time,
  revert rate, Jira cycle time) once that data source is in scope.

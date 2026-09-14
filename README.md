# Opik Validation Packets

Independent validation packets built and run against a real, live Opik instance rather than a
sandbox. Each packet is self-contained — its own `README.md`, `.env.example`, and numbered step
scripts — and can be run on its own against any Opik instance (cloud or self-hosted).

## 1. Environment setup

Every packet reads its own connection details from a local `.env` (gitignored, never committed;
copy `.env.example` to `.env` and fill in your values before running anything). None of the
packets hardcode a specific Opik instance, workspace, or project — point `.env` at whichever
Opik deployment you're validating against.

To get an API key: log into your Opik instance, click your profile icon in the top-right corner,
and select **API Key**.

### Navigating to Model Production Monitoring (MPM)

MPM lives under **Experiment Management**, not as its own top-level app. From anywhere in the
product: click the grid icon in the top navigation bar (next to the account avatar) ->
**Experiment management**. MPM views and dashboards are accessible from within that app.

## 2. General resources

- [Opik documentation](https://www.comet.com/docs/opik/v1/)
- [Model Production Monitoring documentation](https://www.comet.com/docs/v2/guides/model-production-monitoring/quickstart/)

## 3. Repo structure

```
.
├── genai-gateway-persona-poc/       Persona-driven gateway chatbot: dataset/metrics/
│                                    experiments/regression/dashboard
├── multi-agent-orchestration-poc/   Real Microsoft Agent Framework multi-agent demand
│                                    forecasting flow: tracing, online eval, failure/retry
│                                    detection, dashboard
└── mpm-monitoring-poc/              Model production monitoring validation packet
```

Each directory has its own `README.md` with full setup and step-by-step usage — start there for
anything packet-specific. This file only covers what's common across all three.

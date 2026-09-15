"""
Synthetic Jira-tickets-linked-to-Spec-Kit-features corpus.

Stands in for the real customer's Jira project — fully fictional tickets,
titles, descriptions, repositories, and teams. Each ticket is what a real
developer would feed into GitHub Copilot's Spec-Kit `/specify` command to
kick off a session (copilot_session.run_copilot_session's `ticket_id`).

Replace with a real (redacted/generalized) sample of the customer's actual
Jira backlog once known — same fields, same shape.
"""

TICKETS = [
    {
        "ticket_id": "PROJ-101",
        "title": "Add pagination to the order history API",
        "description": (
            "The /orders endpoint returns the full order history in one response. Large "
            "accounts time out. Add cursor-based pagination with a configurable page size."
        ),
        "repository": "retail-order-service",
        "team": "commerce-platform",
    },
    {
        "ticket_id": "PROJ-114",
        "title": "Cache product catalog lookups",
        "description": (
            "Catalog lookups hit the database on every request. Add an in-memory cache with a "
            "5 minute TTL in front of the catalog lookup service to cut p95 latency."
        ),
        "repository": "retail-order-service",
        "team": "commerce-platform",
    },
    {
        "ticket_id": "PROJ-128",
        "title": "Retry transient failures in the shipping-label client",
        "description": (
            "The shipping-label integration occasionally times out on the carrier's side. Add "
            "an exponential backoff retry (max 3 attempts) around that client call."
        ),
        "repository": "retail-order-service",
        "team": "commerce-platform",
    },
    {
        "ticket_id": "INV-205",
        "title": "Expose a warehouse reorder-point override endpoint",
        "description": (
            "Ops needs to manually override a SKU's reorder point ahead of a promotion. Add an "
            "authenticated PATCH endpoint that updates the reorder point and logs who changed it."
        ),
        "repository": "inventory-service",
        "team": "supply-chain-eng",
    },
    {
        "ticket_id": "INV-219",
        "title": "Emit a low-stock event when inventory crosses the reorder point",
        "description": (
            "Currently low-stock detection is a nightly batch job. Emit a real-time event to the "
            "existing message bus the moment a SKU's on-hand quantity crosses its reorder point."
        ),
        "repository": "inventory-service",
        "team": "supply-chain-eng",
    },
    {
        "ticket_id": "INV-233",
        "title": "Add a dry-run mode to the inventory reconciliation job",
        "description": (
            "The nightly reconciliation job writes corrections directly. Add a --dry-run flag "
            "that logs the corrections it WOULD make without writing them, for safer rollout."
        ),
        "repository": "inventory-service",
        "team": "supply-chain-eng",
    },
    {
        "ticket_id": "PORT-042",
        "title": "Add CSV export to the internal reporting portal",
        "description": (
            "Analysts currently screenshot the reporting dashboard. Add a CSV export button that "
            "downloads the currently filtered table view."
        ),
        "repository": "internal-reporting-portal",
        "team": "data-platform",
    },
    {
        "ticket_id": "PORT-057",
        "title": "Add role-based access control to the reporting portal",
        "description": (
            "All logged-in users currently see every report. Restrict report visibility by team "
            "using the existing identity-provider group claims."
        ),
        "repository": "internal-reporting-portal",
        "team": "data-platform",
    },
    {
        "ticket_id": "PORT-063",
        "title": "Add a saved-filters feature to the reporting portal",
        "description": (
            "Analysts re-enter the same filter combinations every day. Let a user save a named "
            "filter set and reapply it from a dropdown."
        ),
        "repository": "internal-reporting-portal",
        "team": "data-platform",
    },
    {
        "ticket_id": "AUTH-088",
        "title": "Add device fingerprinting to the login-anomaly detector",
        "description": (
            "The login-anomaly detector currently only looks at IP geolocation. Add a device "
            "fingerprint signal (user agent + screen params) to reduce false positives."
        ),
        "repository": "identity-service",
        "team": "platform-security",
    },
    {
        "ticket_id": "AUTH-101",
        "title": "Shorten session token TTL for admin-role users",
        "description": (
            "Admin-role sessions currently share the same 24h TTL as regular users. Reduce it to "
            "2h for admin-role tokens specifically, with a silent refresh if still active."
        ),
        "repository": "identity-service",
        "team": "platform-security",
    },
    {
        "ticket_id": "AUTH-115",
        "title": "Add a break-glass audit log for emergency access grants",
        "description": (
            "Emergency access grants bypass normal approval but aren't logged distinctly today. "
            "Write a dedicated, tamper-evident audit entry any time break-glass access is used."
        ),
        "repository": "identity-service",
        "team": "platform-security",
    },
    {
        # Deliberately injected risk scenario for 03_risk_governance.py — not
        # a template for a real ticket. The fabricated secret in `description`
        # below lands verbatim in this turn's captured prompt when
        # capture_content=True, so it reliably trips risk_patterns.py's
        # sensitive-data scan.
        "ticket_id": "SEC-201",
        "title": "Remove hardcoded staging API key from config.py",
        "description": (
            "While debugging the staging deploy we noticed our staging API key is hardcoded "
            "directly in the client: api_key=sk-abc123DEFghijKLMnop456QRS789 in config.py, "
            "instead of being pulled from the secrets manager. Remove the hardcoded value and "
            "load it from the existing secrets-manager client at startup instead."
        ),
        "repository": "identity-service",
        "team": "platform-security",
    },
]

DEVELOPERS = [
    "morgan.lee",
    "casey.nguyen",
    "riley.patel",
    "jordan.smith",
    "sam.osei",
    "taylor.diaz",
]

_TICKETS_BY_ID = {t["ticket_id"]: t for t in TICKETS}


def get_ticket(ticket_id: str) -> dict:
    return _TICKETS_BY_ID[ticket_id]

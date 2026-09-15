"""
repo_team_map.py — repository -> team lookup, joined in analysis, NOT
queryable from Opik or from Copilot's own telemetry.

Real GitHub Copilot Chat OTel export carries `github.copilot.git.repository`
(a real, documented attribute — see copilot_session.py). It does NOT, and
cannot, carry a `team` attribute: "team" isn't a git/GitHub concept Copilot's
own instrumentation code knows about, so there's no schema field for it and
no mechanism for a customer to inject one (see the README's headline finding
on this rearchitecture).

What a REAL customer already has, however, is their own mapping from
repository to owning team — via CODEOWNERS files, their internal service
catalog, or their org chart. `REPOSITORY_TO_TEAM` below stands in for that
mapping: it is plain Python data the harness supplies, NOT something Opik or
Copilot's telemetry can tell you on its own. Step 01 (01_session_tracing.py)
queries `github.copilot.git.repository` back from Opik (it lands in
`trace.input` — see that script's docstring) and joins it against this dict
to reconstruct a team breakdown. This is an explicit external join performed
in analysis, not a field read directly off any Opik trace/span.

The repository/team pairs below match spec_kit_artifacts.TICKETS exactly, so
a real customer's CODEOWNERS-derived mapping would have the identical shape,
just with production repository/team names.
"""

REPOSITORY_TO_TEAM = {
    "retail-order-service": "commerce-platform",
    "inventory-service": "supply-chain-eng",
    "internal-reporting-portal": "data-platform",
    "identity-service": "platform-security",
}


def get_team(repository: str) -> str:
    """Look up the owning team for a repository. Returns "unknown" if unmapped."""
    return REPOSITORY_TO_TEAM.get(repository, "unknown")

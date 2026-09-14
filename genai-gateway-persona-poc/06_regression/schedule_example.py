"""
Step 06c — Scheduling Sketch (not run as part of the demo path)

Two ways to run run_regression.py on a cadence. Both are illustrated here for
reference; neither is invoked automatically by this repo.

TODO(SE): pick whichever matches the real customer's existing infra (a
long-running service vs. their CI/CD system) and wire up real alerting
(Slack/PagerDuty/email) in place of the `print()` calls below.
"""

# ---------------------------------------------------------------------------
# Option 1 — local polling loop (e.g. run as a systemd service / background
# process on a schedule-agnostic host)
# ---------------------------------------------------------------------------

LOCAL_POLLING_LOOP_EXAMPLE = '''
import subprocess
import time

POLL_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours

while True:
    result = subprocess.run(
        ["python", "run_regression.py", "--gate"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("REGRESSION GATE FAILED:")
        print(result.stdout)
        # TODO(SE): replace with a real alert (Slack webhook, PagerDuty, email).
    time.sleep(POLL_INTERVAL_SECONDS)
'''

# ---------------------------------------------------------------------------
# Option 2 — GitHub Actions cron workflow
# ---------------------------------------------------------------------------

GITHUB_ACTIONS_EXAMPLE = """
# .github/workflows/genai-gateway-regression.yml
name: GenAI Gateway Regression Gate

on:
  schedule:
    - cron: "0 */6 * * *"   # every 6 hours
  workflow_dispatch: {}      # allow manual trigger too

jobs:
  regression-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python 06_regression/run_regression.py --gate
        env:
          OPIK_API_KEY: ${{ secrets.OPIK_API_KEY }}
          OPIK_WORKSPACE: ${{ secrets.OPIK_WORKSPACE }}
          OPIK_PROJECT_NAME: genai-gateway-persona-poc
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      # A non-zero exit from run_regression.py --gate fails this step, which
      # fails the workflow run — wire up GitHub's built-in workflow-failure
      # notifications, or add a dedicated Slack-notify step here.
"""

if __name__ == "__main__":
    print("This is a reference sketch, not an executable demo step.\n")
    print("=" * 70)
    print("Option 1 — local polling loop:")
    print(LOCAL_POLLING_LOOP_EXAMPLE)
    print("=" * 70)
    print("Option 2 — GitHub Actions cron workflow:")
    print(GITHUB_ACTIONS_EXAMPLE)

"""
Demo Trigger Script
Fires a pre-built CI/CD failure scenario at the Webhook Receiver,
then polls the Integrations service until the AI decision arrives.

Usage:
    python trigger_failure.py        # scenario 1 (default)
    python trigger_failure.py 1      # Missing Environment Variable
    python trigger_failure.py 2      # Dependency Conflict
    python trigger_failure.py 3      # Flaky Test
"""

import sys
import time
import json

import requests

# ── Pre-built failure scenarios ───────────────────────────────────────────────

SCENARIO_1 = {
    "name":       "Missing Environment Variable",
    "workflow":   "Production Deploy",
    "job":        "deploy-to-gcp",
    "repository": "acme-corp/platform",
    "run_id":     "9876543210",
    "error_log":  """
      Error: DATABASE_URL environment variable is not set
      at validateConfig (/app/config.js:23:11)
      at Server.start (/app/server.js:45:3)
      TypeError: Cannot read property 'split' of undefined
      Process exited with code 1
      Build failed after 2m 34s
      Deployment to production: FAILED
    """,
}

SCENARIO_2 = {
    "name":       "Dependency Conflict",
    "workflow":   "Backend CI",
    "job":        "test-and-build",
    "repository": "acme-corp/api-service",
    "run_id":     "1234567890",
    "error_log":  """
      ERROR: Cannot install -r requirements.txt (line 12)
      Conflict: package 'requests' requires 'urllib3<2.0'
      but 'google-cloud-storage' requires 'urllib3>=2.0'
      Could not find a version that satisfies the requirement
      pip install failed with exit code 1
    """,
}

SCENARIO_3 = {
    "name":       "Flaky Test",
    "workflow":   "Integration Tests",
    "job":        "run-integration-tests",
    "repository": "acme-corp/platform",
    "run_id":     "5555555555",
    "error_log":  """
      FAILED tests/integration/test_payment.py::test_stripe_webhook -
      AssertionError: Expected status 200, got 503
      Connection timeout after 30s to external service
      Test has passed 47/50 times in last 7 days
      Retry attempt 3/3 failed
      Integration test suite: 1 failed, 156 passed
    """,
}

SCENARIOS = {1: SCENARIO_1, 2: SCENARIO_2, 3: SCENARIO_3}

WEBHOOK_URL = "http://localhost:5000/webhook"
STATE_URL   = "http://localhost:5002/state"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_current_state() -> dict:
    """Fetch the latest state from the Integrations service."""
    try:
        resp = requests.get(STATE_URL, timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def print_decision(state: dict) -> None:
    """Pretty-print the AI decision."""
    print("\n" + "=" * 60)
    print("  AI DECISION RECEIVED")
    print("=" * 60)
    print(f"  Incident  : {state.get('incident_id', 'N/A')}")
    print(f"  Pipeline  : {state.get('pipeline', 'N/A')}")
    print(f"  Category  : {state.get('category', 'N/A')}")
    print(f"  Severity  : {state.get('severity', 'N/A')}")
    print(f"  Confidence: {int(state.get('confidence', 0) * 100)}%")
    print(f"  Action    : {state.get('action', 'N/A')}")
    print(f"  Root cause: {state.get('root_cause', 'N/A')}")

    if state.get("action") == "AUTO_FIX":
        print(f"  Fix cmd   : {state.get('fix_command', 'N/A')}")
    else:
        steps = state.get("investigation_steps") or []
        for i, step in enumerate(steps, 1):
            print(f"  Step {i}    : {step}")

    print(f"  Fix time  : {state.get('estimated_fix_time', 'N/A')}")
    if state.get("used_cache"):
        print("  NOTE      : Used emergency backup (Claude API unavailable)")
    print("=" * 60)
    print("\n  Open http://localhost:5000/ to see the live dashboard.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    """Select a scenario, fire it, and wait for the AI decision."""
    # Parse scenario number
    scenario_num = 1
    if len(sys.argv) > 1:
        try:
            scenario_num = int(sys.argv[1])
        except ValueError:
            print(f"ERROR: argument must be 1, 2, or 3 — got '{sys.argv[1]}'")
            sys.exit(1)

    if scenario_num not in SCENARIOS:
        print(f"ERROR: scenario {scenario_num} not found. Choose 1, 2, or 3.")
        sys.exit(1)

    scenario = SCENARIOS[scenario_num]

    print("\n" + "=" * 60)
    print(f"  TRIGGERING SCENARIO {scenario_num}: {scenario['name']}")
    print("=" * 60)
    print(f"  Workflow  : {scenario['workflow']}")
    print(f"  Job       : {scenario['job']}")
    print(f"  Repo      : {scenario['repository']}")
    print(f"  Run ID    : {scenario['run_id']}")
    print(f"  Target    : {WEBHOOK_URL}")
    print("=" * 60)

    # Snapshot current state so we can detect the new one
    initial_state   = get_current_state()
    initial_iid     = initial_state.get("incident_id")

    # Build the webhook payload (drop the display-only 'name' key)
    payload = {k: v for k, v in scenario.items() if k != "name"}

    # Fire the webhook
    try:
        print(f"\n  Sending POST to {WEBHOOK_URL}...")
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        print(f"  ✓ Webhook accepted — Incident ID: {data.get('incident_id', 'N/A')}")
        print(f"  Waiting for AI analysis (up to 30 seconds)...")
    except requests.ConnectionError:
        print(f"\n  ERROR: Cannot reach {WEBHOOK_URL}")
        print("  Make sure all services are running first:")
        print("    python start_all.py")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        sys.exit(1)

    # Poll for the AI decision
    time.sleep(1)
    for attempt in range(30):
        state = get_current_state()
        if state and state.get("incident_id") and state.get("incident_id") != initial_iid:
            print_decision(state)
            return
        print(f"  Polling... ({attempt + 1}/30)", end="\r")
        time.sleep(1)

    print("\n  TIMEOUT: AI decision did not arrive within 30 seconds.")
    print("  Check the service logs for errors.")
    sys.exit(1)


if __name__ == "__main__":
    main()

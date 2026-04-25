"""
SERVICE 2 — AI Agent (port 5001)
OODA pillars: ANALYZE + DECIDE

Receives incidents from the Webhook Receiver, classifies them with Claude,
decides on AUTO_FIX vs CREATE_ISSUE, and forwards the result to Integrations.
Falls back to emergency_backup.py if the Claude API is unavailable.
"""

import sys
import os
import re
import json
import socket
import threading

import requests
import anthropic
from flask import Flask, request, jsonify
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

from emergency_backup import get_cached_response  # noqa: E402

app = Flask(__name__)

# ── System prompt (verbatim from spec) ───────────────────────────────────────

SYSTEM_PROMPT = """
You are an expert DevOps AI agent analyzing CI/CD pipeline failures.

When given an error log, you must:
1. Classify the failure into exactly ONE category:
   - MISSING_ENV_VAR: Environment variable not set or missing
   - DEPENDENCY_CONFLICT: Package version mismatch or incompatibility
   - FLAKY_TEST: Non-deterministic or intermittent test failure
   - INFRA_TIMEOUT: Cloud infrastructure timeout or unavailability
   - CODE_REGRESSION: New code commit broke existing functionality
   - UNKNOWN: Cannot determine cause from available information

2. Determine the action:
   - AUTO_FIX: Issue is clear enough to suggest an exact fix command
   - CREATE_ISSUE: Too complex or risky, requires human review

3. Rules for AUTO_FIX vs CREATE_ISSUE:
   - MISSING_ENV_VAR + FLAKY_TEST + INFRA_TIMEOUT = AUTO_FIX
   - DEPENDENCY_CONFLICT + CODE_REGRESSION + UNKNOWN = CREATE_ISSUE

4. Assign confidence score between 0.0 and 1.0

5. Write a one-line plain English root cause summary (max 80 chars)

6. If AUTO_FIX: write the exact terminal command to fix it
   If CREATE_ISSUE: write exactly 3 bullet investigation steps

7. Estimate fix time as a short string like "30 seconds" or "2 hours"

Respond ONLY with valid JSON, no markdown, no explanation, just the JSON object:
{
  "category": "CATEGORY_NAME",
  "confidence": 0.95,
  "action": "AUTO_FIX or CREATE_ISSUE",
  "root_cause": "One sentence plain English summary under 80 chars",
  "fix_command": "exact terminal command or null",
  "investigation_steps": ["step 1", "step 2", "step 3"],
  "severity": "CRITICAL or HIGH or MEDIUM",
  "estimated_fix_time": "30 seconds"
}
"""


# ── Claude API call ──────────────────────────────────────────────────────────

def call_claude(error_log: str) -> dict:
    """
    Send the error log to Claude and return a parsed dict.
    Raises an exception if the API call fails or the response is not valid JSON.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role":    "user",
                "content": f"Analyze this CI/CD pipeline failure:\n\n{error_log}",
            }
        ],
    )

    raw = message.content[0].text.strip()
    # Strip optional markdown code fence
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ── Async forward to Integrations ────────────────────────────────────────────

def forward_to_integrations(result: dict) -> None:
    """POST the merged AI result to the Integrations service (background thread)."""
    try:
        print(f"[ANALYZE] → Forwarding {result.get('incident_id')} to Integrations on :5002")
        resp = requests.post(
            "http://localhost:5002/act",
            json=result,
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"[ANALYZE] ✓ Integrations accepted {result.get('incident_id')}")
        else:
            print(f"[ANALYZE] ✗ Integrations returned HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[ANALYZE] ✗ Could not reach Integrations: {exc}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.after_request
def add_cors(response):
    """Allow cross-origin requests."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Classify a CI/CD incident with Claude.
    Falls back to emergency_backup if the API is unavailable.
    """
    try:
        incident    = request.json or {}
        incident_id = incident.get("incident_id", "UNKNOWN")
        error_log   = incident.get("error_log", "")
        workflow    = incident.get("workflow", "unknown")
        job         = incident.get("job", "unknown")

        print(f"\n[ANALYZE] {'='*52}")
        print(f"[ANALYZE] Processing incident {incident_id}")
        print(f"[ANALYZE] Pipeline : {workflow} / {job}")
        print(f"[ANALYZE] Calling Claude API (model: claude-sonnet-4-6)...")

        used_cache = False
        try:
            ai_result = call_claude(error_log)
            print(f"[ANALYZE] ✓ Claude responded successfully")
        except Exception as api_err:
            print(f"[ANALYZE] ✗ Claude API failed: {api_err}")
            print(f"[ANALYZE] ⚡ Loading emergency backup response...")
            ai_result  = get_cached_response(error_log)
            used_cache = True

        # Log the full decision
        conf_pct = int(ai_result.get("confidence", 0) * 100)
        print(f"[ANALYZE] Classification : {ai_result.get('category')} ({conf_pct}% confidence)")
        print(f"[ANALYZE] Severity       : {ai_result.get('severity')}")
        print(f"[ANALYZE] Decision       : {ai_result.get('action')}")
        print(f"[ANALYZE] Root cause     : {ai_result.get('root_cause')}")
        if ai_result.get("action") == "AUTO_FIX":
            print(f"[ANALYZE] Fix command    : {ai_result.get('fix_command')}")
        else:
            steps = ai_result.get("investigation_steps") or []
            for i, step in enumerate(steps, 1):
                print(f"[ANALYZE] Step {i}         : {step}")
        print(f"[ANALYZE] Est. fix time  : {ai_result.get('estimated_fix_time')}")
        if used_cache:
            print(f"[ANALYZE] ⚠ Used cached backup response (API unavailable)")
        print(f"[ANALYZE] {'='*52}")

        if used_cache:
            ai_result["used_cache"] = True

        # Merge AI result with incident metadata
        merged = {
            **ai_result,
            "incident_id": incident_id,
            "pipeline":    workflow,
            "job":         job,
            "repo":        incident.get("repository", "unknown"),
            "run_id":      incident.get("run_id", "unknown"),
            "timestamp":   incident.get("timestamp", ""),
            "error_log":   error_log,
        }

        # Non-blocking forward to Integrations
        threading.Thread(
            target=forward_to_integrations,
            args=(merged,),
            daemon=True,
        ).start()

        return jsonify(merged), 200

    except Exception as exc:
        print(f"[ANALYZE] ERROR: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Service health check."""
    return jsonify({
        "status":             "ok",
        "service":            "ai-agent",
        "port":               5001,
        "pillar":             "ANALYZE/DECIDE",
        "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }), 200


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("localhost", 5001))
        sock.close()
    except OSError:
        print("[ANALYZE] ERROR: Port 5001 is already in use.")
        print("[ANALYZE] Kill the existing process and retry.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ANALYZE] WARNING: ANTHROPIC_API_KEY not set — will use cached backup responses")

    print("[ANALYZE] AI Agent starting on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)

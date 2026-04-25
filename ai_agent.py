"""
AI Agent - Port 5001
Classifies CI/CD failures with Claude, emits progress events,
then triggers the integrations service.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests
import json
import time
import re
import os
import threading
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

_anthropic_client = None


def get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


# ─── Broadcast helper ─────────────────────────────────────────────────────────

def broadcast(event: dict):
    """Push an event to the webhook receiver's SSE hub."""
    try:
        requests.post(
            "http://localhost:5000/internal/broadcast",
            json=event,
            timeout=5,
        )
    except Exception:
        pass  # Dashboard update is non-critical


# ─── Claude classification ────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert AI DevOps engineer specialising in CI/CD pipeline forensics.
You receive a JSON payload describing a GitHub Actions workflow failure and must
produce a structured JSON root-cause analysis.

Always respond with ONLY valid JSON — no markdown, no prose, just the JSON object.
"""

USER_TEMPLATE = """\
Analyse the following CI/CD pipeline failure and return a JSON object with exactly
these keys:

{{
  "category": "<one of: dependency_issue | test_failure | build_error | deploy_error | config_error | resource_exhaustion | network_error | security_violation | unknown>",
  "severity": "<critical | high | medium | low>",
  "confidence": <integer 0-100>,
  "root_cause": "<concise 1-2 sentence explanation>",
  "remediation_steps": ["<step 1>", "<step 2>", "<step 3>"],
  "estimated_fix_time": "<human-readable estimate, e.g. 5-10 minutes>",
  "auto_fixable": <true | false>,
  "similar_incidents": <integer — estimated number of similar past incidents>
}}

Failure payload:
{payload}
"""


def classify_failure(failure_data: dict) -> dict:
    client = get_client()

    prompt = USER_TEMPLATE.format(payload=json.dumps(failure_data, indent=2))

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip optional markdown code fence
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/classify", methods=["POST"])
def classify():
    failure_data = request.json or {}
    workflow = failure_data.get("workflow_name", "Unknown Workflow")

    print(f"\n[AIAgent] Classifying: {workflow}")

    # Stage 1 – signal that analysis has started
    broadcast({
        "type":      "classification_started",
        "stage":     "AI_AGENT",
        "status":    "active",
        "title":     "AI Agent Analysing",
        "message":   f"Claude is performing root-cause analysis on '{workflow}'",
        "detail":    "Inspecting logs, error codes, and failure patterns…",
        "timestamp": time.time(),
    })

    try:
        classification = classify_failure(failure_data)

        result = {
            "original_failure": failure_data,
            "classification":   classification,
            "timestamp":        time.time(),
        }

        print(
            f"[AIAgent] Result: category={classification.get('category')}  "
            f"severity={classification.get('severity')}  "
            f"confidence={classification.get('confidence')}%"
        )

        broadcast({
            "type":           "classification_complete",
            "stage":          "AI_AGENT",
            "status":         "complete",
            "title":          "Classification Complete",
            "message":        f"Root cause identified: {classification.get('category', 'unknown').replace('_', ' ').title()}",
            "detail":         classification.get("root_cause", ""),
            "classification": classification,
            "timestamp":      time.time(),
        })

        # Fire integrations asynchronously
        def _notify():
            try:
                requests.post(
                    "http://localhost:5002/notify",
                    json=result,
                    timeout=30,
                )
            except Exception as exc:
                broadcast({
                    "type":      "error",
                    "stage":     "INTEGRATIONS",
                    "status":    "error",
                    "title":     "Integrations Unreachable",
                    "message":   str(exc),
                    "timestamp": time.time(),
                })

        threading.Thread(target=_notify, daemon=True).start()

        return jsonify(result)

    except json.JSONDecodeError as exc:
        msg = f"Claude returned non-JSON response: {exc}"
        print(f"[AIAgent] ERROR {msg}")
        broadcast({
            "type":      "error",
            "stage":     "AI_AGENT",
            "status":    "error",
            "title":     "Parse Error",
            "message":   msg,
            "timestamp": time.time(),
        })
        return jsonify({"error": msg}), 500

    except Exception as exc:
        msg = str(exc)
        print(f"[AIAgent] ERROR {msg}")
        broadcast({
            "type":      "error",
            "stage":     "AI_AGENT",
            "status":    "error",
            "title":     "Classification Failed",
            "message":   msg,
            "timestamp": time.time(),
        })
        return jsonify({"error": msg}), 500


@app.route("/health")
def health():
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({
        "status":      "ok",
        "service":     "ai-agent",
        "port":        5001,
        "api_key_set": api_key_set,
    })


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  AI Agent (Claude)  |  http://localhost:5001")
    print(f"  API Key configured  |  {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)

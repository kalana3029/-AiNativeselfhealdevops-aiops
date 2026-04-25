"""
SERVICE 1 — Webhook Receiver (port 5000)
OODA pillar: OBSERVE

Accepts GitHub Actions failure webhooks, generates incident IDs,
stores them in memory, and forwards them to the AI Agent asynchronously.
"""

import sys
import os
import socket
import threading
import datetime

import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Ensure project root is on the path so sibling modules are importable
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

# ── In-memory storage ────────────────────────────────────────────────────────
incidents: list[dict] = []
MAX_INCIDENTS = 100


# ── Helpers ──────────────────────────────────────────────────────────────────

def generate_incident_id() -> str:
    """Generate a human-readable incident ID: INC-HHMMSS."""
    return f"INC-{datetime.datetime.now().strftime('%H%M%S')}"


def forward_to_analyzer(incident: dict) -> None:
    """POST the incident to the AI Agent (runs in a background thread)."""
    try:
        print(f"[OBSERVE] → Forwarding {incident['incident_id']} to AI Agent on :5001")
        resp = requests.post(
            "http://localhost:5001/analyze",
            json=incident,
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"[OBSERVE] ✓ AI Agent accepted {incident['incident_id']}")
        else:
            print(f"[OBSERVE] ✗ AI Agent returned HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[OBSERVE] ✗ Could not reach AI Agent: {exc}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.after_request
def add_cors(response):
    """Allow cross-origin requests (dashboard served as file://)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """
    Entry point for GitHub Actions failure webhooks.
    Generates an incident, stores it, and asynchronously forwards it.
    Returns incident_id immediately so the caller is never blocked.
    """
    try:
        payload = request.json or {}

        incident_id = generate_incident_id()
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"

        incident = {
            "incident_id": incident_id,
            "timestamp":   timestamp,
            "status":      "detected",
            "workflow":    payload.get("workflow", "unknown"),
            "job":         payload.get("job", "unknown"),
            "repository":  payload.get("repository", "unknown"),
            "run_id":      payload.get("run_id", "unknown"),
            "error_log":   payload.get("error_log", ""),
        }

        incidents.append(incident)
        if len(incidents) > MAX_INCIDENTS:
            incidents.pop(0)

        print(f"\n[OBSERVE] {'='*52}")
        print(f"[OBSERVE] Incident {incident_id} detected")
        print(f"[OBSERVE] Pipeline : {incident['workflow']} / {incident['job']}")
        print(f"[OBSERVE] Repo     : {incident['repository']}")
        print(f"[OBSERVE] Run ID   : {incident['run_id']}")
        print(f"[OBSERVE] {'='*52}")

        # Non-blocking forward — webhook returns in <5 ms
        threading.Thread(
            target=forward_to_analyzer,
            args=(incident,),
            daemon=True,
        ).start()

        return jsonify({
            "incident_id": incident_id,
            "status":      "detected",
            "message":     "Incident received and dispatched for analysis",
        }), 200

    except Exception as exc:
        print(f"[OBSERVE] ERROR processing webhook: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Service health check."""
    return jsonify({
        "status":           "ok",
        "service":          "webhook-receiver",
        "port":             5000,
        "pillar":           "OBSERVE",
        "incidents_stored": len(incidents),
    }), 200


@app.route("/incidents", methods=["GET"])
def get_incidents():
    """Return the last 10 incidents (most recent first)."""
    return jsonify(list(reversed(incidents[-10:]))), 200


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("localhost", 5000))
        sock.close()
    except OSError:
        print("[OBSERVE] ERROR: Port 5000 is already in use.")
        print("[OBSERVE] Kill the existing process and retry.")
        sys.exit(1)

    print("[OBSERVE] Webhook Receiver starting on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

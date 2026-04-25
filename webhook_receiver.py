"""
Webhook Receiver - Port 5000
Hub service: receives GitHub Actions failure webhooks,
broadcasts real-time events via SSE, serves the live dashboard.
"""

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import requests
import json
import time
import queue
import threading
import os

app = Flask(__name__)
CORS(app)

# In-memory event log and SSE client queues
events_log = []
clients = []
clients_lock = threading.Lock()


def sse_broadcast(event_data: dict):
    """Append to log and push to every connected dashboard client."""
    events_log.append(event_data)
    if len(events_log) > 200:
        events_log.pop(0)

    with clients_lock:
        dead = []
        for q in clients:
            try:
                q.put_nowait(event_data)
            except queue.Full:
                dead.append(q)
        for q in dead:
            clients.remove(q)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def serve_dashboard():
    return send_from_directory(os.path.dirname(__file__), "dashboard.html")


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """Entry point: GitHub Actions posts failure payloads here."""
    payload = request.json or {}
    workflow = payload.get("workflow_name", "Unknown Workflow")
    repo     = payload.get("repository", "unknown/repo")
    run_id   = payload.get("run_id", "N/A")

    print(f"\n[WebhookReceiver] ← FAILURE  repo={repo}  workflow={workflow}  run={run_id}")

    sse_broadcast({
        "type":      "webhook_received",
        "stage":     "WEBHOOK",
        "status":    "active",
        "title":     "Webhook Received",
        "message":   f"GitHub Actions failure detected in '{workflow}'",
        "detail":    f"Repo: {repo} | Run ID: {run_id} | Branch: {payload.get('branch', 'main')}",
        "payload":   payload,
        "timestamp": time.time(),
    })

    # Forward to AI agent in a background thread so we can return immediately
    def _forward():
        try:
            resp = requests.post(
                "http://localhost:5001/classify",
                json=payload,
                timeout=90,
            )
            if resp.status_code != 200:
                sse_broadcast({
                    "type":      "error",
                    "stage":     "AI_AGENT",
                    "status":    "error",
                    "title":     "AI Agent Error",
                    "message":   f"AI Agent returned HTTP {resp.status_code}",
                    "timestamp": time.time(),
                })
        except Exception as exc:
            sse_broadcast({
                "type":      "error",
                "stage":     "AI_AGENT",
                "status":    "error",
                "title":     "AI Agent Unreachable",
                "message":   str(exc),
                "timestamp": time.time(),
            })

    threading.Thread(target=_forward, daemon=True).start()

    return jsonify({"status": "received", "message": "Processing started asynchronously"})


@app.route("/internal/broadcast", methods=["POST"])
def internal_broadcast():
    """Other services call this to push events to the dashboard."""
    event = request.json
    if event:
        sse_broadcast(event)
    return jsonify({"status": "ok"})


@app.route("/stream")
def sse_stream():
    """Server-Sent Events endpoint consumed by dashboard.html."""
    def generate():
        q = queue.Queue(maxsize=100)
        with clients_lock:
            clients.append(q)

        # Replay recent history so a freshly opened dashboard catches up
        for event in events_log[-30:]:
            yield f"data: {json.dumps(event)}\n\n"

        try:
            while True:
                try:
                    event = q.get(timeout=28)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
        except GeneratorExit:
            with clients_lock:
                if q in clients:
                    clients.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.route("/health")
def health():
    return jsonify({
        "status":  "ok",
        "service": "webhook-receiver",
        "port":    5000,
        "clients": len(clients),
        "events":  len(events_log),
    })


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Webhook Receiver  |  http://localhost:5000")
    print("  Dashboard         |  http://localhost:5000/")
    print("  SSE Stream        |  http://localhost:5000/stream")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

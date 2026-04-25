"""
SERVICE 3 — Integrations (port 5002)
OODA pillars: ACT + COMMUNICATE

Receives the AI decision, saves state, posts to Slack, and creates
GitHub Issues for incidents that require human review.
"""

import sys
import os
import json
import socket

import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

STATE_FILE = os.path.join(BASE_DIR, "demo_state.json")


# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack(result: dict) -> None:
    """
    Post a Slack notification using Block Kit.
    - AUTO_FIX  → green attachment with fix details
    - CREATE_ISSUE → orange attachment with investigation steps
    Falls back to console print if SLACK_WEBHOOK_URL is not configured.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    action      = result.get("action", "UNKNOWN")
    pipeline    = result.get("pipeline", "unknown")
    category    = result.get("category", "UNKNOWN")
    confidence  = int(result.get("confidence", 0) * 100)
    root_cause  = result.get("root_cause", "N/A")
    incident_id = result.get("incident_id", "N/A")
    severity    = result.get("severity", "N/A")
    fix_time    = result.get("estimated_fix_time", "N/A")

    if action == "AUTO_FIX":
        fix_cmd = result.get("fix_command") or "N/A"
        color   = "#36a64f"
        title   = f":white_check_mark: Auto-Fix Applied — {incident_id}"
        blocks  = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"✅ Auto-Fix Applied — {incident_id}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Pipeline:*\n{pipeline}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{category}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence}%"},
                    {"type": "mrkdwn", "text": f"*Est. Fix Time:*\n{fix_time}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Fix Command Applied:*\n```{fix_cmd}```",
                },
            },
        ]
    else:
        steps = result.get("investigation_steps") or []
        steps_text = "\n".join(f"• {s}" for s in steps)
        color  = "#ff9000"
        title  = f":ticket: GitHub Issue Created — {incident_id}"
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🎫 GitHub Issue Created — {incident_id}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Pipeline:*\n{pipeline}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{category}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence}%"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Investigation Steps:*\n{steps_text}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": ":github: GitHub Issue created automatically by AI DevOps Agent"},
                ],
            },
        ]

    payload = {
        "text":        title,
        "attachments": [{"color": color, "blocks": blocks}],
    }

    if not webhook_url:
        print("[COMMUNICATE] Slack not configured — printing to console")
        print(f"[COMMUNICATE] SLACK MESSAGE: {title}")
        print(f"[COMMUNICATE]   Category  : {category} | Confidence: {confidence}%")
        print(f"[COMMUNICATE]   Root cause: {root_cause}")
        if action == "AUTO_FIX":
            print(f"[COMMUNICATE]   Fix cmd   : {result.get('fix_command')}")
        return

    try:
        print("[COMMUNICATE] Sending Slack notification...")
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        print("[COMMUNICATE] ✓ Slack notification sent successfully")
    except Exception as exc:
        print(f"[COMMUNICATE] ✗ Slack notification failed: {exc}")


# ── GitHub Issues ─────────────────────────────────────────────────────────────

def create_github_issue(result: dict) -> None:
    """
    Create a GitHub Issue with a full AI incident report.
    Falls back to console print if GITHUB_TOKEN / GITHUB_REPO are not set.
    """
    token     = os.environ.get("GITHUB_TOKEN", "")
    repo      = os.environ.get("GITHUB_REPO", "")
    category  = result.get("category", "UNKNOWN")
    root_cause = result.get("root_cause", "N/A")
    incident_id = result.get("incident_id", "N/A")
    timestamp   = result.get("timestamp", "N/A")
    confidence  = result.get("confidence", 0)
    severity    = result.get("severity", "N/A")
    pipeline    = result.get("pipeline", "unknown")
    steps       = result.get("investigation_steps") or []

    title = f"[AI-DEVOPS] {category}: {root_cause[:60]}"

    steps_md = "\n".join(f"- [ ] {s}" for s in steps)

    category_descriptions = {
        "MISSING_ENV_VAR":    "A required environment variable is not configured in the deployment environment.",
        "DEPENDENCY_CONFLICT": "A package version conflict prevents the build from completing successfully.",
        "FLAKY_TEST":         "A non-deterministic test failed intermittently, not due to a code change.",
        "INFRA_TIMEOUT":      "A cloud infrastructure resource was unavailable or timed out.",
        "CODE_REGRESSION":    "A recent commit introduced a regression that broke existing functionality.",
        "UNKNOWN":            "The AI agent could not determine the root cause from the available logs.",
    }
    category_desc = category_descriptions.get(category, "See category name.")

    body = f"""## AI Incident Report

| Field | Value |
|---|---|
| **Incident ID** | `{incident_id}` |
| **Timestamp** | {timestamp} |
| **Confidence Score** | {int(confidence * 100)}% |
| **Pipeline** | {pipeline} |
| **Severity** | {severity} |

## Root Cause

{root_cause}

## Failure Category

**{category}** — {category_desc}

## Investigation Steps

{steps_md}

## What the AI Agent Tried

The AI agent received the CI/CD failure log, analysed it using Claude (claude-sonnet-4-6),
and classified the incident as `{category}` with {int(confidence * 100)}% confidence.
The confidence threshold for automatic remediation was not met for this category
(`{category}` requires human review per policy), so the agent escalated to a GitHub Issue
to ensure an engineer reviews the root cause before any fix is applied.

## Suggested Fix

1. Review the investigation steps above
2. Examine the full build log in the linked GitHub Actions run
3. Apply a fix in a feature branch and validate in staging before merging to main

---
*Auto-generated by AI-Native Self-Healing DevOps Platform · Incident `{incident_id}`*
"""

    if not token or not repo:
        print("[COMMUNICATE] GitHub not configured — printing issue to console")
        print(f"[COMMUNICATE] GITHUB ISSUE TITLE : {title}")
        print(f"[COMMUNICATE] GITHUB ISSUE BODY  :\n{body}")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
    }
    payload = {
        "title":  title,
        "body":   body,
        "labels": ["ai-detected", "incident"],
    }

    try:
        print(f"[COMMUNICATE] Creating GitHub Issue in {repo}...")
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/issues",
            json=payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        issue = resp.json()
        print(f"[COMMUNICATE] ✓ GitHub Issue #{issue['number']} created: {issue['html_url']}")
    except Exception as exc:
        print(f"[COMMUNICATE] ✗ GitHub Issue creation failed: {exc}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.after_request
def add_cors(response):
    """Allow cross-origin requests (dashboard served as file://)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/act", methods=["POST"])
def act():
    """
    Receive the AI decision, persist it, and fire all configured integrations.
    """
    try:
        result      = request.json or {}
        incident_id = result.get("incident_id", "UNKNOWN")
        action      = result.get("action", "UNKNOWN")
        pipeline    = result.get("pipeline", "unknown")

        print(f"\n[COMMUNICATE] {'='*52}")
        print(f"[COMMUNICATE] Received action for incident {incident_id}")
        print(f"[COMMUNICATE] Pipeline : {pipeline}")
        print(f"[COMMUNICATE] Action   : {action}")

        # 1. Persist state so the dashboard can poll it
        try:
            with open(STATE_FILE, "w") as fh:
                json.dump(result, fh, indent=2)
            print(f"[COMMUNICATE] ✓ State saved to demo_state.json")
        except Exception as exc:
            print(f"[COMMUNICATE] ✗ Failed to save state: {exc}")

        # 2. Slack notification (always)
        send_slack(result)

        # 3. GitHub Issue (only for CREATE_ISSUE)
        if action == "CREATE_ISSUE":
            create_github_issue(result)

        print(f"[COMMUNICATE] ✓ All integrations complete for {incident_id}")
        print(f"[COMMUNICATE] {'='*52}")

        return jsonify({"status": "ok", "incident_id": incident_id}), 200

    except Exception as exc:
        print(f"[COMMUNICATE] ERROR: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/state", methods=["GET"])
def get_state():
    """Return the latest demo_state.json so the dashboard can poll it."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as fh:
                return jsonify(json.load(fh)), 200
        return jsonify({}), 200
    except Exception as exc:
        print(f"[COMMUNICATE] ERROR reading state: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Service health check."""
    return jsonify({
        "status":             "ok",
        "service":            "integrations",
        "port":               5002,
        "pillar":             "ACT/COMMUNICATE",
        "slack_configured":   bool(os.environ.get("SLACK_WEBHOOK_URL")),
        "github_configured":  bool(
            os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO")
        ),
    }), 200


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("localhost", 5002))
        sock.close()
    except OSError:
        print("[COMMUNICATE] ERROR: Port 5002 is already in use.")
        print("[COMMUNICATE] Kill the existing process and retry.")
        sys.exit(1)

    slack_ok  = bool(os.environ.get("SLACK_WEBHOOK_URL"))
    github_ok = bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))
    print(f"[COMMUNICATE] Slack  : {'configured' if slack_ok  else 'not configured — console fallback'}")
    print(f"[COMMUNICATE] GitHub : {'configured' if github_ok else 'not configured — console fallback'}")
    print("[COMMUNICATE] Integrations Service starting on http://localhost:5002")
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)

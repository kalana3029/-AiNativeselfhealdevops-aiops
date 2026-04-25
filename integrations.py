"""
Integrations Service - Port 5002
Fires Slack notifications and creates GitHub Issues when an AI-classified
failure arrives.  Works in MOCK mode (no tokens needed) or LIVE mode.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import time
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

SLACK_WEBHOOK_URL   = os.environ.get("SLACK_WEBHOOK_URL", "")
GITHUB_TOKEN        = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO         = os.environ.get("GITHUB_REPO", "")  # e.g. "owner/repo"

MOCK_MODE = not (SLACK_WEBHOOK_URL and GITHUB_TOKEN and GITHUB_REPO)


# ─── Broadcast helper ─────────────────────────────────────────────────────────

def broadcast(event: dict):
    try:
        requests.post(
            "http://localhost:5000/internal/broadcast",
            json=event,
            timeout=5,
        )
    except Exception:
        pass


# ─── Slack ────────────────────────────────────────────────────────────────────

SEVERITY_EMOJI = {
    "critical": ":red_circle:",
    "high":     ":large_orange_circle:",
    "medium":   ":large_yellow_circle:",
    "low":      ":white_circle:",
}

SEVERITY_COLOR = {
    "critical": "#FF0000",
    "high":     "#FF6600",
    "medium":   "#FFAA00",
    "low":      "#36A64F",
}


def send_slack_notification(failure: dict, classification: dict) -> dict:
    severity  = classification.get("severity", "unknown")
    category  = classification.get("category", "unknown").replace("_", " ").title()
    workflow  = failure.get("workflow_name", "Unknown Workflow")
    repo      = failure.get("repository", "unknown/repo")
    branch    = failure.get("branch", "main")
    run_url   = failure.get("run_url", f"https://github.com/{repo}/actions")
    steps     = classification.get("remediation_steps", [])
    fix_time  = classification.get("estimated_fix_time", "unknown")
    auto_fix  = classification.get("auto_fixable", False)
    emoji     = SEVERITY_EMOJI.get(severity, ":warning:")
    color     = SEVERITY_COLOR.get(severity, "#888888")

    remediation_text = "\n".join(f"• {s}" for s in steps[:5])

    message = {
        "text": f"{emoji} *CI/CD Failure Detected* — `{workflow}` on `{repo}`",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                            {"type": "mrkdwn", "text": f"*Category:*\n{category}"},
                            {"type": "mrkdwn", "text": f"*Repository:*\n`{repo}`"},
                            {"type": "mrkdwn", "text": f"*Branch:*\n`{branch}`"},
                            {"type": "mrkdwn", "text": f"*Est. Fix Time:*\n{fix_time}"},
                            {"type": "mrkdwn", "text": f"*Auto-Fixable:*\n{'Yes :white_check_mark:' if auto_fix else 'No :x:'}"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Root Cause:*\n{classification.get('root_cause', 'N/A')}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Remediation Steps:*\n{remediation_text}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type":  "button",
                                "text":  {"type": "plain_text", "text": "View Run"},
                                "url":   run_url,
                                "style": "danger",
                            }
                        ],
                    },
                ],
            }
        ],
    }

    if MOCK_MODE:
        print(f"[Integrations][MOCK] Slack → {workflow} ({severity})")
        return {"mock": True, "channel": "#alerts", "message_preview": message["text"]}

    resp = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
    resp.raise_for_status()
    return {"mock": False, "status": "sent", "http_status": resp.status_code}


# ─── GitHub Issues ────────────────────────────────────────────────────────────

def create_github_issue(failure: dict, classification: dict) -> dict:
    severity = classification.get("severity", "unknown")
    category = classification.get("category", "unknown").replace("_", " ").title()
    workflow = failure.get("workflow_name", "Unknown Workflow")
    repo     = failure.get("repository", "unknown/repo")
    branch   = failure.get("branch", "main")
    run_url  = failure.get("run_url", "#")
    steps    = classification.get("remediation_steps", [])
    fix_time = classification.get("estimated_fix_time", "unknown")
    auto_fix = classification.get("auto_fixable", False)
    ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    remediation_md = "\n".join(f"- [ ] {s}" for s in steps)

    body = f"""## CI/CD Failure Auto-Report

| Field | Value |
|---|---|
| **Workflow** | `{workflow}` |
| **Repository** | `{repo}` |
| **Branch** | `{branch}` |
| **Severity** | `{severity.upper()}` |
| **Category** | {category} |
| **Confidence** | {classification.get('confidence', 0)}% |
| **Est. Fix Time** | {fix_time} |
| **Auto-Fixable** | {'Yes' if auto_fix else 'No'} |
| **Detected** | {ts} |

### Root Cause

{classification.get('root_cause', 'N/A')}

### Remediation Steps

{remediation_md}

### Links

- [View GitHub Actions Run]({run_url})

---
*This issue was automatically created by the AI-Native Self-Healing DevOps Platform.*
"""

    title  = f"[{severity.upper()}] CI/CD Failure: {category} in `{workflow}`"
    labels = [f"severity:{severity}", "ci-failure", "auto-generated"]
    payload = {"title": title, "body": body, "labels": labels}

    if MOCK_MODE:
        mock_number = int(time.time()) % 10000
        print(f"[Integrations][MOCK] GitHub Issue #{mock_number} → {title}")
        return {
            "mock":         True,
            "issue_number": mock_number,
            "title":        title,
            "url":          f"https://github.com/{repo}/issues/{mock_number}",
        }

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        "mock":         False,
        "issue_number": data["number"],
        "title":        data["title"],
        "url":          data["html_url"],
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/notify", methods=["POST"])
def notify():
    body           = request.json or {}
    failure        = body.get("original_failure", {})
    classification = body.get("classification", {})
    workflow       = failure.get("workflow_name", "Unknown Workflow")

    print(f"\n[Integrations] Firing notifications for: {workflow}")

    broadcast({
        "type":      "integrations_started",
        "stage":     "INTEGRATIONS",
        "status":    "active",
        "title":     "Firing Integrations",
        "message":   "Sending Slack alert and creating GitHub Issue…",
        "detail":    f"Mode: {'MOCK' if MOCK_MODE else 'LIVE'}",
        "timestamp": time.time(),
    })

    results = {}

    # ── Slack ──
    try:
        slack_result = send_slack_notification(failure, classification)
        results["slack"] = {"status": "ok", **slack_result}
        broadcast({
            "type":      "slack_sent",
            "stage":     "INTEGRATIONS",
            "status":    "active",
            "title":     "Slack Notification Sent",
            "message":   f"Alert posted to #dev-alerts {'(mock)' if MOCK_MODE else ''}",
            "detail":    f"Workflow: {workflow} | Severity: {classification.get('severity', '?').upper()}",
            "timestamp": time.time(),
        })
    except Exception as exc:
        results["slack"] = {"status": "error", "message": str(exc)}
        broadcast({
            "type":      "error",
            "stage":     "INTEGRATIONS",
            "status":    "error",
            "title":     "Slack Failed",
            "message":   str(exc),
            "timestamp": time.time(),
        })

    # ── GitHub ──
    try:
        gh_result = create_github_issue(failure, classification)
        results["github"] = {"status": "ok", **gh_result}
        broadcast({
            "type":      "github_issue_created",
            "stage":     "INTEGRATIONS",
            "status":    "active",
            "title":     "GitHub Issue Created",
            "message":   f"Issue #{gh_result.get('issue_number')} created {'(mock)' if MOCK_MODE else ''}",
            "detail":    gh_result.get("url", ""),
            "timestamp": time.time(),
        })
    except Exception as exc:
        results["github"] = {"status": "error", "message": str(exc)}
        broadcast({
            "type":      "error",
            "stage":     "INTEGRATIONS",
            "status":    "error",
            "title":     "GitHub Issue Failed",
            "message":   str(exc),
            "timestamp": time.time(),
        })

    # ── Final summary ──
    broadcast({
        "type":      "integrations_complete",
        "stage":     "INTEGRATIONS",
        "status":    "complete",
        "title":     "All Integrations Complete",
        "message":   "Incident fully handled — team notified, ticket created.",
        "detail":    f"Slack: {results.get('slack', {}).get('status')}  |  GitHub: {results.get('github', {}).get('status')}",
        "results":   results,
        "timestamp": time.time(),
    })

    broadcast({
        "type":           "healing_complete",
        "stage":          "DASHBOARD",
        "status":         "complete",
        "title":          "Self-Healing Cycle Complete",
        "message":        "AI agent detected, classified, and remediated the failure.",
        "classification": classification,
        "results":        results,
        "timestamp":      time.time(),
    })

    return jsonify({"status": "ok", "mock_mode": MOCK_MODE, "results": results})


@app.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "service":   "integrations",
        "port":      5002,
        "mock_mode": MOCK_MODE,
        "slack":     bool(SLACK_WEBHOOK_URL),
        "github":    bool(GITHUB_TOKEN and GITHUB_REPO),
    })


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = "MOCK (no tokens configured)" if MOCK_MODE else "LIVE"
    print("=" * 60)
    print(f"  Integrations Service  |  http://localhost:5002")
    print(f"  Mode                  |  {mode}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)

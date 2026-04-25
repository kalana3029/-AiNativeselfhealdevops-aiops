# AI-Native Self-Healing DevOps Platform

An end-to-end demo showing an AI agent automatically detecting, classifying,
and responding to CI/CD pipeline failures in real time — powered by Claude.

---

## 1. Prerequisites

- Python 3.11 or higher
- pip (comes with Python)
- An Anthropic API key (get one at https://console.anthropic.com)
- Optional: Slack Incoming Webhook URL, GitHub personal access token

---

## 2. Installation

```bash
# 1. Clone the repository
git clone <your-repo-url> && cd <repo-name>

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure environment variables
cp .env.example .env
```

---

## 3. Configuration

Edit `.env` and fill in your values:

```env
# Required — the demo uses Claude for root-cause analysis
ANTHROPIC_API_KEY=sk-ant-...
  # Get your key at: https://console.anthropic.com/settings/keys

# Optional — enables live Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
  # Create one at: https://api.slack.com/messaging/webhooks

# Optional — enables automatic GitHub Issue creation
GITHUB_TOKEN=ghp_...
  # Create one at: https://github.com/settings/tokens (scope: repo)
GITHUB_REPO=your-username/your-repo-name
```

> If Slack or GitHub are not configured the platform still works — it prints
> the notification and issue body to the terminal instead.

---

## 4. Running the Demo

```bash
# Terminal 1 — start all three services
python start_all.py

# Open dashboard.html in your browser (double-click the file)

# Terminal 2 — trigger a failure scenario
python trigger_failure.py 1   # Missing environment variable (AUTO_FIX)
python trigger_failure.py 2   # Dependency conflict (CREATE_ISSUE)
python trigger_failure.py 3   # Flaky test (AUTO_FIX)
```

---

## 5. Demo Script (90-second live walkthrough)

> Say this to the judges while the demo runs:

**[0:00]** "This is an AI-native DevOps platform built on the OODA loop — Observe,
Analyze, Decide, Act, Communicate. Every CI/CD failure triggers an automated
AI-driven response with no human intervention required."

**[0:10]** *(run `python trigger_failure.py 1`)* "I'm firing a simulated GitHub
Actions failure — a missing environment variable has crashed our production deploy."

**[0:20]** "The Webhook Receiver catches it instantly and generates Incident
ID INC-HHMMSS. You can see the OBSERVE pill turn green on the dashboard."

**[0:30]** "The AI Agent sends the error log to Claude. Watch — it classifies
this as MISSING_ENV_VAR with 97% confidence and decides AUTO_FIX is safe."

**[0:45]** "The exact fix command is generated and handed to the Integrations
service. A Slack message goes to the team, the fix is logged — all automatically."

**[0:55]** "The dashboard shows the full OODA cycle complete. MTTR: under
10 seconds. For comparison, a human would take 20-40 minutes to diagnose this."

**[1:05]** *(run `python trigger_failure.py 2`)* "Now a dependency conflict —
the AI correctly decides CREATE_ISSUE because this requires human review.
A GitHub Issue is created automatically with full investigation steps."

**[1:20]** "The platform handles three failure categories out of the box,
has emergency fallback when the API is unavailable, and needs just one
environment variable to run. This is AI-native DevOps."

---

## 6. Troubleshooting

**Port already in use**
```
ERROR: Port 5000 is already in use.
```
Kill the existing process: `npx kill-port 5000 5001 5002` or restart your terminal.

**ANTHROPIC_API_KEY not set**
The AI Agent logs a warning and uses `emergency_backup.py` cached responses.
The demo still works — set the key for live Claude analysis.

**Dashboard shows "Waiting for incidents" after trigger**
Check that all three services are running (`python test_all.py`).
Confirm `demo_state.json` is being written to the project root.

**Slack notification not appearing**
Check that `SLACK_WEBHOOK_URL` is the full webhook URL starting with
`https://hooks.slack.com/`. The platform falls back to console output silently.

**GitHub Issue creation fails**
Ensure `GITHUB_TOKEN` has `repo` scope and `GITHUB_REPO` is in `owner/repo`
format. The platform falls back to printing the issue body to console.

---

## 7. Fallback Options

| Failure | Fallback |
|---|---|
| Claude API unavailable | `emergency_backup.py` returns pre-classified cached responses |
| Slack not configured | Notification printed to the Integrations terminal |
| GitHub not configured | Issue body printed to the Integrations terminal |
| Any service crashes | `start_all.py` auto-restarts the crashed service |
| Dashboard blank | Open `demo_state.json` directly — it has the full AI result |

---

## Architecture

```
GitHub Actions Failure
        |
        v POST /webhook
+---------------------+
|  Webhook Receiver   |  port 5000  [OBSERVE]
|  services/webhook_  |
|  receiver.py        |
+--------+------------+
         | POST /analyze (async thread)
         v
+---------------------+
|    AI Agent         |  port 5001  [ANALYZE + DECIDE]
|  services/          |  Claude claude-sonnet-4-6
|  ai_agent.py        |
+--------+------------+
         | POST /act (async thread)
         v
+---------------------+
|   Integrations      |  port 5002  [ACT + COMMUNICATE]
|  services/          |  Slack + GitHub Issues
|  integrations.py    |
+--------+------------+
         | GET /state (poll every 1s)
         v
+---------------------+
|   dashboard.html    |  browser
|   Live OODA view    |
+---------------------+
```

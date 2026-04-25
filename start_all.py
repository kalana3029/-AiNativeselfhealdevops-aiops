"""
start_all.py — Single entry point for the demo.

Starts all 3 Flask services as separate subprocesses, waits for them to
become healthy, prints demo instructions, then blocks until Ctrl+C.
"""

import os
import sys
import time
import signal
import subprocess

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SERVICES = [
    {
        "name":   "Webhook Receiver",
        "script": os.path.join(BASE_DIR, "services", "webhook_receiver.py"),
        "port":   5000,
        "pillar": "OBSERVE",
        "prefix": "[OBSERVE]",
    },
    {
        "name":   "AI Agent",
        "script": os.path.join(BASE_DIR, "services", "ai_agent.py"),
        "port":   5001,
        "pillar": "ANALYZE/DECIDE",
        "prefix": "[ANALYZE]",
    },
    {
        "name":   "Integrations",
        "script": os.path.join(BASE_DIR, "services", "integrations.py"),
        "port":   5002,
        "pillar": "ACT/COMMUNICATE",
        "prefix": "[COMMUNICATE]",
    },
]

DEMO_INSTRUCTIONS = """
================================
  AI DEVOPS DEMO — READY
================================
  Dashboard : Open dashboard.html in your browser
  Trigger   : python trigger_failure.py [1|2|3]
  Health    : python test_all.py
  Stop      : Ctrl+C
================================

  Scenarios:
    1 — Missing Environment Variable (AUTO_FIX)
    2 — Dependency Conflict         (CREATE_ISSUE)
    3 — Flaky Test                  (AUTO_FIX)

================================
"""


def wait_for_healthy(port: int, retries: int = 15, delay: float = 0.5) -> bool:
    """Poll the /health endpoint until the service responds or we time out."""
    url = f"http://localhost:{port}/health"
    for _ in range(retries):
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def main() -> None:
    """Start all services and block until the user presses Ctrl+C."""
    # ── Environment ──────────────────────────────────────────────────────────
    env = os.environ.copy()
    # Make the project root importable from inside services/
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        BASE_DIR + os.pathsep + existing_pythonpath
        if existing_pythonpath
        else BASE_DIR
    )

    print("\n" + "=" * 52)
    print("  AI-Native Self-Healing DevOps Platform")
    print("  Starting all services…")
    print("=" * 52 + "\n")

    if not env.get("ANTHROPIC_API_KEY"):
        print("  WARNING: ANTHROPIC_API_KEY is not set.")
        print("  The AI Agent will use cached backup responses.\n")

    # ── Launch subprocesses ───────────────────────────────────────────────────
    processes: list[subprocess.Popen] = []

    for svc in SERVICES:
        print(f"  Starting {svc['name']} on port {svc['port']}…")
        proc = subprocess.Popen(
            [sys.executable, svc["script"]],
            cwd=BASE_DIR,
            env=env,
        )
        processes.append(proc)
        # Short stagger so each service finishes binding before the next starts
        time.sleep(0.8)

    # ── Health checks ─────────────────────────────────────────────────────────
    print("\n  Waiting for services to become healthy…\n")
    all_ok = True
    for svc in SERVICES:
        ok = wait_for_healthy(svc["port"])
        status = "READY" if ok else "NOT RESPONDING"
        mark   = "✓" if ok else "✗"
        print(f"  {mark} {svc['name']:20s} http://localhost:{svc['port']}  [{status}]")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n  WARNING: One or more services did not start correctly.")
        print("  Check the output above for errors.\n")

    # ── Demo instructions ─────────────────────────────────────────────────────
    print(DEMO_INSTRUCTIONS)

    # ── Block until Ctrl+C ────────────────────────────────────────────────────
    def shutdown(signum=None, frame=None):
        print("\n\n  Shutting down all services…")
        for proc in processes:
            try:
                proc.terminate()
            except Exception:
                pass
        # Give them a moment to exit gracefully
        time.sleep(1)
        for proc in processes:
            try:
                proc.kill()
            except Exception:
                pass
        print("  All services stopped. Goodbye.\n")
        sys.exit(0)

    # Register signal handlers (works on Unix; on Windows Ctrl+C raises KeyboardInterrupt)
    try:
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT,  shutdown)
    except (OSError, ValueError):
        pass  # Some environments don't support all signals

    try:
        # Monitor child processes; if any exits unexpectedly, warn the user
        while True:
            time.sleep(2)
            for i, proc in enumerate(processes):
                ret = proc.poll()
                if ret is not None:
                    svc = SERVICES[i]
                    print(f"\n  WARNING: {svc['name']} exited unexpectedly (code {ret})")
                    print(f"  Restarting {svc['name']}…")
                    new_proc = subprocess.Popen(
                        [sys.executable, svc["script"]],
                        cwd=BASE_DIR,
                        env=env,
                    )
                    processes[i] = new_proc
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()

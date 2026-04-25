"""
Demo Trigger
Sends a realistic GitHub Actions failure webhook to the local platform.
Run this AFTER all three services are started.

Usage:
    python demo_trigger.py              # random scenario
    python demo_trigger.py 2            # specific scenario (1-6)
    python demo_trigger.py all          # fire all scenarios with delays
"""

import requests
import json
import sys
import time
import random

WEBHOOK_URL = "http://localhost:5001/classify"  # direct to AI agent for faster demo
# Or send to webhook receiver: "http://localhost:5000/webhook"
WEBHOOK_URL = "http://localhost:5000/webhook"

# ─── Realistic failure scenarios ──────────────────────────────────────────────

SCENARIOS = [
    {
        "id": 1,
        "name": "Dependency Hell",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "CI Pipeline",
            "repository":     "acme-corp/backend-api",
            "branch":         "feature/auth-refactor",
            "run_id":         "8472910345",
            "run_url":        "https://github.com/acme-corp/backend-api/actions/runs/8472910345",
            "commit_sha":     "a3f8c21d",
            "actor":          "dev-alice",
            "conclusion":     "failure",
            "failed_step":    "Install Dependencies",
            "error_message":  (
                "ERROR: pip's dependency resolver does not currently take into account "
                "all the packages that are installed. This behaviour is the source of the "
                "following dependency conflicts.\n"
                "cryptography 41.0.0 requires cffi>=1.12, but you have cffi 1.11.5 which is incompatible.\n"
                "ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device"
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   47,
        },
    },
    {
        "id": 2,
        "name": "Test Suite Failure",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "Test & Lint",
            "repository":     "acme-corp/payment-service",
            "branch":         "main",
            "run_id":         "8472911001",
            "run_url":        "https://github.com/acme-corp/payment-service/actions/runs/8472911001",
            "commit_sha":     "b7d2e44f",
            "actor":          "dev-bob",
            "conclusion":     "failure",
            "failed_step":    "Run Tests",
            "error_message":  (
                "FAILED tests/test_payment_processor.py::TestChargeCard::test_stripe_webhook_signature - "
                "AssertionError: Expected status 200 but got 422\n"
                "FAILED tests/test_refund.py::TestRefundFlow::test_partial_refund - "
                "stripe.error.InvalidRequestError: No such charge: 'ch_test_missing'\n"
                "23 passed, 2 failed in 18.34s"
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   89,
        },
    },
    {
        "id": 3,
        "name": "Docker Build Error",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "Build & Push Image",
            "repository":     "acme-corp/ml-inference",
            "branch":         "release/v2.4.0",
            "run_id":         "8472912500",
            "run_url":        "https://github.com/acme-corp/ml-inference/actions/runs/8472912500",
            "commit_sha":     "c9a1f55b",
            "actor":          "dev-carol",
            "conclusion":     "failure",
            "failed_step":    "Build Docker Image",
            "error_message":  (
                "Step 7/12 : RUN pip install torch==2.1.0+cu118 --index-url https://download.pytorch.org/whl/cu118\n"
                " ---> Running in 3a8f7b2c1d4e\n"
                "ERROR: Could not find a version that satisfies the requirement torch==2.1.0+cu118\n"
                "ERROR: No matching distribution found for torch==2.1.0+cu118\n"
                "error: failed to solve: process '/bin/sh -c pip install...' did not complete successfully: exit code 1"
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   203,
        },
    },
    {
        "id": 4,
        "name": "Deploy to Production Failed",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "Deploy to Production",
            "repository":     "acme-corp/customer-portal",
            "branch":         "main",
            "run_id":         "8472913800",
            "run_url":        "https://github.com/acme-corp/customer-portal/actions/runs/8472913800",
            "commit_sha":     "d0b3e66c",
            "actor":          "ci-bot",
            "conclusion":     "failure",
            "failed_step":    "Kubernetes Rolling Deploy",
            "error_message":  (
                "Error from server: error when creating deployment: "
                "admission webhook 'validate.kyverno.svc' denied the request: "
                "resource Deployment/prod/customer-portal was blocked due to the following policies: "
                "require-image-digest: autogen-check-image-digest: "
                "validation error: An image digest must be specified. "
                "Rule autogen-check-image-digest failed at path /spec/template/spec/containers/0/image/"
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   315,
        },
    },
    {
        "id": 5,
        "name": "OOM / Resource Exhaustion",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "Integration Tests",
            "repository":     "acme-corp/data-pipeline",
            "branch":         "feature/batch-processing",
            "run_id":         "8472915200",
            "run_url":        "https://github.com/acme-corp/data-pipeline/actions/runs/8472915200",
            "commit_sha":     "e1c4f77d",
            "actor":          "dev-dave",
            "conclusion":     "failure",
            "failed_step":    "Run Integration Tests",
            "error_message":  (
                "fatal error: runtime: out of memory\n\n"
                "runtime stack:\n"
                "runtime.throw2({0x1a2b3c, 0x0})\n"
                "        /usr/local/go/src/runtime/panic.go:1023 +0x57\n"
                "runtime.sysMap(0xc000000000, 0x80000000, 0x7f2b8c0d9140)\n"
                "The process 'python -m pytest' was killed with signal SIGKILL (OOM Killer)\n"
                "Memory usage peaked at 14.2 GB (limit: 14 GB)"
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   621,
        },
    },
    {
        "id": 6,
        "name": "Security Scan Violation",
        "payload": {
            "event":          "workflow_run",
            "action":         "completed",
            "workflow_name":  "Security Scan",
            "repository":     "acme-corp/api-gateway",
            "branch":         "feature/new-endpoint",
            "run_id":         "8472916700",
            "run_url":        "https://github.com/acme-corp/api-gateway/actions/runs/8472916700",
            "commit_sha":     "f2d5g88e",
            "actor":          "dev-eve",
            "conclusion":     "failure",
            "failed_step":    "Trivy Vulnerability Scan",
            "error_message":  (
                "CRITICAL: 3 vulnerabilities found\n"
                "CVE-2024-21626 (CRITICAL) in runc 1.1.11 - container escape vulnerability\n"
                "CVE-2023-44487 (HIGH) in golang.org/x/net v0.15.0 - HTTP/2 Rapid Reset Attack\n"
                "CVE-2024-0232 (HIGH) in sqlite 3.43.2 - heap use-after-free\n"
                "Policy: block-on-critical is ENABLED — pipeline halted."
            ),
            "runner_os":      "ubuntu-22.04",
            "duration_sec":   58,
        },
    },
]


def fire(scenario: dict):
    payload = scenario["payload"]
    print(f"\n{'='*60}")
    print(f"  Firing Scenario #{scenario['id']}: {scenario['name']}")
    print(f"  Repo: {payload['repository']}  |  Workflow: {payload['workflow_name']}")
    print(f"{'='*60}")

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"  Webhook accepted: {data.get('message', 'ok')}")
        print(f"  Watch the dashboard at http://localhost:5000/")
    except requests.ConnectionError:
        print(f"\n  ERROR: Cannot reach {WEBHOOK_URL}")
        print("  Make sure all services are running:")
        print("    bash start_demo.sh")
        sys.exit(1)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)


def main():
    args = sys.argv[1:]

    if not args:
        # Pick a random scenario
        scenario = random.choice(SCENARIOS)
        fire(scenario)

    elif args[0].lower() == "all":
        for i, scenario in enumerate(SCENARIOS):
            fire(scenario)
            if i < len(SCENARIOS) - 1:
                print("\n  Waiting 8 seconds before next scenario…")
                time.sleep(8)
        print("\n  All scenarios fired!")

    elif args[0].lower() == "list":
        print("\nAvailable scenarios:")
        for s in SCENARIOS:
            print(f"  {s['id']}. {s['name']:30s}  ({s['payload']['repository']})")

    else:
        try:
            idx = int(args[0])
            match = next((s for s in SCENARIOS if s["id"] == idx), None)
            if not match:
                print(f"Scenario {idx} not found. Run `python demo_trigger.py list`")
                sys.exit(1)
            fire(match)
        except ValueError:
            print(f"Unknown argument: {args[0]}")
            print("Usage: python demo_trigger.py [1-6 | all | list]")
            sys.exit(1)


if __name__ == "__main__":
    main()

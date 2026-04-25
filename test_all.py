"""
test_all.py — Health check for all three services.

Usage:
    python test_all.py

Exit code 0 if all pass, 1 if any fail.
"""

import sys
import requests

CHECKS = [
    {"name": "Webhook Receiver", "url": "http://localhost:5000/health", "pillar": "OBSERVE"},
    {"name": "AI Agent",         "url": "http://localhost:5001/health", "pillar": "ANALYZE/DECIDE"},
    {"name": "Integrations",     "url": "http://localhost:5002/health", "pillar": "ACT/COMMUNICATE"},
]


def check_service(check: dict) -> bool:
    """Return True if the service responds with HTTP 200."""
    try:
        resp = requests.get(check["url"], timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def main() -> None:
    """Run all health checks and print a summary."""
    print("\n" + "=" * 52)
    print("  AI DevOps Platform — Health Check")
    print("=" * 52)

    results = []
    for check in CHECKS:
        ok = check_service(check)
        results.append(ok)
        status = "PASS" if ok else "FAIL"
        mark   = "✓" if ok else "✗"
        print(f"  {mark} {check['name']:20s} [{check['pillar']:16s}]  {status}")

    print("=" * 52)
    all_ok = all(results)
    if all_ok:
        print("  Overall: READY — all services are healthy\n")
    else:
        failed = sum(1 for r in results if not r)
        print(f"  Overall: NOT READY — {failed} service(s) are not responding")
        print("  Run `python start_all.py` to start the platform.\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

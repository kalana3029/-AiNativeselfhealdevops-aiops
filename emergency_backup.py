"""
Emergency backup cached responses for when the Claude API is unavailable.
Used by the AI agent as a fallback to keep the demo running.
"""

CACHED_RESPONSES = {
    "MISSING_ENV_VAR": {
        "category": "MISSING_ENV_VAR",
        "confidence": 0.95,
        "action": "AUTO_FIX",
        "root_cause": "Required environment variable DATABASE_URL is not configured",
        "fix_command": "export DATABASE_URL='postgresql://localhost:5432/mydb' && pm2 restart all",
        "investigation_steps": None,
        "severity": "CRITICAL",
        "estimated_fix_time": "30 seconds",
    },
    "DEPENDENCY_CONFLICT": {
        "category": "DEPENDENCY_CONFLICT",
        "confidence": 0.91,
        "action": "CREATE_ISSUE",
        "root_cause": "urllib3 version conflict between requests and google-cloud-storage",
        "fix_command": None,
        "investigation_steps": [
            "Run `pip-compile --upgrade requirements.in` to auto-resolve dependency tree",
            "Pin urllib3 to a mutually compatible version (try urllib3>=1.26,<2.0)",
            "Test the updated requirements in a clean virtualenv before merging",
        ],
        "severity": "HIGH",
        "estimated_fix_time": "2 hours",
    },
    "FLAKY_TEST": {
        "category": "FLAKY_TEST",
        "confidence": 0.87,
        "action": "AUTO_FIX",
        "root_cause": "Intermittent external service timeout causing non-deterministic failure",
        "fix_command": "pytest tests/integration/test_payment.py --reruns 3 --reruns-delay 5 -v",
        "investigation_steps": None,
        "severity": "MEDIUM",
        "estimated_fix_time": "2 minutes",
    },
}


def get_cached_response(error_log: str) -> dict:
    """
    Pick the most appropriate cached response based on keywords in the error log.
    Defaults to MISSING_ENV_VAR if no keywords match.
    """
    log_lower = error_log.lower()

    env_keywords = ["environment variable", "env var", "not set", "undefined",
                    "environ", "cannot read property", "validateconfig"]
    dep_keywords = ["conflict", "dependency", "requirements", "version",
                    "incompatible", "pip install", "urllib", "satisfies"]
    flaky_keywords = ["flaky", "intermittent", "timeout", "retry",
                      "passed", "times in last", "503", "connection"]

    if any(kw in log_lower for kw in env_keywords):
        return CACHED_RESPONSES["MISSING_ENV_VAR"].copy()
    if any(kw in log_lower for kw in dep_keywords):
        return CACHED_RESPONSES["DEPENDENCY_CONFLICT"].copy()
    if any(kw in log_lower for kw in flaky_keywords):
        return CACHED_RESPONSES["FLAKY_TEST"].copy()

    # Default fallback
    return CACHED_RESPONSES["MISSING_ENV_VAR"].copy()

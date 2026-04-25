import requests, json

# This simulates a GitHub Actions failure webhook
failure_payload = {
    "workflow": "Production Deploy",
    "job": "deploy-to-gcp",
    "repository": "acme-corp/platform",
    "run_id": "9876543210",
    "error_log": """
    Error: DATABASE_URL environment variable is not set
    at validateConfig (/app/config.js:23:11)
    at Server.start (/app/server.js:45:3)
    Process exited with code 1
    Build failed after 2m 34s
    Deployment to production: FAILED
    """
}

try:
    response = requests.post('http://localhost:5000/webhook', 
                             json=failure_payload, timeout=5)
    print(f"Triggered: {response.json()}")
except requests.exceptions.ConnectionError:
    print("Error: Could not connect to localhost:5000. Is app.py running?")

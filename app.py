from flask import Flask, request, jsonify
import json, os, requests
from datetime import datetime

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_failure():
    payload = request.json
    print(f"Failure received: {payload}")

    # Extract the key fields judges will see
    failure_event = {
        "id": f"INC-{datetime.now().strftime('%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "pipeline": payload.get('workflow', 'CI Pipeline'),
        "stage": payload.get('job', 'build'),
        "repo": payload.get('repository', 'demo-repo'),
        "error_log": payload.get('error_log', ''),
        "status": "detected"
    }

    # Fire and forget to AI agent (Person B)
    try:
        requests.post('http://localhost:5001/analyze', 
                      json=failure_event, timeout=2)
    except requests.exceptions.RequestException as e:
        print(f"Warning: AI Agent at localhost:5001 is unreachable: {e}")

    return jsonify({"received": True, "incident_id": failure_event["id"]})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "online", "pillar": "OBSERVE"})

if __name__ == '__main__':
    # Running on port 5000 as specified for Person A
    app.run(port=5000, debug=True)

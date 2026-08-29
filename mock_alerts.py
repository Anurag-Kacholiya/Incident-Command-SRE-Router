import requests
import time
import random
import json
import hmac
import hashlib
import os

WEBHOOK_URL = "http://localhost:8000/webhook"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dummy-secret").encode()

ALERTS = [
    {"service": "auth-service", "error": "504 Gateway Timeout", "tags": ["noisy"]},
    {"service": "database", "error": "P0: OOM Killed", "tags": ["critical", "SEV1"]},
    {"service": "payment-api", "error": "ConnectionPoolTimeout", "tags": ["noisy"]},
    {"service": "frontend", "error": "JS Error: TypeError", "tags": ["noisy"]},
    {"service": "redis-cache", "error": "Connection refused", "tags": ["SEV2"]},
]

def fire_alert():
    alert = random.choice(ALERTS)
    try:
        payload_bytes = json.dumps(alert).encode()
        signature = hmac.new(WEBHOOK_SECRET, payload_bytes, hashlib.sha256).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "x-signature": signature
        }
        
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        print(f"Sent alert: {alert['error']} | Status: {response.status_code}")
    except Exception as e:
        print(f"Failed to send alert: {e}")

if __name__ == "__main__":
    print("Starting mock alert storm...")
    for _ in range(20):  # Simulate a burst of 20 alerts
        fire_alert()
        # Sleep randomly between 0.1 to 0.5 seconds to simulate an alert storm
        time.sleep(random.uniform(0.1, 0.5))
    print("Alert storm finished.")

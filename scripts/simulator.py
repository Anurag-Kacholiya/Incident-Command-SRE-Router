import requests
import time
import random
import json
import hmac
import hashlib
import os
import sys

WEBHOOK_URL = "http://localhost:8000/webhook/tenant-A"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dummy-secret").encode()

# 10 Different Mock Sources
SOURCES = [
    "aws-cloudwatch", "datadog", "sentry", "pagerduty", "gitlab-ci",
    "kubernetes", "nginx", "kafka", "redis", "custom-app"
]

def generate_noise():
    """Generates random, benign background noise logs."""
    noise_events = [
        {"service": "auth-service", "error": "Info: User login successful", "level": "INFO"},
        {"service": "billing-api", "error": "Warning: Query took 200ms", "level": "WARN"},
        {"service": "frontend", "error": "HTTP 200 OK - /home", "level": "INFO"},
        {"service": "nginx-ingress", "error": "HTTP 304 Not Modified", "level": "INFO"},
        {"service": "kafka-broker", "error": "Consumer group rebalanced", "level": "INFO"},
        {"service": "redis-cache", "error": "Memory usage at 45%", "level": "INFO"},
        {"service": "user-db", "error": "Vacuum process completed", "level": "INFO"},
        {"service": "inventory-svc", "error": "Stock sync successful", "level": "INFO"},
        {"service": "payment-api", "error": "Healthcheck passed", "level": "INFO"},
        {"service": "email-sender", "error": "Queue size: 4", "level": "INFO"},
    ]
    event = random.choice(noise_events)
    return {
        "source": random.choice(SOURCES),
        "service": event["service"],
        "error": event["error"],
        "severity": event["level"],
        "timestamp": time.time()
    }

def get_scenario_alerts(scenario_id):
    """Returns a list of critical alerts corresponding to the chosen scenario."""
    scenarios = {
        1: [ # Database OOM
            {"source": "aws-cloudwatch", "service": "user-db-node-1", "error": "P0: OOM Killed", "severity": "CRITICAL"},
            {"source": "datadog", "service": "user-db", "error": "Connection refused", "severity": "ERROR"},
            {"source": "custom-app", "service": "auth-service", "error": "500 Internal Server Error: DB connection failed", "severity": "ERROR"},
            {"source": "custom-app", "service": "billing-api", "error": "500 Internal Server Error: DB connection failed", "severity": "ERROR"},
        ],
        2: [ # Cache Stampede
            {"source": "redis", "service": "redis-cluster-main", "error": "Max memory reached, evicting keys", "severity": "WARN"},
            {"source": "pagerduty", "service": "redis-cluster-main", "error": "High latency alert > 500ms", "severity": "CRITICAL"},
            {"source": "nginx", "service": "api-gateway", "error": "504 Gateway Timeout upstream", "severity": "ERROR"},
            {"source": "sentry", "service": "frontend-app", "error": "ConnectionPoolTimeout fetching user profile", "severity": "ERROR"},
        ],
        3: [ # 3rd Party Payment Outage
            {"source": "datadog", "service": "stripe-integration", "error": "503 Service Unavailable from external API", "severity": "ERROR"},
            {"source": "sentry", "service": "billing-api", "error": "PaymentFailedException: Downstream timeout", "severity": "ERROR"},
            {"source": "custom-app", "service": "checkout-service", "error": "Cart checkout failed, returning 500", "severity": "ERROR"},
        ],
        4: [ # Bad CI/CD Deployment
            {"source": "gitlab-ci", "service": "inventory-svc", "error": "Deployment Pipeline Success", "severity": "INFO"},
            {"source": "kubernetes", "service": "inventory-svc-pod-abc", "error": "Back-off restarting failed container", "severity": "CRITICAL"},
            {"source": "kubernetes", "service": "inventory-svc-pod-abc", "error": "Liveness probe failed: HTTP 500", "severity": "ERROR"},
            {"source": "nginx", "service": "api-gateway", "error": "502 Bad Gateway - no healthy upstream", "severity": "ERROR"},
        ],
        5: [ # DNS Partition
            {"source": "kubernetes", "service": "coredns", "error": "Query timed out", "severity": "WARN"},
            {"source": "custom-app", "service": "auth-service", "error": "Name resolution failed for auth.internal", "severity": "ERROR"},
            {"source": "kafka", "service": "kafka-worker-1", "error": "Cannot connect to broker: UnknownHostException", "severity": "ERROR"},
            {"source": "sentry", "service": "email-sender", "error": "Failed to resolve SMTP server", "severity": "ERROR"},
        ]
    }
    return scenarios.get(scenario_id, [])

def fire_alert(alert_payload):
    try:
        payload_bytes = json.dumps(alert_payload).encode()
        signature = hmac.new(WEBHOOK_SECRET, payload_bytes, hashlib.sha256).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "x-signature": signature
        }
        
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        
        # Colorize output for the demo
        if alert_payload['severity'] in ["CRITICAL", "ERROR"]:
            color = "\033[91m" # Red
        elif alert_payload['severity'] == "WARN":
            color = "\033[93m" # Yellow
        else:
            color = "\033[94m" # Blue (Noise)
        reset = "\033[0m"
        
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} {color}[{alert_payload['source'][:12]:<12}] {alert_payload['service'][:18]:<18} | {alert_payload['error'][:50]}{reset}")
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

def run_simulation(scenario_id):
    if scenario_id == 0:
        print(f"\n🌊 INJECTING BACKGROUND NOISE STREAM 🌊")
    else:
        print(f"\n🌪️  INITIATING ALERT STORM FOR SCENARIO {scenario_id} 🌪️")
        
    print("="*80)
    
    incident_alerts = get_scenario_alerts(scenario_id)
    
    # We will fire a total of 150 alerts over a few seconds.
    # ~130 will be noise, ~20 will be the critical incident signals (repeated)
    total_alerts = 150
    
    for i in range(total_alerts):
        # 15% chance to fire a critical incident signal, 85% chance for noise
        if scenario_id != 0 and random.random() < 0.15:
            alert = random.choice(incident_alerts)
        else:
            alert = generate_noise()
            
        fire_alert(alert)
        time.sleep(random.uniform(0.01, 0.05)) # Fast burst
        
    print("="*80)
    print("Storm complete. Check your worker logs for the AI resolution!")

def print_menu():
    print("\n" + "#"*60)
    print("   🚨 INCIDENT COMMAND SRE ROUTER - DEMO SIMULATOR 🚨")
    print("#"*60)
    print("\nSelect a scenario to inject into the alert stream:")
    print("  [1] Primary Database OOM & Failover (SEV1)")
    print("  [5] DNS/Network Partition (SEV1/SEV2)")
    print("  [2] Cache Stampede & Gateway Timeouts (SEV2)")
    print("  [4] Bad CI/CD Deployment (CrashLoopBackOff) (SEV2)")
    print("  [3] Third-Party Payment Gateway Outage (SEV2/SEV3)")
    print("  [0] Just Background Noise (No Incidents) (SEV4)")
    print("  [q] Quit")
    print("\n" + "-"*60)

if __name__ == "__main__":
    while True:
        print_menu()
        choice = input("Enter choice: ").strip().lower()
        
        if choice == 'q':
            print("Exiting simulator.")
            sys.exit(0)
            
        if choice in ['0', '1', '2', '3', '4', '5']:
            run_simulation(int(choice))
        else:
            print("Invalid choice, please try again.")

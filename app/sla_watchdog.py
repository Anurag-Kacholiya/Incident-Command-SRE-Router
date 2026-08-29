import redis
import time
import os
from dotenv import load_dotenv
import requests

env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# SLA Definitions (in seconds for hackathon demo purposes)
SLA_THRESHOLDS = {
    "SEV1": 20,
    "SEV2": 40,
    "SEV3": 60,
    "SEV4": 120
}

def escalate_incident(incident):
    incident_id = incident['id']
    severity = incident['severity']
    
    print("\n" + "="*50)
    print(f"!!! SLA BREACH - ESCALATING !!!")
    print(f"Incident {incident_id} ({severity}) has been open for >{SLA_THRESHOLDS[severity]} seconds without acknowledgment.")
    print("="*50 + "\n")
    
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    message = f"🔥 *SLA BREACH ESCALATION* 🔥\n*Incident ID:* `{incident_id}`\n*Severity:* {severity}\nThis incident exceeded the SLA and was not acknowledged. Paging engineering leadership!"
    
    if webhook_url:
        try:
            requests.post(webhook_url, json={"text": message})
        except Exception as e:
            pass
    
    # Mark as escalated to prevent spamming
    r.hset(f"incident:{incident_id}", "acked", "escalated")

def watch_loop():
    print("SLA Watchdog started. Monitoring active incidents...")
    while True:
        # Scan for active incidents
        cursor, keys = r.scan(match="incident:*", count=100)
        for key in keys:
            incident = r.hgetall(key)
            if incident and incident.get("acked") == "false":
                created_at = float(incident.get("created_at", 0))
                severity = incident.get("severity", "SEV4")
                
                # Check if it breached SLA
                time_open = time.time() - created_at
                sla_limit = SLA_THRESHOLDS.get(severity, 300)
                
                if time_open > sla_limit:
                    escalate_incident(incident)
                    
        time.sleep(2)

if __name__ == "__main__":
    watch_loop()

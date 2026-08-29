from fastapi import FastAPI, Request, HTTPException, Header
import redis
import time
import json
import uuid
import hmac
import hashlib
import os

app = FastAPI()

# Connect to local Redis
# decode_responses=True ensures we get strings back instead of bytes
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Webhook Secret (Shared with mock_alerts.py)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dummy-secret").encode()

def verify_signature(payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.post("/webhook")
async def webhook(request: Request, x_signature: str = Header(None)):
    """
    Ingestion Layer (The API Gateway)
    Its only job is to timestamp the alert and dump it into a Message Queue.
    """
    payload_bytes = await request.body()
    
    if not verify_signature(payload_bytes, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Receive alert payload (untrusted text)
    payload = json.loads(payload_bytes)
    
    # Timestamp the alert at ingestion to start the SLA clock instantly
    alert_event = {
        "id": str(uuid.uuid4()),
        "ingestion_time": time.time(),
        "payload": payload
    }
    
    # Push incoming JSON directly into a Redis List (The Buffer)
    try:
        r.lpush("alerts", json.dumps(alert_event))
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Queue unavailable")
    
    # Return HTTP 200 OK instantly (zero synchronous processing)
    return {"status": "received", "id": alert_event["id"]}

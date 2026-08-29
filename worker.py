import redis
import time
import json
import os
from collections import defaultdict
from groq import Groq

# Connect to local Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def process_batch(alerts):
    # Dedup logic
    # We fingerprint by service and error
    fingerprints = defaultdict(int)
    has_critical = False
    
    for alert in alerts:
        payload = alert.get("payload", {})
        service = payload.get("service", "unknown")
        error = payload.get("error", "unknown")
        
        # Hard-override check
        if "P0" in error or "OOM" in error:
            has_critical = True
            
        fingerprint = f"{service}: {error}"
        fingerprints[fingerprint] += 1
        
    if not fingerprints:
        return

    print(f"Processing batch of {len(alerts)} alerts. Deduped to {len(fingerprints)} unique signatures.")

    if has_critical:
        print("CRITICAL ALERT DETECTED via hard-override. Escalate instantly (SEV1).")
        # In a real system, we'd fire off to PagerDuty/Slack here directly
    
    # Format deduped alerts for the LLM
    summary = []
    for fp, count in fingerprints.items():
        summary.append(f"[{fp}] - fired {count}x in 5s")
        
    prompt_content = "Alert batch: [" + ", ".join(summary) + "]"
    
    print("Calling LLM API...")
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an SRE AI router. Analyze the alert batch and output valid JSON only. Include an enum severity (SEV1-SEV4) and a confidence score (0.0 to 1.0)."
                },
                {
                    "role": "user",
                    "content": prompt_content
                }
            ],
            response_format={"type": "json_object"}
        )
        llm_decision = response.choices[0].message.content
        print(f"LLM Response ({time.time() - start_time:.2f}s): {llm_decision}")
        
        # Audit Log
        with open("audit_log.txt", "a") as f:
            f.write(f"--- Timestamp: {time.time()} ---\n")
            f.write(f"Prompt: {prompt_content}\n")
            f.write(f"Decision: {llm_decision}\n\n")
            
    except Exception as e:
        print(f"LLM API failed: {e}")
        # Here we would trigger the fallback router to local Qwen2.5:3B

def worker_loop():
    print("Worker started. Listening for alerts...")
    while True:
        # Block until at least one alert arrives
        item = r.brpop("alerts", timeout=0)
        if item:
            alerts = [json.loads(item[1])]
            print("Received first alert, opening 5-second window...")
            
            # Start the 5-second accumulation window
            window_start = time.time()
            while time.time() - window_start < 5.0:
                # Pop all currently available alerts without blocking
                while True:
                    next_item = r.rpop("alerts")
                    if next_item:
                        alerts.append(json.loads(next_item))
                    else:
                        break
                time.sleep(0.1) # Wait a bit before checking again in this window
                    
            # Window closed, dedup and process
            process_batch(alerts)

if __name__ == "__main__":
    worker_loop()

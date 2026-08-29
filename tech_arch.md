Here is the complete technical architecture for the **"Incident Command" SRE Router**.

Since the judges care most about "what you chose and what you deliberately rejected," we will split this into two parts: **The Production Architecture** (what you will draw and explain to the judges) and **The Hackathon MVP** (what you actually code today).

## The Production Architecture (Draw this on the whiteboard)

To make this system reliable, it must survive an **"Alert Storm"**—the exact moment a primary database fails and triggers 10,000 cascading alerts in 5 seconds. If your router crashes or gets rate-limited during an alert storm, it is worse than useless.

Here is the robust, decoupled architecture to handle that:

### 1. Ingestion Layer (The API Gateway)

* **Component:** FastAPI (Python) webhooks.
* **Role:** Exposes endpoints for CloudWatch, Datadog, and Sentry to push alerts.
* **Robustness Choice:** This layer does **zero** processing. Its only job is to acknowledge the payload (HTTP 200 OK) instantly and dump the raw JSON into a Message Queue.
* **Rejected Alternative:** Synchronous processing. If you process the alert in the API request thread, a spike in alerts will exhaust your server's connection pool and drop incoming data.

### 2. Buffer & Queue Layer (The Shock Absorber)

* **Component:** Redis Pub/Sub or RabbitMQ.
* **Role:** Holds the massive influx of alerts and feeds them to the workers at a controlled rate.
* **Robustness Choice:** Decouples ingestion from inference. If the AI model goes down or is slow, the alerts queue up safely instead of disappearing.

### 3. The Batching Engine (The Context Builder)

* **Component:** Python Async Worker with a Time-Window (e.g., 5 seconds).
* **Role:** Instead of analyzing alerts 1 by 1, this worker waits 5 seconds, groups all alerts in the queue, and packages them into a single payload.
* **Robustness Choice:** **Time-Window Batching.** This is crucial for avoiding LLM rate limits. More importantly, it gives the LLM *context*. It is much easier for an AI to realize 50 alerts are the same issue if it sees them all at once.

### 4. Stateful AI Evaluator (The Brain)

* **Component:** LLM API (Claude/OpenAI) + Redis Key-Value Store.
* **Role:** Analyzes the batch of alerts, identifies the root cause, assigns an `Urgency_Score`, and extracts granular metadata.
* **Robustness Choice 1: Stateful Memory.** The worker checks Redis for "Active Incidents." If an incident was declared 2 minutes ago, the AI is prompted: *"Is this new batch related to the ongoing Database Outage?"* This prevents sending duplicate summaries.
* **Robustness Choice 2: Hallucination Safeguards (The Bouncer).** To prevent the AI from inventing errors:
  * **Strict JSON Schema:** The LLM is forced to output a JSON object (`{"summary": "...", "confidence": 0.9, "affected_entities": ["pod-1"]}`). If the schema fails, it routes to the regex fallback.
  * **Entity Verification:** A post-generation Python script verifies that every IP or server mentioned by the LLM actually exists in the raw input alerts.
  * **Confidence Thresholds:** If the LLM's self-assigned confidence is `< 0.8`, the AI summary is dropped in favor of raw alert routing.
* **Robustness Choice 3: Payload Granularity Extraction.** To avoid losing critical details in a generic summary, the LLM extracts an `affected_entities` array. The summary provides the "what happened," while the extracted metadata preserves the "where it happened."

### 5. Fallback Router (Graceful Degradation)

* **Component:** Regex/Heuristic Rules Engine.
* **Role:** What happens if the LLM API times out or goes down?
* **Robustness Choice:** **Kill-switch fallback.** If the LLM takes longer than 3 seconds to reply, the system automatically falls back to a dumb keyword scanner (e.g., if JSON contains "FATAL" or "500", route to human).
* **Judges love this:** It proves you understand that AI is a fragile dependency and you engineered a safety net.

### 6. Delivery Layer (Actionable Notifications)

* **Component:** Slack Webhook / PagerDuty API.
* **Role:** Sends a cleanly formatted markdown summary to the engineering channel, while attaching the exact extracted metadata (IPs, Pod IDs).
* **Robustness Choice:** By delivering the summary *alongside* the exact metadata, engineers get the high-level context immediately without having to dig through raw logs to find the failing IP address.

---

## The Hackathon MVP (What to build by 3:00 PM)

You do not have time to build full Kafka clusters. Because you are on your Ubuntu machine with 16GB RAM and an RTX 3050, you can simulate this entire architecture locally using Python and Redis.

* **Install Redis:** Run `sudo apt install redis-server` or spin it up in Docker.
* **The Code Structure:**
* `mock_alerts.py`: A script that fires a mix of noisy alerts and critical alerts via `requests.post()` in a loop to simulate the firehose.
* `main.py`: A FastAPI app with one endpoint (`/webhook`). It pushes incoming JSON directly into a Redis List (`r.lpush('alerts', data)`).
* `worker.py`: An infinite loop that pops items from the Redis List in batches of 10 (`r.rpop('alerts', 10)`).
* **The AI Call:** Pass the batch of 10 to an LLM API. Instruct it: *"Read these 10 alerts. Deduplicate them. If urgency > 7, output JSON with a 1-sentence summary and a list of affected IPs/Pod IDs. If urgency < 7, output 'DROP'."*
* **The Delivery:** If the LLM outputs a summary, send the summary and the specific extracted IPs/IDs to a free Slack workspace via Webhook.



## How to Pitch the Architecture

When you present to the Signal Labs engineers, lead with the problem of **API Rate Limiting, Context Fragmentation, and AI Hallucinations**.

**Say this during your demo:**
*"The biggest point of failure in an AI-native router is treating inference synchronously. If 1,000 alerts fire, 1,000 LLM calls will trigger a rate limit, and the system fails. We architected a decoupling queue with a time-window batcher, allowing the AI to evaluate alerts in groups to establish cross-signal context. 
Furthermore, we explicitly addressed AI hallucinations. We implemented strict JSON schema enforcement, post-generation entity verification, and confidence thresholds to eliminate fake alerts. Finally, by explicitly extracting granular metadata alongside the summary, we ensure engineers get immediate context without losing the exact IP addresses they need to fix the outage. And if the LLM fails, we gracefully degrade to heuristic regex routing so a critical alert is never dropped."*

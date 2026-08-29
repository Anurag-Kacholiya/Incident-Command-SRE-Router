Here is the complete technical architecture for the **"Incident Command" SRE Router**.

Since the judges care most about "what you chose and what you deliberately rejected," we will split this into two parts: **The Production Architecture** (what you will draw and explain to the judges) and **The Hackathon MVP** (what you actually code today).

## The Production Architecture (Draw this on the whiteboard)

To make this system reliable, it must survive an **"Alert Storm"**—the exact moment a primary database fails and triggers 10,000 cascading alerts in 5 seconds. If your router crashes or gets rate-limited during an alert storm, it is worse than useless.

Here is the robust, decoupled architecture to handle that:

### 1. Ingestion Layer (The API Gateway)

* **Component:** FastAPI (Python) webhooks.
* **Role:** Exposes endpoints for CloudWatch, Datadog, and Sentry to push alerts.
* **Robustness Choice 1 (Zero-Processing):** Its only job is to **timestamp the alert** (starting the SLA clock instantly) and dump the raw JSON into a Message Queue (HTTP 200 OK).
* **Robustness Choice 2 (Multi-Tenancy):** The webhook URL requires a `tenant_id`, allowing complete logical isolation of customer data throughout the entire pipeline.
* **Security Choice:** Webhook payloads are verified using SHA-256 HMAC signatures. Alert content is explicitly delimited as inert data (XML tags) to prevent prompt injection.
* **Interactive Choice (The ACK Loop):** Exposes a `/slack/events` webhook that listens for ✅ reactions in Slack to automatically acknowledge incidents and stop the SLA Watchdog.

### 2. Buffer & Queue Layer (The Shock Absorber)

* **Component:** Redis Streams.
* **Role:** Holds the massive influx of alerts and feeds them to the workers at a controlled rate.
* **Robustness Choice:** Decouples ingestion from inference. If the AI model goes down, the alerts queue safely. 
* **Reliability Choice (Crash-Safety):** We deliberately reject Redis Pub/Sub (fire-and-forget) and basic `RPOP` (which drops messages on a worker crash). Instead, we explicitly use Redis Streams with Consumer Groups (`XADD`, `XREADGROUP`). Messages are only removed from the queue after the worker explicitly confirms completion via `XACK`—guaranteeing **at-least-once delivery**.

### 3. The Batching Engine (The Context Builder)

* **Component:** Python Async Worker with a Time-Window (e.g., 5 seconds).
* **Role:** Groups all alerts in the queue over a 5-second window.
* **Robustness Choice:** **Dedup/fingerprinting before the LLM.** Instead of feeding 50 near-identical blobs to the LLM, we hash on `(service, error signature)`, collapse repeats, and pass counts ("fired 47× in 5s") as context. This cuts LLM calls and provides cleaner signal.

### 4. Stateful AI Evaluator (The Brain)

* **Component:** LLM API (Claude/OpenAI) + Redis Key-Value Store.
* **Role:** Analyzes the batch of alerts, maps them to SLA buckets (e.g., SEV1 ≤ 5 min, SEV2 ≤ 30 min), and extracts metadata.
* **Architecture Rules:**
  * **PII Redaction:** Before any data leaves our infrastructure, a scrubbing layer automatically strips emails, IP addresses, and API keys from the error traces.
  * **No Unilateral DROP Authority:** The LLM's classification is superseded by a deterministic allowlist. Known-critical tags (`P0`/`OOM`) bypass the LLM drop completely and force-escalate. 
  * **Structured Output, Confidence & Noise Filtering:** The LLM outputs a strict JSON schema with an enum severity, numeric confidence score, and an `is_noise` boolean flag. If `is_noise` is true (and no critical override exists), the batch is safely dropped. **Low confidence ALWAYS means escalate.** 
  * **Grounding & Verification:** The LLM must cite actual alert IDs from the batch, which we cheaply verify exist in the input to catch hallucinated root causes.
  * **Double-Pass Validation:** If the LLM returns a borderline `SEV3` with high confidence, the system automatically triggers a strict, secondary re-evaluation. If the second pass believes it should be `SEV1/SEV2`, the system upgrades the severity to err on the side of caution.
  * **Multi-Tenancy:** All processing and Redis states are **scoped by tenant ID** ensuring logical isolation.
  * **Audit Log:** A full decision audit log (input XML, response JSON, decision) is recorded for every batch to ensure complete explainability.

### 5. Fallback Router (Graceful Degradation)

* **Component:** Regex Fallback Engine + Deterministic Allowlist.
* **Role:** What happens if the primary LLM API times out or goes down?
* **Robustness Choice 1 (Circuit Breaker):** If the LLM throws an exception or times out, we catch it instantly and route to a fallback engine so the alerts are never dropped.
* **Robustness Choice 2 (Regex Scanner):** We downgrade to a robust regex keyword scanner. It scans the deduplicated fingerprints for critical terms (`fatal|5xx|exception|timeout|error`). If any match is found, it artificially escalates the incident to `SEV2`, ensuring engineers are paged even when the AI brain is completely offline.

### 6. Delivery Layer & SLA Watchdog (Actionable Notifications)

* **Component:** Slack Webhook / PagerDuty API + Separate SLA Watchdog.
* **Role:** Delivers the summary, and enforces response times.
* **Robustness Choice:** **SLA Watchdog Loop.** The LLM only classifies severity; a separate, small watchdog reads open-incident timestamps in Redis and enforces the SLA. If no explicit human acknowledgment (e.g., Slack button click) occurs within the window, it automatically pages the next person up. This ensures alerts don't just "sit in Slack unread."

---

### 7. Capacity & Rate Limiting Math (Surviving the Storm)

To prove this architecture works during a major outage:
* **The Scenario:** A primary DB failure triggers 10,000 cascading alerts across 50 microservices within a 5-second window.
* **The Math:** 
  - 10,000 raw alerts hit the API Gateway (2,000 req/sec) and are instantly buffered into Redis.
  - The Batching Engine consumes them over a single 5-second window.
  - Deduplication hashes them into ~50 unique fingerprints (e.g., `auth-service: 504 Gateway Timeout`).
  - Instead of 10,000 LLM calls, the Router makes exactly **1 LLM call** containing 50 fingerprints with their aggregated counts.
  - This keeps API usage well below OpenAI/Claude rate limits (e.g., 500 RPM / 10,000 TPM) while preserving the full context of the outage.

---

## The Hackathon MVP (What was built)

Because you do not have time to build full Kafka clusters, this architecture was simulated locally using Python and Redis, achieving production-grade resilience.

* **The Code Structure:**
  * `simulator.py`: An interactive CLI that fires a mix of noisy alerts and complex incident scenarios via `requests.post()` to simulate the firehose.
  * `app/main.py`: A FastAPI app providing the ingestion webhook (with HMAC security and multi-tenancy) and a `/slack/events` callback for incident acknowledgment. It pushes JSON safely into Redis Streams (`XADD`).
  * `app/worker.py`: An infinite loop that consumes from the Stream via `XREADGROUP`, performs 5-second time-window deduplication, applies PII redaction, runs the Groq LLM validation (with Double-Pass and Noise filtering logic), and finally issues an `XACK` for crash-safety.
  * `app/sla_watchdog.py`: An independent process that continuously scans Redis for active incidents that have not been acknowledged by humans in time, escalating them via Slack webhooks.
* **The Brain Logic:**
  * Hard-override keyword bypass (if "P0" or "OOM" is in the batch, escalate instantly).
  * Confidence threshold enforcement (`< 0.8` forces `SEV1`).
  * Regex fallback engine if the LLM API fails.
  * Comprehensive plain-text audit logging.

## How to Pitch the Architecture

When you present to the Signal Labs engineers, lead with the problem of **API Rate Limiting, AI Hallucinations, and Silent Failures**.

**Say this during your demo:**
*"The biggest point of failure in an AI-native router is treating inference synchronously. We architected a decoupling queue using Redis Streams for at-least-once delivery via XACK, with a time-window batcher allowing the AI to establish cross-signal context.*

*More importantly, we built multiple safety nets around the AI. Before hitting the LLM, payloads are scrubbed of PII. We never give the LLM unilateral drop authority without a hard-override bypass. We enforce JSON schemas, perform post-generation hallucination checks, and even trigger a 'Double-Pass' re-evaluation on borderline severities. We also implemented an interactive Slack ACK loop to stop our independent SLA Watchdog.*

*Finally, if the LLM API ever fails, our circuit breaker instantly catches the exception and gracefully degrades to a robust Regex Fallback Engine, ensuring critical alerts are escalated even when the AI brain is completely offline."*

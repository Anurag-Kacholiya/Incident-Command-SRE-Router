# System Analysis: Incident Command SRE Router

## 1. System Overview
The Incident Command SRE Router is an AI-driven, multi-tenant alert aggregation and routing platform. It ingests raw telemetry and alerts from various monitoring sources (Datadog, AWS Cloudwatch, Sentry, Kubernetes, etc.), deduplicates them, analyzes the payload using a Large Language Model (LLM) to determine severity, and orchestrates incident escalation via Slack. It is backed by an independent, asynchronous Redis-based SLA watchdog that guarantees critical incidents are acknowledged within strict time limits.

---

## 2. Key Design Choices & Rationale

### A. Decoupled Architecture (Gateway vs. Worker)
- **Choice**: Using FastAPI exclusively as an ingestion buffer (`app/main.py`) and offloading heavy processing to a background worker (`app/worker.py`).
- **Why**: Alert storms (e.g., cascading microservice failures) can generate hundreds of POST requests per second. Synchronously processing these, calling an LLM, and waiting for HTTP responses would immediately bottleneck and crash the API Gateway. By instantly acknowledging the payload and dropping it into a Redis Stream, the API can scale independently and handle massive throughput without dropping a single alert.

### B. Redis Streams for Message Queueing
- **Choice**: Using `XADD` and `XREADGROUP` instead of generic lists (`LPUSH`/`RPOP`).
- **Why**: Standard lists don't provide crash safety. If the worker crashed mid-processing, the popped alerts would be lost forever. Redis Consumer Groups require explicit acknowledgment (`XACK`). If the worker crashes, the unacknowledged messages remain in the stream's Pending Entries List (PEL) and can be safely recovered by another worker, guaranteeing at-least-once delivery.

### C. Time-Boxed Accumulation Windows
- **Choice**: The worker blocks on the stream until an alert arrives, then opens a 5-second accumulation window before processing.
- **Why**: Systems rarely fail cleanly with a single alert; they fail loudly and generate localized alert storms. By waiting 5 seconds, the system captures the context of the entire failure (e.g., DB OOM + Gateway Timeout + Pod Crash) and submits it to the LLM as a single, compressed batch. This drastically improves the AI's contextual awareness and reduces API costs.

### D. Multi-Tiered Routing with Fallbacks
- **Choice**: Implementing deterministic hard-overrides (e.g., keywords like `P0` or `OOM`) and a robust Regex fallback engine.
- **Why**: LLMs can hallucinate, experience high latency, or the API provider can experience an outage. An SRE tool cannot fail silently. The hard-overrides ensure critical keywords bypass AI evaluation altogether, and the Regex Fallback Engine acts as a circuit breaker. If the LLM API throws an exception, the system relies on traditional regex to categorize the alerts, ensuring zero dropped signals.

### E. Asynchronous SLA Watchdog
- **Choice**: Running the SLA monitor (`app/sla_watchdog.py`) as a completely independent loop rather than scheduling async tasks within the worker.
- **Why**: Separation of concerns. If the LLM worker gets blocked, hits rate limits, or crashes, the watchdog keeps ticking because it relies entirely on the Redis state (`incident:*` hashes). It ensures that even if ingestion goes down entirely, existing open incidents will still successfully escalate.

---

## 3. Potential Failure Points (Where it might fail)

### 1. Redis Memory Exhaustion
- **Risk**: Currently, all incoming alerts are dumped into `alerts_stream`, and incident hashes stay in Redis indefinitely (there is no TTL or archive mechanism). During a massive, prolonged alert storm, Redis could run out of memory (OOM) and crash.
- **Mitigation**: Implement `MAXLEN` on the `XADD` command to cap the stream size, and set TTLs (Time to Live) on old incident hashes once they are resolved.

### 2. Single Point of Failure: The Worker Process
- **Risk**: The system currently assumes a single worker process (`worker-1`). If the rate of alerts significantly exceeds the LLM processing speed, the stream backlog will grow indefinitely.
- **Mitigation**: Deploy multiple worker processes scaling horizontally. Redis consumer groups handle this natively, allowing multiple workers to pull unique messages from the same stream, but deployment orchestration (like Kubernetes HPA) is required to manage this.

### 3. Context Window Limits
- **Risk**: If the 5-second window captures thousands of unique alert fingerprints (e.g., highly variable dynamic error strings that bypass deduplication), formatting them into XML might exceed the LLM's token context limit. This would cause the API call to fail and force the system into the regex fallback.
- **Mitigation**: Implement truncation, strict limits, or semantic chunking of the alert batch before sending it to the Groq API.

### 4. Slack API Rate Limiting
- **Risk**: If the SLA watchdog trips for many incidents simultaneously, or a massive storm generates numerous SEV1s, the system might trigger Slack's strict webhook rate limits (typically 1 request per second), causing critical notifications to be dropped.
- **Mitigation**: Implement a rate-limited queue or exponential backoff specifically for Slack notifications.

---

## 4. Future Scope of Improvement

1. **Auto-Remediation & Runbooks**: 
   Integrate outbound webhooks to trigger automatic rollback scripts, halt CI/CD pipelines, or restart Kubernetes pods based on the LLM's classification and confidence score.
   
2. **Alert Archiving & Analytics**: 
   Move resolved incidents from Redis into a persistent relational database (like PostgreSQL) for historical reporting. This would allow the team to calculate MTTA (Mean Time To Acknowledge) and MTTR (Mean Time To Resolve) metrics over time.
   
3. **Advanced PII Scrubbing**: 
   Replace the current regex-based PII scrubber with a local, lightweight NLP model (like Microsoft Presidio) to catch complex, dynamic secrets and PII before they ever hit the cloud LLM.
   
4. **Slack Interactivity (Block Kit)**: 
   Enhance the `/slack/events` integration to use Slack's Block Kit. Allow engineers to not only acknowledge incidents but also assign them to specific users, manually update severity, or resolve them entirely from the Slack UI.
   
5. **Contextual RAG Retrieval**: 
   When evaluating an alert, the worker could use Retrieval-Augmented Generation (RAG) to pull past incident post-mortems from Confluence/Jira and attach them to the prompt. This would allow the LLM to conclude: *"This looks exactly like the SEV1 we had last month, attaching runbook X."*

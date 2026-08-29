# Incident Command SRE Router - Architecture

Based on the updated `tech_arch.md` that was pulled, here is the visual representation of your robust, decoupled architecture.

```mermaid
flowchart TD
    %% 1. Ingestion Layer
    subgraph Ingestion ["1. Ingestion Layer"]
        Sources["Alert Sources"]
        API["FastAPI Gateway\n(Multi-Tenant)"]
        SlackEvent["Slack /events\n(✅ Reaction)"]
        
        Sources -- "Untrusted JSON" --> API
    end

    %% 2. Buffer & Queue Layer
    subgraph QueueLayer ["2. Buffer & Queue Layer"]
        Queue[("Redis Streams\n(XADD / XREADGROUP)")]
        API -- "Dump Payload" --> Queue
    end

    %% 3. Batching Engine
    subgraph BatchingLayer ["3. Batching Engine"]
        Worker["Python Async Worker\n(5s Time-Window)"]
        Dedup["Dedup & Fingerprinting\nHash: (service, error)"]
        
        Queue -- "Pull & Process" --> Worker
        Worker --> Dedup
    end

    %% 4. AI Evaluator & 5. Fallback Router
    subgraph IntelligenceLayer ["4. Brain & 5. Fallback"]
        PII["PII Redaction Scrub"]
        Rules{"Deterministic Allowlist"}
        CircuitBreaker{"Circuit Breaker"}
        
        LLM["Primary LLM\n(Noise Filter & Double-Pass)"]
        RegexFallback["Regex Fallback Engine"]
        
        StateStore[("Redis KV Store\n(Tenant Isolated)")]
        AuditLog[("Audit Log")]
        
        Dedup --> PII
        PII --> Rules
        Rules -- "Needs AI Evaluation" --> CircuitBreaker
        
        CircuitBreaker -- "Healthy" --> LLM
        CircuitBreaker -- "Exception / Timeout" --> RegexFallback
        
        LLM -- "Read/Write State" --> StateStore
        RegexFallback -- "Read/Write State" --> StateStore
        
        LLM -.-> AuditLog
        RegexFallback -.-> AuditLog
    end

    %% 6. Delivery & Watchdog
    subgraph DeliveryLayer ["6. Delivery & Watchdog"]
        DeliveryAPI["Slack Webhooks"]
        Watchdog["SLA Watchdog Loop"]
        
        Rules -- "Force Escalate" --> DeliveryAPI
        LLM -- "Escalate" --> DeliveryAPI
        RegexFallback -- "Escalate" --> DeliveryAPI
        
        StateStore -. "Poll Unacknowledged" .-> Watchdog
        Watchdog -- "SLA Breach" --> DeliveryAPI
        SlackEvent -- "ACK Incident" --> StateStore
    end
    
    %% Worker XACK completion
    DeliveryAPI -. "Complete" .-> XACK(("XACK Queue"))
    XACK -.-> Queue
```

### Key Highlights Visualized:
- **Interactive ACK Loop**: The `Delivery API` sends the alert to Slack, and if an engineer reacts with a ✅, the `Slack /events` webhook receives it and acknowledges the incident in Redis—stopping the `SLA Watchdog` from paging the next person.
- **Robust Queueing**: The pipeline leverages `Redis Streams`. Messages are consumed via `XREADGROUP` and only marked as complete (`XACK`) after the LLM or Fallback engine successfully processes them, ensuring true crash-safety.
- **The Brain's Safety Nets**: Before any LLM is called, data is passed through `PII Redaction`, and then the `Deterministic Allowlist` checks for known severe incidents (like P0 or OOM) to force-escalate them immediately.
- **Circuit Breaker Pattern**: If the primary LLM API times out, the `Circuit Breaker` catches it and routes the batch to a `Regex Fallback Engine` to guarantee alerts are never dropped.

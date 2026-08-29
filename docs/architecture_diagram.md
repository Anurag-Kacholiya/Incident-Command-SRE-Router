# Incident Command SRE Router - Architecture

Based on the updated `tech_arch.md` that was pulled, here is the visual representation of your robust, decoupled architecture.

```mermaid
flowchart TD
    %% 1. Ingestion Layer
    subgraph Ingestion ["1. Ingestion Layer"]
        Sources["CloudWatch / Datadog / Sentry"]
        API["FastAPI Webhook Gateway\n(Timestamp & Ack)"]
        Sources -- "Untrusted JSON" --> API
    end

    %% 2. Buffer & Queue Layer
    subgraph QueueLayer ["2. Buffer & Queue Layer"]
        Queue[("RabbitMQ / Redis Streams\n(At-least-once delivery)")]
        API -- "Dump Payload" --> Queue
    end

    %% 3. Batching Engine
    subgraph BatchingLayer ["3. Batching Engine"]
        Worker["Python Async Worker\n(5s Time-Window)"]
        Dedup["Dedup & Fingerprinting\nHash: (service, error)"]
        Queue -- "XREADGROUP / RPOPLPUSH" --> Worker
        Worker --> Dedup
    end

    %% 4. AI Evaluator & 5. Fallback Router
    subgraph IntelligenceLayer ["4. Evaluator & 5. Fallback Router"]
        Rules{"Deterministic Allowlist\n(P0 / OOM / SEV1)"}
        CircuitBreaker{"Circuit Breaker"}
        
        LLM["Primary LLM API\n(Structured JSON & Confidence)"]
        LocalFallback["Local Quantized Model\n(Qwen2.5:3B)"]
        
        StateStore[("Redis KV Store\n(Stateful Memory)")]
        AuditLog[("Audit Log\n(Decisions)")]
        
        Dedup --> Rules
        Rules -- "Needs AI Evaluation" --> CircuitBreaker
        
        CircuitBreaker -- "Healthy" --> LLM
        CircuitBreaker -- "Timeout/Down" --> LocalFallback
        
        LLM <--> |"Check/Update Incidents"| StateStore
        LocalFallback <--> StateStore
        
        LLM -.-> AuditLog
        LocalFallback -.-> AuditLog
    end

    %% 6. Delivery & Watchdog
    subgraph DeliveryLayer ["6. Delivery & Watchdog"]
        DeliveryAPI["Slack / PagerDuty Webhooks"]
        Watchdog["SLA Watchdog Loop"]
        
        Rules -- "Force Escalate (Bypass AI)" --> DeliveryAPI
        LLM -- "Severity Classification\nor Low Confidence" --> DeliveryAPI
        LocalFallback -- "Classification" --> DeliveryAPI
        
        StateStore -.-> |"Poll Open SLA Timers"| Watchdog
        Watchdog -- "SLA Breach Escalate" --> DeliveryAPI
    end
```

### Key Highlights Visualized:
- **Decoupled Architecture**: Notice how the `FastAPI Webhook Gateway` drops data directly into `RabbitMQ / Redis Streams` and returns a 200 OK, completely isolating ingestion traffic from processing latency.
- **The Brain's Safety Net**: Before any LLM is called, the `Deterministic Allowlist` checks for known severe incidents (like P0 or OOM) and force-escalates them immediately.
- **Circuit Breaker Pattern**: If the primary LLM API times out, the `Circuit Breaker` catches it and routes the batch to the `Local Quantized Model` to ensure smart routing even offline.
- **The SLA Watchdog**: Operating completely independently of the AI inference, the `Watchdog` constantly polls the Redis state store to escalate any incidents that breach SLA timeframes.

# Incident Command SRE Router

An AI-powered Site Reliability Engineering (SRE) incident router and SLA watchdog. This system ingests alerts, deduplicates them in real-time, uses a Large Language Model (via Groq) to evaluate incident severity, and monitors response SLAs to automatically escalate unacknowledged incidents.

## Architecture

The system consists of three main components:

1. **Ingestion Layer (`app/main.py`)**: 
   A blazing fast FastAPI webhook endpoint that acts as the API Gateway. It validates incoming payloads using HMAC signatures, timestamps the alerts (to start the SLA clock instantly), and pushes them to a Redis message queue. It returns an HTTP 200 OK immediately with zero synchronous processing.

2. **Batching Engine & LLM Router (`app/worker.py`)**: 
   A background worker that pulls from the Redis queue using a 5-second accumulation window. It deduplicates alerts based on their signature (service + error) and formats them as XML. It then uses an LLM (via the Groq API) to determine the severity (SEV1-SEV4), summarize the outage, and measure confidence. 
   - **Hard Overrides**: Automatically escalates "P0" or "OOM" errors to SEV1.
   - **Grounding Validation**: Ensures the LLM cites actual alert IDs.
   - **Delivery**: Declares incidents in Redis and fires a Slack notification.
   - **Auditing**: Logs all LLM inputs, raw outputs, and final decisions to `audit_log.txt`.

3. **SLA Watchdog (`app/sla_watchdog.py`)**: 
   A continuous monitoring loop that watches active incidents in Redis. If an incident remains unacknowledged (`acked: "false"`) beyond its severity-based SLA threshold, the watchdog automatically escalates it by paging engineering leadership via Slack.

## Prerequisites

- Python 3.8+
- Redis (running locally on default port 6379)

## Setup

1. **Install Dependencies**:
   ```bash
   pip install fastapi uvicorn redis groq python-dotenv requests
   ```

2. **Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   WEBHOOK_SECRET=dummy-secret
   SLACK_WEBHOOK_URL=your_slack_webhook_url_here  # Optional: For actual Slack notifications
   ```

## Running the Application

You will need to run the components in separate terminal windows/tabs:

1. **Start Redis Server**:
   ```bash
   redis-server
   ```

2. **Start the API Gateway**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

3. **Start the Background Worker**:
   ```bash
   python app/worker.py
   ```

4. **Start the SLA Watchdog**:
   ```bash
   python app/sla_watchdog.py
   ```

## Testing

You can simulate an alert storm to test the deduplication and AI routing logic.

```bash
python scripts/simulator.py
```

This interactive script will let you choose different disaster scenarios and inject them into the alert stream alongside background noise. Watch the worker logs to see how it dedups and handles the incident!

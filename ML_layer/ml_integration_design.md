# Integrating Traditional ML for Hallucination Reduction and XAI

Integrating a traditional, trained Machine Learning (ML) model into the Incident Command SRE Router is an excellent strategy. It provides a grounded, data-backed signal that anchors the LLM, significantly reducing the chance of hallucination while introducing an element of Explainable AI (XAI).

Here is a detailed brainstorm on how to design, train, and integrate this ML layer into your existing architecture.

## 1. Where It Fits in the Architecture

The ML model should sit right between the **Batching/Dedup Engine (Step 3)** and the **Stateful AI Evaluator (Step 4)**.

**New Flow:**
1. Raw Alerts → API Gateway → Message Queue → Batching/Dedup Engine
2. **[NEW] ML Feature Extraction & Ranking:** The deduped alert batch is passed through a lightweight ML classifier.
3. LLM Evaluator: The LLM receives the alerts **plus** the ML model's prediction, confidence score, and explainability factors.

## 2. The ML Model Design (What & How)

Because this needs to run fast and be highly explainable, you should avoid deep learning here and stick to robust, traditional ML models.

### Recommended Algorithms
* **XGBoost or LightGBM:** Excellent for tabular data and highly explainable.
* **Random Forest:** Very robust against overfitting and easy to explain.
* **Logistic Regression:** If you need extreme speed and a pure probabilistic output.

### Feature Engineering (The Input)
You will train the model on historical incident data. Features extracted from incoming alerts could include:
* **Categorical:** `service_name`, `environment` (prod/staging), `error_code` (500, 502, 504), `alert_source` (Datadog, Sentry).
* **Numerical:** `alert_frequency_in_5s_window`, `time_of_day`, `day_of_week`.
* **Textual (Lightweight):** TF-IDF vectors or fastText embeddings of the `error_message` or `stack_trace_snippet`.
* **Historical Context:** `time_since_last_similar_alert`.

### The Output
The ML model outputs:
1. **Severity Probability Distribution:** e.g., `[P0: 5%, P1: 80%, P2: 10%, P3: 5%]`
2. **Top Features (XAI):** The features that contributed most to this specific prediction.

## 3. How This Reduces LLM Hallucinations

LLMs hallucinate when they try to infer rules that don't exist or when they lack concrete context. By providing the ML output *within the prompt*, you ground the LLM's reasoning.

**Example LLM Prompt with ML Context:**
```text
You are an SRE Assistant evaluating a batch of alerts.

<alerts>
[Service: auth-service, Error: 504 Gateway Timeout, Count: 47]
</alerts>

<ml_context>
Our internal historical ML model predicts this is a P1 (80% confidence). 
Explainability (Top contributing factors): 
1. "Count > 40 in 5s" (High impact)
2. "Service: auth-service" (Medium impact)
</ml_context>

Task: Based on the alerts and the ML context, provide a final severity classification and a human-readable summary. If you disagree with the ML model, explicitly state why.
```
*Result:* The LLM now acts as a *reviewer* of a statistical prediction rather than starting from scratch. It is far less likely to hallucinate a "P4 - low priority" when grounded with the ML's 80% P1 prediction.

## 4. Explainable AI (XAI) Aspect

Judges love XAI. You can use **SHAP (SHapley Additive exPlanations)** or **LIME** (Local Interpretable Model-agnostic Explanations) alongside your XGBoost model. 

When the system routes an alert to Slack, the message can look like this:

> 🚨 **SEV1: auth-service is failing**
> **AI Summary:** 47 Gateway Timeouts detected in the last 5 seconds.
> 
> 🧠 **ML Routing Rationale (Confidence 85%):**
> ⬆️ Alert volume spiked >500% above baseline
> ⬆️ 'auth-service' has high historical correlation with SEV1s
> ⬇️ Time of day is non-peak (reduced severity weight)

This transparency builds trust with SREs—they know *why* the AI escalated it.

## 5. Implementation for the Hackathon MVP

To build this quickly for the hackathon while impressing the judges with real data:
1. **The Dataset:** Download the open-source **"Incident Management Process Enriched Event Log"** from the UCI Machine Learning Repository (which contains real ServiceNow tickets).
2. **The Model:** Train a `scikit-learn` Random Forest Classifier using a quick python script (`train_real_data.py`) on real features like `category`, `subcategory`, and `u_symptom` to predict the priority. Export this as a `.pkl` file.
3. **The Router Integration:** In your `worker.py`, load the `.pkl` file. Before calling the LLM, pass the batch properties to the model, get the `predict()`, and extract the top feature importances using `model.feature_importances_`.
4. **The Prompt:** Append the prediction and top features to the prompt sent to the LLM.

## 6. Bonus: The "Fast Track" Circuit Breaker
If the ML model predicts SEV1 with >95% confidence, you can **bypass the LLM entirely** and escalate immediately. The LLM can then be run asynchronously just to generate the readable summary, ensuring zero delay in paging the on-call engineer for obvious critical issues.

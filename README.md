# Tiered Verdict Engine — Fact Knowledge Layer

A resilient, two-tier AI system that extracts meaningful facts from PDFs, grounds them in explicit source evidence, and discovers cross-document relationships (corroborations, contradictions, and contextual reconciliations).

Built for the **Superjoin VIT 2026 Engineering Intern Assignment**.

## Setup and Run Instructions

### Prerequisites
- Docker & Docker Compose (for PostgreSQL + `pgvector`)
- Python 3.10+
- Google API Key (for Gemini)

### Quick Start

1. **Configure Environment:**
   Copy the example environment file and add your Google API key.
   ```bash
   cp .env.example .env
   ```
   *(Ensure `GEMINI_MODEL=gemini-3.7-flash` is set inside `.env`)*

2. **Start the Vector Database:**
   ```bash
   docker-compose up -d
   ```

3. **Install Dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Run the FastAPI Backend (API Requirement):**
   ```bash
   uvicorn app.api:app --reload --port 8000
   ```

5. **Run the Streamlit Frontend (UI Requirement):**
   *(In a new terminal window)*
   ```bash
   source venv/bin/activate
   streamlit run app/ui.py
   ```

---

## Approach and Architecture

This pipeline is built for high precision and resilience against API limits:

1. **Page-Aware Extraction**: PDFs are chunked at 4000 characters to preserve context while minimizing LLM round-trips.
2. **Fuzzy Ingestion Gate**: Before touching the database, every LLM-extracted claim is validated against the raw document text using `thefuzz`. Hallucinated quotes (<85% match) are rejected and logged.
3. **Matryoshka Vector Search**: Uses `gemini-embedding-001` natively truncated to 768 dimensions, stored in `pgvector`. This reduces storage while perfectly supporting rapid semantic similarity lookups. Embeddings are batched per-chunk for maximum speed.
4. **Tier 1 (Deterministic Fast Filter)**: Uses pure regex/heuristics to dynamically detect time scope differences (e.g., Q1 vs Q2, FY23 vs FY24) and numeric deltas. It is completely independent of hardcoded document rules.
5. **Tier 2 (LLM Reasoning)**: Gemini evaluates candidate pairs that pass Tier 1, classifying them and explicitly citing the quotes used in its reasoning.
6. **Resiliency Engine**: Custom exponential backoff wrappers seamlessly handle Google's strict 15 RPM free-tier rate limits, combined with incremental per-chunk database commits so partial document progress is never lost on a crash.

---

## Trade-Offs

- **Chunk Size vs. Resolution**: Increased the chunk size to 4000 characters. *Trade-off*: Drastically reduces the number of expensive LLM API calls and latency, but risks burying tiny, isolated facts deep in the context window.
- **API vs. Local Models**: Chose Gemini API for its superior semantic reasoning and JSON output structuring. *Trade-off*: Subject to strict free-tier rate limits (15 RPM), which necessitated building a robust exponential backoff handler rather than running instantly.
- **Deterministic vs. Semantic Filtering**: Tier 1 uses rigid regex for time/number comparisons to save API calls. *Trade-off*: Ultra-fast, but lacks the nuanced linguistic understanding that a pure LLM approach would have for complex edge cases.

---

## The Four Required Cases Demonstrated

1. **Corroboration (Semantic & Mathematical Equivalence)**
   - *Behavior:* The system identifies that two differently phrased facts actually mean the same thing.
   - *Example Achieved:* The engine successfully proved that `"500 Crore INR"` from Document A was mathematically identical to `"5,000 million Indian Rupees"` from Document B, citing the exact source quotes.

2. **Contradiction (Genuine Conflict)**
   - *Behavior:* Detects mutually exclusive claims that cannot be resolved.
   - *Example Achieved:* Identified a strict conflict where Fact A stated "Mr. Ravi Kumar" is the current CFO, while Fact B stated he was succeeded by "Ms. Anjali Mehta", flagging the direct contradiction in personnel.

3. **Reconciled Context (Resolving Apparent Conflicts)**
   - *Behavior:* Recognizes when numbers differ for a valid, explainable reason.
   - *Example Achieved:* Extracted revenue numbers of 500 Crore and 430 Crore. The Tier 1 deterministic filter parsed the temporal qualifiers (`FY24` vs `FY23`) via dynamic regex. Tier 2 then successfully flagged this as `Reconciled` because the time context explains the delta.

4. **Failure / Audit Handling**
   - *Extraction Failures:* If the LLM generates a claim but the exact quote doesn't fuzzy-match the source chunk (e.g., the LLM hallucinates a number), the Ingestion Gate blocks it from the Knowledge Base and logs it to the Audit table.
   - *System Failures:* If the API hits a 429 Rate Limit, the system logs the exhaustion and gracefully applies exponential backoff (`time.sleep(wait)`) instead of crashing the application.

---

## Limitations and Next Steps

1. **Sequential Blocking UI**: Currently, extraction blocks the Streamlit frontend. 
   - *Next Step*: Move the extraction loop to a background worker queue (Celery/Redis) with WebSockets for real-time progress updates.
2. **Heuristic Constraints**: Tier 1 flags unit mismatches but leaves explicit currency/metric conversions (e.g., converting USD to INR via historical exchange rates) to the LLM. 
   - *Next Step*: Integrate a deterministic unit-conversion microservice into Tier 1.
3. **API Dependency**: Completely dependent on Google's remote API uptime.
   - *Next Step*: Implement an abstract LLM interface to allow seamless failover to local offline models (like `Llama-3` via Ollama) when the network is down.

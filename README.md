# Tiered Verdict Engine — Fact Knowledge Layer

A system that extracts meaningful facts from PDFs, grounds them in explicit source evidence,
and discovers cross-document relationships (corroborations, contradictions, and contextual reconciliations).

Built for the **Superjoin VIT 2026 Engineering Intern Assignment**.

## Setup and Run Instructions

### Prerequisites
- Docker & Docker Compose (for PostgreSQL + pgvector)
- Python 3.10+
- Google API Key (for Gemini)

### Quick Start

1. Copy `.env.example` to `.env` and add your API key:
   ```bash
   cp .env.example .env
   # Edit .env with your GOOGLE_API_KEY
   ```

2. Start the database:
   ```bash
   docker-compose up -d
   ```

3. Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Run the API (required by assignment):
   ```bash
   uvicorn app.api:app --reload --port 8000
   ```

5. Run the UI (in a new terminal):
   ```bash
   streamlit run app/ui.py
   ```

## Architecture: Tiered Verdict Engine

1. **Extraction (Page-Aware Chunking)**
PDFs are split with strict page-level lineage. The LLM extracts claims into a fully agnostic schema: Subject-Predicate-Object + Qualifiers. Extraction confidence is tracked.

2. **Ingestion Verifier Gate**
Before saving, a fuzzy-matching gate verifies the `source_quote` exists in the raw chunk. Grounding failures and low-confidence extractions are logged to `failure_logs`.

3. **Diversity Vector Search**
pgvector retrieves Top-K similar claims, deliberately mixing cross-document and intra-document candidates to combat proximity bias.

4. **Tier 1: Deterministic Fast Filter**
Rejects or flags pairs based on structural mismatches:
- Unit mismatches (Cr vs Mn, USD vs INR)
- Time scope non-overlaps (FY24 vs FY23)
- Numeric deltas above threshold
- Categorical contradictions

5. **Tier 2: LLM Verdict + Evidence Verification**
Surviving pairs go to Gemini Pro for semantic reasoning. The LLM must cite evidence quotes, which are then deterministically verified against source text via fuzzy matching. This catches hallucinated reasoning on real sources.

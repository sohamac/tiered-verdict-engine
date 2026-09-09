# Tiered Verdict Engine - Fact Knowledge Layer

A system that extracts meaningful facts from PDFs, grounds them in explicit source evidence, and discovers cross-document or intra-document relationships (corroborations, contradictions, and contextual reconciliations).

## Setup and Run Instructions

### Prerequisites
- Docker & Docker Compose (for the PostgreSQL + pgvector database)
- Python 3.10+
- OpenAI API Key (or equivalent LLM configuration)

### Quick Start
1. Rename `.env.example` to `.env` and insert your API keys.
2. Spin up the local database (PostgreSQL with pgvector):
   ```bash
   docker-compose up -d
   ```
3. Create a virtual environment and install the requirements:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run the UI:
   ```bash
   streamlit run app/ui.py
   ```

## Approach

This system implements a **Tiered Verdict Engine** architecture optimized to prevent the $O(N^2)$ scaling problem and hallucination drift commonly found in LLM pipelines.

1. **Extraction (Page-Aware Semantic Chunking):** PDFs are split while maintaining strict page-level lineage. The LLM extracts facts into a fully agnostic Schema (Subject, Predicate, Object, Qualifiers).
2. **Ingestion Verifier Gate:** Before saving to the database, a deterministic fuzzy-matching gate verifies that the extracted `source_quote` genuinely exists in the raw chunk. Grounding failures are logged to the `failure_logs` table.
3. **Diversity Vector Search (Top-K):** To compare facts, we use `pgvector` to pull the Top-K most semantically similar claims, deliberately mixing cross-document and intra-document claims to combat proximity bias.
4. **Tier 1 (Fast Filter) & Tier 2 (LLM Verdict):** Deterministic filters handle basic rejections. Surviving pairs go to the LLM for a final corroboration/contradiction verdict, which is permanently saved to the `verdicts` table as a graph edge.

## Limitations and Next Steps
- Currently uses a simplistic Tier 1 filter. Next step is a robust deterministic rules engine (e.g., using explicit unit conversion logic).
- Extracting huge PDFs sequentially blocks the user (even with Streamlit progress bars). Next step is moving ingestion to a background Celery worker queue.

## Additional Notes
- The "Evaluator Showcase" tab in the Streamlit UI specifically hard-pins the exact 4 required assignment cases for easy grading.

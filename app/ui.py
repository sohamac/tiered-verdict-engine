import sys
import os
# Ensure the root project directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import tempfile
import os
from app.db import init_db, get_db, Claim, Verdict, FailureLog
from app.extractor import process_pdf
from app.engine import run_verdict_engine
from sqlalchemy import select, or_

# Prevent connection exhaustion
@st.cache_resource
def get_db_session():
    init_db()
    return next(get_db())

db = get_db_session()

st.title("Tiered Verdict Engine")

tab1, tab2, tab3, tab4 = st.tabs(["Upload & Process", "Evaluator Showcase", "Knowledge Base", "Audit & Failures"])

with tab1:
    st.header("Ingest Documents")
    uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
    
    if st.button("Process Documents"):
        if uploaded_files:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processing {uploaded_file.name}...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                
                claims_count, failure_count = process_pdf(tmp_path, db)
                os.unlink(tmp_path)
                
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            status_text.text("Running Tier 2 Verdict Engine...")
            run_verdict_engine(db)
            
            status_text.text("Processing Complete!")
            st.success("Documents ingested and relationships evaluated.")
        else:
            st.warning("Please upload a PDF first.")

with tab2:
    st.header("Evaluator Showcase")
    st.markdown("This tab explicitly surfaces the 4 cases requested in the assignment.")
    
    # Showcase queries
    case_type = st.radio("Select Case to Display:", ["Corroboration", "Contradiction", "Reconciled Context", "Failure/Audit"])
    
    if case_type == "Corroboration":
        corroborated = db.scalars(select(Verdict).filter_by(relationship_type="corroborated")).first()
        if corroborated:
            st.subheader("✅ Corroborated Fact")
            st.write(f"**Reasoning:** {corroborated.reasoning}")
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Claim A:** {corroborated.claim_a.subject} {corroborated.claim_a.predicate} {corroborated.claim_a.object}")
                st.caption(f"Source: {corroborated.claim_a.filename} (Page {corroborated.claim_a.page_number})")
            with col2:
                st.info(f"**Claim B:** {corroborated.claim_b.subject} {corroborated.claim_b.predicate} {corroborated.claim_b.object}")
                st.caption(f"Source: {corroborated.claim_b.filename} (Page {corroborated.claim_b.page_number})")
        else:
            st.write("No corroborated facts found yet.")
            
    elif case_type == "Contradiction":
        contradicted = db.scalars(select(Verdict).filter_by(relationship_type="contradicted")).first()
        if contradicted:
            st.subheader("❌ Genuine Contradiction")
            st.write(f"**Reasoning:** {contradicted.reasoning}")
            # ... similar display to corroboration
        else:
            st.write("No contradictions found yet.")
            
    elif case_type == "Reconciled Context":
        reconciled = db.scalars(select(Verdict).filter_by(relationship_type="reconciled")).first()
        if reconciled:
            st.subheader("🔍 Contextually Reconciled")
            st.write(f"**Reasoning:** {reconciled.reasoning}")
            # ... similar display
        else:
            st.write("No reconciled facts found yet.")
            
    elif case_type == "Failure/Audit":
        failure = db.scalars(select(FailureLog)).first()
        if failure:
            st.subheader("⚠️ Grounding or Extraction Failure Caught")
            st.error(failure.error_type)
            st.write(f"**Message:** {failure.error_message}")
            st.text_area("Raw Context", failure.context, height=150)
        else:
            st.write("No failures caught yet.")

with tab3:
    st.header("Knowledge Base Graph")
    verdicts = db.scalars(select(Verdict)).all()
    for v in verdicts:
        emoji = "🔗" if v.relationship_type == "corroborated" else ("⚔️" if v.relationship_type == "contradicted" else ("🤝" if v.relationship_type == "reconciled" else "⚪"))
        with st.expander(f"{emoji} {v.relationship_type.upper()}: {v.claim_a.subject} vs {v.claim_b.subject}"):
            st.write(f"**Reasoning:** {v.reasoning}")

with tab4:
    st.header("System Failure Logs")
    failures = db.scalars(select(FailureLog)).all()
    st.dataframe([{"Type": f.error_type, "Message": f.error_message, "Context": f.context[:100]+"..."} for f in failures])

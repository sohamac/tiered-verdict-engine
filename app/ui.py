import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore", message="Direct use of automatic function calling.*")

import streamlit as st
import tempfile
import requests
from app.db import init_db, get_db, Claim, Verdict, FailureLog
from app.extractor import process_pdf
from app.engine import run_verdict_engine
from sqlalchemy import select

# Initialize DB once
init_db()

st.title("🧠 Tiered Verdict Engine")
st.markdown("**Fact Knowledge Layer** — Delhivery Document Analysis")

tab1, tab2, tab3, tab4 = st.tabs([
    "📤 Upload & Process", 
    "🏆 Evaluator Showcase", 
    "🔍 Knowledge Base", 
    "⚠️ Audit & Failures"
])

with tab1:
    st.header("Ingest Documents")
    uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
    
    if st.button("Process Documents"):
        if uploaded_files:
            db = next(get_db())
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
            run_verdict_engine(db, process_all=False)
            
            status_text.text("Processing Complete!")
            st.success(f"Extracted {claims_count} claims. {failure_count} failures caught.")
        else:
            st.warning("Please upload a PDF first.")

with tab2:
    st.header("Evaluator Showcase")
    st.markdown("The 4 required cases for the assignment.")
    
    db = next(get_db())
    case_type = st.radio(
        "Select Case:", 
        ["Corroboration", "Contradiction", "Reconciled Context", "Failure/Audit"]
    )
    
    if case_type == "Corroboration":
        corroborated = db.scalars(
            select(Verdict).filter_by(relationship_type="corroborated")
        ).first()
        if corroborated:
            st.subheader("✅ Corroborated Fact")
            st.info(f"**Reasoning:** {corroborated.reasoning}")
            st.caption(f"Tier used: {corroborated.tier_used} | Verified: {corroborated.verification_status}")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Claim A:** {corroborated.claim_a.subject} → {corroborated.claim_a.predicate} → {corroborated.claim_a.object}")
                st.caption(f"Source: {corroborated.claim_a.filename} (Page {corroborated.claim_a.page_number})")
                with st.expander("Quote A"):
                    st.text(corroborated.claim_a.source_quote)
            with col2:
                st.write(f"**Claim B:** {corroborated.claim_b.subject} → {corroborated.claim_b.predicate} → {corroborated.claim_b.object}")
                st.caption(f"Source: {corroborated.claim_b.filename} (Page {corroborated.claim_b.page_number})")
                with st.expander("Quote B"):
                    st.text(corroborated.claim_b.source_quote)
        else:
            st.write("No corroborated facts found yet. Process some documents first.")
            
    elif case_type == "Contradiction":
        contradicted = db.scalars(
            select(Verdict).filter_by(relationship_type="contradicted")
        ).first()
        if contradicted:
            st.subheader("❌ Genuine Contradiction")
            st.error(f"**Reasoning:** {contradicted.reasoning}")
            st.caption(f"Tier used: {contradicted.tier_used} | Verified: {contradicted.verification_status}")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Claim A:** {contradicted.claim_a.subject} → {contradicted.claim_a.predicate} → {contradicted.claim_a.object}")
                st.caption(f"Source: {contradicted.claim_a.filename} (Page {contradicted.claim_a.page_number})")
                with st.expander("Quote A"):
                    st.text(contradicted.claim_a.source_quote)
            with col2:
                st.write(f"**Claim B:** {contradicted.claim_b.subject} → {contradicted.claim_b.predicate} → {contradicted.claim_b.object}")
                st.caption(f"Source: {contradicted.claim_b.filename} (Page {contradicted.claim_b.page_number})")
                with st.expander("Quote B"):
                    st.text(contradicted.claim_b.source_quote)
        else:
            st.write("No contradictions found yet. Process some documents first.")
            
    elif case_type == "Reconciled Context":
        reconciled = db.scalars(
            select(Verdict).filter_by(relationship_type="reconciled")
        ).first()
        if reconciled:
            st.subheader("🔍 Contextually Reconciled")
            st.warning(f"**Reasoning:** {reconciled.reasoning}")
            st.caption(f"Tier used: {reconciled.tier_used} | Verified: {reconciled.verification_status}")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Claim A:** {reconciled.claim_a.subject} → {reconciled.claim_a.predicate} → {reconciled.claim_a.object}")
                st.caption(f"Source: {reconciled.claim_a.filename} (Page {reconciled.claim_a.page_number})")
                with st.expander("Quote A"):
                    st.text(reconciled.claim_a.source_quote)
            with col2:
                st.write(f"**Claim B:** {reconciled.claim_b.subject} → {reconciled.claim_b.predicate} → {reconciled.claim_b.object}")
                st.caption(f"Source: {reconciled.claim_b.filename} (Page {reconciled.claim_b.page_number})")
                with st.expander("Quote B"):
                    st.text(reconciled.claim_b.source_quote)
        else:
            st.write("No reconciled facts found yet. Process some documents first.")
            
    elif case_type == "Failure/Audit":
        st.subheader("Case 4a: Extraction/Grounding Failure")
        failure = db.scalars(
            select(FailureLog).filter(FailureLog.error_type.in_([
                "Grounding_Verification_Failed", 
                "Low_Confidence_Extraction",
                "Extraction_Error"
            ]))
        ).first()
        if failure:
            st.error(failure.error_type)
            st.write(f"**Message:** {failure.error_message}")
            st.text_area("Context", failure.context, height=150)
        else:
            st.write("No extraction failures caught yet.")
        
        st.divider()
        st.subheader("Case 4b: Tier 2 Reasoning Failure")
        t2_fail = db.scalars(
            select(FailureLog).filter_by(error_type="Tier2_Evidence_Verification_Failed")
        ).first()
        if t2_fail:
            st.error("Tier 2 Evidence Verification Failed")
            st.write(f"**Message:** {t2_fail.error_message}")
        else:
            st.write("No Tier 2 reasoning failures caught yet.")

with tab3:
    st.header("Knowledge Base Graph")
    db = next(get_db())
    verdicts = db.scalars(select(Verdict)).all()
    
    if not verdicts:
        st.info("No relationships found yet. Upload and process documents first.")
    else:
        rel_filter = st.multiselect(
            "Filter by type:", 
            ["corroborated", "contradicted", "reconciled"],
            default=["corroborated", "contradicted", "reconciled"]
        )
        for v in verdicts:
            if v.relationship_type not in rel_filter:
                continue
            emoji = {"corroborated": "🔗", "contradicted": "⚔️", "reconciled": "🤝"}.get(v.relationship_type, "⚪")
            with st.expander(f"{emoji} {v.relationship_type.upper()}: {v.claim_a.subject} vs {v.claim_b.subject}"):
                st.write(f"**Reasoning:** {v.reasoning}")
                st.caption(f"Tier: {v.tier_used} | Verified: {v.verification_status} | Confidence: {v.confidence:.2f}")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"A: {v.claim_a.object}")
                    st.caption(f"{v.claim_a.filename} p.{v.claim_a.page_number}")
                with col2:
                    st.write(f"B: {v.claim_b.object}")
                    st.caption(f"{v.claim_b.filename} p.{v.claim_b.page_number}")

with tab4:
    st.header("System Failure Logs")
    db = next(get_db())
    failures = db.scalars(select(FailureLog)).all()
    if failures:
        data = []
        for f in failures:
            data.append({
                "Type": f.error_type,
                "Message": f.error_message[:100] + "...",
                "Context": f.context[:80] + "..." if f.context else ""
            })
        st.dataframe(data, use_container_width=True)
    else:
        st.info("No failures logged yet.")

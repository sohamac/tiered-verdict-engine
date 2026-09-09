from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.dialects.postgresql import insert
from app.db import Claim, Verdict
from app.schema import Tier2Verdict, VerdictType

def run_verdict_engine(db: Session, newly_inserted_only: bool = True):
    # Using gemini-1.5-pro for the complex reasoning task, but flash works too
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest", temperature=0.0)
    structured_llm = llm.with_structured_output(Tier2Verdict)
    
    claims = db.scalars(select(Claim)).all()
    
    for current_claim in claims:
        # Diversity Vector Search: Get Top 20 most similar claims
        similar_claims = db.scalars(
            select(Claim)
            .filter(Claim.id != current_claim.id)
            .order_by(Claim.embedding.cosine_distance(current_claim.embedding))
            .limit(20)
        ).all()
        
        # Python Filter: Ensure we capture both cross-doc and same-doc
        cross_doc_matches = [c for c in similar_claims if c.doc_id != current_claim.doc_id][:3]
        same_doc_matches = [c for c in similar_claims if c.doc_id == current_claim.doc_id][:2]
        
        top_k = cross_doc_matches + same_doc_matches
        
        for candidate in top_k:
            # Deterministic Ordering to satisfy DB constraint
            claim_a, claim_b = (current_claim, candidate) if current_claim.id < candidate.id else (candidate, current_claim)
            
            # Tier 1 (Fast Filter)
            if len(set(claim_a.subject.lower().split()) & set(claim_b.subject.lower().split())) == 0:
                continue
                
            # Check if this pair was already evaluated
            existing_verdict = db.scalar(
                select(Verdict).filter(
                    and_(Verdict.claim_a_id == claim_a.id, Verdict.claim_b_id == claim_b.id)
                )
            )
            if existing_verdict:
                continue

            # Tier 2 (Verdict)
            prompt = f"""
            Evaluate the relationship between these two facts:
            
            FACT A (Doc: {claim_a.filename}, Page {claim_a.page_number}):
            Subject: {claim_a.subject}
            Predicate: {claim_a.predicate}
            Object: {claim_a.object}
            Qualifiers: {claim_a.qualifiers}
            Quote: "{claim_a.source_quote}"
            
            FACT B (Doc: {claim_b.filename}, Page {claim_b.page_number}):
            Subject: {claim_b.subject}
            Predicate: {claim_b.predicate}
            Object: {claim_b.object}
            Qualifiers: {claim_b.qualifiers}
            Quote: "{claim_b.source_quote}"
            
            Are these corroborated (same fact), contradicted (conflicting facts), reconciled (appear to conflict but explained by qualifiers like time/units), or unrelated?
            """
            
            try:
                result = structured_llm.invoke(prompt)
                
                # Insert safely using ON CONFLICT DO NOTHING
                stmt = insert(Verdict).values(
                    claim_a_id=claim_a.id,
                    claim_b_id=claim_b.id,
                    relationship_type=result.relationship_type.value,
                    reasoning=result.reasoning
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=['claim_a_id', 'claim_b_id'])
                db.execute(stmt)
                db.commit()
            except Exception as e:
                db.rollback()
                pass # A production system would log this Tier 2 failure

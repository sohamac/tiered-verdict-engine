from app.config import GEMINI_MODEL
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.dialects.postgresql import insert
from app.db import Claim, Verdict, FailureLog
from app.schema import Tier2Verdict, VerdictType
from app.tier1 import tier1_filter
from thefuzz import fuzz
from typing import Tuple

def verify_evidence(claim, cited_quote: str) -> Tuple[bool, str]:
    """Verify that a cited quote actually appears in the source."""
    if not cited_quote:
        return False, "No quote cited"
    similarity = fuzz.partial_ratio(cited_quote.lower(), claim.source_quote.lower())
    if similarity >= 80:
        return True, f"Verified ({similarity}%)"
    return False, f"Verification failed ({similarity}%)"

def run_verdict_engine(db: Session, process_all: bool = False):
    """Run the Tiered Verdict Engine.
    
    Args:
        db: Database session
        process_all: If False, only process claims that have no verdicts yet (incremental)
    """
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0.0)
    structured_llm = llm.with_structured_output(Tier2Verdict)
    
    # Get claims to process
    if process_all:
        claims = db.scalars(select(Claim)).all()
    else:
        # Only process claims that don't have any verdicts yet
        subq = select(Verdict.claim_a_id).union(select(Verdict.claim_b_id))
        claims = db.scalars(
            select(Claim).where(Claim.id.notin_(subq))
        ).all()
    
    for current_claim in claims:
        # Diversity Vector Search: Top 20 similar
        similar_claims = db.scalars(
            select(Claim)
            .filter(Claim.id != current_claim.id)
            .order_by(Claim.embedding.cosine_distance(current_claim.embedding))
            .limit(20)
        ).all()
        
        # Mix cross-doc and same-doc
        cross_doc = [c for c in similar_claims if c.doc_id != current_claim.doc_id][:4]
        same_doc = [c for c in similar_claims if c.doc_id == current_claim.doc_id][:2]
        top_k = cross_doc + same_doc
        
        for candidate in top_k:
            # Canonical ordering
            claim_a, claim_b = (current_claim, candidate) if current_claim.id < candidate.id else (candidate, current_claim)
            
            # Check existing
            existing = db.scalar(
                select(Verdict).filter(
                    and_(Verdict.claim_a_id == claim_a.id, Verdict.claim_b_id == claim_b.id)
                )
            )
            if existing:
                continue
            
            # ===== TIER 1: Fast Filter =====
            t1_verdict, t1_reason = tier1_filter(claim_a, claim_b)
            
            if t1_verdict == VerdictType.FLAGGED:
                # Tier 1 flagged — still needs Tier 2 to decide final verdict
                # But we pass the flag reason as context
                pass  # Continue to Tier 2 with context
            elif t1_verdict is not None:
                # Tier 1 rejected (unrelated) — skip
                continue
            
            # ===== TIER 2: LLM Verdict =====
            flag_context = f"\n[Tier 1 flagged: {t1_reason}]" if t1_verdict == VerdictType.FLAGGED else ""
            
            prompt = f"""Evaluate the relationship between these two facts.{flag_context}

FACT A (from {claim_a.filename}, page {claim_a.page_number}):
- Type: {claim_a.claim_type}
- Subject: {claim_a.subject}
- Predicate: {claim_a.predicate}
- Object: {claim_a.object}
- Qualifiers: {claim_a.qualifiers}
- Source Quote: "{claim_a.source_quote}"

FACT B (from {claim_b.filename}, page {claim_b.page_number}):
- Type: {claim_b.claim_type}
- Subject: {claim_b.subject}
- Predicate: {claim_b.predicate}
- Object: {claim_b.object}
- Qualifiers: {claim_b.qualifiers}
- Source Quote: "{claim_b.source_quote}"

Determine if these are:
- CORROBORATED: Same fact, expressed differently
- CONTRADICTED: Genuine conflict that cannot be explained
- RECONCILED: Appear to conflict but explained by context (time, units, scope)
- UNRELATED: Not about the same thing

Provide your reasoning and cite the specific evidence quotes you used."""
            
            try:
                result = structured_llm.invoke(prompt)
                
                # ===== EVIDENCE VERIFIER =====
                verified_a, status_a = verify_evidence(claim_a, result.cited_quote_a)
                verified_b, status_b = verify_evidence(claim_b, result.cited_quote_b)
                
                verification_status = "verified" if (verified_a and verified_b) else "failed"
                
                if verification_status == "failed":
                    # Log but still save — the reasoning might be valid even if quotes are slightly off
                    log = FailureLog(
                        doc_id=claim_a.doc_id,
                        error_type="Tier2_Evidence_Verification_Failed",
                        context=f"Pair: {claim_a.id} vs {claim_b.id}",
                        error_message=f"A: {status_a} | B: {status_b}"
                    )
                    db.add(log)
                
                # Determine final tier_used
                tier_used = 1 if (t1_verdict == VerdictType.FLAGGED and result.relationship_type in [VerdictType.RECONCILED, VerdictType.CONTRADICTED]) else 2
                
                stmt = insert(Verdict).values(
                    claim_a_id=claim_a.id,
                    claim_b_id=claim_b.id,
                    relationship_type=result.relationship_type.value,
                    confidence=0.85 if verification_status == "verified" else 0.6,
                    tier_used=tier_used,
                    reasoning=result.reasoning,
                    verified_quote_a=result.cited_quote_a,
                    verified_quote_b=result.cited_quote_b,
                    verification_status=verification_status
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=['claim_a_id', 'claim_b_id'])
                db.execute(stmt)
                db.commit()
                
            except Exception as e:
                db.rollback()
                log = FailureLog(
                    doc_id=claim_a.doc_id,
                    error_type="Tier2_Error",
                    context=f"Pair: {claim_a.id} vs {claim_b.id}",
                    error_message=str(e)
                )
                db.add(log)
                db.commit()

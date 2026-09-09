from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
import tempfile
import os
import shutil

from app.db import get_db, init_db, Claim, Verdict, FailureLog
from app.extractor import process_pdf
from app.engine import run_verdict_engine

app = FastAPI(title="Fact Knowledge Layer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files allowed")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        claims_count, failures_count = process_pdf(tmp_path, db)
        run_verdict_engine(db, process_all=False)
        
        return {
            "status": "success",
            "filename": file.filename,
            "claims_extracted": claims_count,
            "failures": failures_count
        }
    finally:
        os.unlink(tmp_path)

@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.execute(
        text("SELECT c.doc_id, c.filename, COUNT(c.id) as claim_count FROM claims c GROUP BY c.doc_id, c.filename")
    ).fetchall()
    return [{"doc_id": d[0], "filename": d[1], "claim_count": d[2]} for d in docs]

@app.get("/claims")
def list_claims(db: Session = Depends(get_db)):
    claims = db.query(Claim).order_by(Claim.id.desc()).limit(100).all()
    return [{
        "id": c.id,
        "doc_id": c.doc_id,
        "filename": c.filename,
        "claim_type": c.claim_type,
        "subject": c.subject,
        "predicate": c.predicate,
        "object": c.object,
        "qualifiers": c.qualifiers,
        "source_quote": c.source_quote,
        "extraction_confidence": c.extraction_confidence,
        "page_number": c.page_number
    } for c in claims]

@app.get("/claims/{claim_id}")
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    return {
        "id": claim.id,
        "claim_type": claim.claim_type,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "qualifiers": claim.qualifiers,
        "source_quote": claim.source_quote,
        "extraction_confidence": claim.extraction_confidence,
        "page_number": claim.page_number,
        "filename": claim.filename
    }

@app.get("/relationships")
def list_relationships(rel_type: str = None, db: Session = Depends(get_db)):
    query = db.query(Verdict)
    if rel_type:
        query = query.filter(Verdict.relationship_type == rel_type)
    verdicts = query.order_by(Verdict.id.desc()).limit(100).all()
    
    result = []
    for v in verdicts:
        result.append({
            "id": v.id,
            "relationship_type": v.relationship_type,
            "confidence": v.confidence,
            "tier_used": v.tier_used,
            "reasoning": v.reasoning,
            "verification_status": v.verification_status,
            "claim_a": {
                "subject": v.claim_a.subject,
                "predicate": v.claim_a.predicate,
                "object": v.claim_a.object,
                "filename": v.claim_a.filename,
                "page": v.claim_a.page_number
            },
            "claim_b": {
                "subject": v.claim_b.subject,
                "predicate": v.claim_b.predicate,
                "object": v.claim_b.object,
                "filename": v.claim_b.filename,
                "page": v.claim_b.page_number
            }
        })
    return result

@app.get("/relationships/{rel_id}")
def get_relationship(rel_id: int, db: Session = Depends(get_db)):
    v = db.query(Verdict).filter(Verdict.id == rel_id).first()
    if not v:
        raise HTTPException(404, "Relationship not found")
    return {
        "id": v.id,
        "relationship_type": v.relationship_type,
        "confidence": v.confidence,
        "tier_used": v.tier_used,
        "reasoning": v.reasoning,
        "verified_quote_a": v.verified_quote_a,
        "verified_quote_b": v.verified_quote_b,
        "verification_status": v.verification_status,
        "claim_a": {
            "subject": v.claim_a.subject,
            "predicate": v.claim_a.predicate,
            "object": v.claim_a.object,
            "source_quote": v.claim_a.source_quote,
            "filename": v.claim_a.filename,
            "page": v.claim_a.page_number
        },
        "claim_b": {
            "subject": v.claim_b.subject,
            "predicate": v.claim_b.predicate,
            "object": v.claim_b.object,
            "source_quote": v.claim_b.source_quote,
            "filename": v.claim_b.filename,
            "page": v.claim_b.page_number
        }
    }

@app.get("/failures")
def list_failures(db: Session = Depends(get_db)):
    failures = db.query(FailureLog).order_by(FailureLog.id.desc()).limit(50).all()
    return [{
        "id": f.id,
        "error_type": f.error_type,
        "error_message": f.error_message,
        "context": f.context
    } for f in failures]

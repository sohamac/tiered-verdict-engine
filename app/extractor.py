from app.config import GEMINI_MODEL, GEMINI_EMBEDDING_MODEL
import os
import uuid
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from thefuzz import fuzz
from sqlalchemy.orm import Session
from app.schema import ExtractionResult
from app.db import Claim, FailureLog

EXTRACTION_PROMPT_TEMPLATE = """
You are a precise fact-extraction engine. Extract ALL meaningful claims from the text below.

A "claim" is any statement that asserts a fact about an entity. Include:
- Numerical facts (revenue, profit, shipments, percentages, counts)
- Categorical facts (roles, statuses, locations, types)
- Relational facts (acquisitions, partnerships, expansions)
- Definitional facts (what something is, what it does)

For EACH claim, output:
- claim_type: numerical | categorical | relational | definitional
- subject: the entity being described
- predicate: what is being said about it
- object: the value or target
- qualifiers: dict with keys like time_scope, unit, geography, fiscal_year, basis
- source_quote: the EXACT verbatim text supporting this claim
- extraction_confidence: 0.0-1.0

RULES:
1. source_quote MUST appear verbatim (or very close) in the text.
2. Include units in qualifiers, not in object.
3. Include time periods in qualifiers.
4. Be exhaustive — extract every fact.
5. If a fact seems uncertain, lower the confidence.

TEXT:
{text}
"""

def process_pdf(filepath: str, db: Session):
    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0.0)
    structured_llm = llm.with_structured_output(ExtractionResult)
    embeddings = GoogleGenerativeAIEmbeddings(model=GEMINI_EMBEDDING_MODEL)
    
    filename = os.path.basename(filepath)
    doc_id = str(uuid.uuid4())
    
    loader = PyPDFLoader(filepath)
    pages = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    total_claims = 0
    total_failures = 0
    
    for page in pages:
        chunks = text_splitter.split_documents([page])
        for chunk in chunks:
            chunk_text = chunk.page_content
            page_number = chunk.metadata.get("page", 0) + 1
            chunk_id = str(uuid.uuid4())
            
            try:
                prompt = EXTRACTION_PROMPT_TEMPLATE.format(text=chunk_text)
                result = structured_llm.invoke(prompt)
                
                if not result or not result.claims:
                    continue
                    
                for extracted_claim in result.claims:
                    # Ingestion Verifier Gate
                    similarity = fuzz.partial_ratio(
                        extracted_claim.source_quote.lower(), 
                        chunk_text.lower()
                    )
                    
                    if similarity < 85:
                        log = FailureLog(
                            doc_id=doc_id,
                            chunk_id=chunk_id,
                            error_type="Grounding_Verification_Failed",
                            context=f"Doc: {filename}, Page: {page_number}",
                            error_message=f"Fuzzy match {similarity}% < 85%. Quote: {extracted_claim.source_quote[:200]}"
                        )
                        db.add(log)
                        total_failures += 1
                        continue
                    
                    # Low confidence flag
                    if extracted_claim.extraction_confidence < 0.6:
                        log = FailureLog(
                            doc_id=doc_id,
                            chunk_id=chunk_id,
                            error_type="Low_Confidence_Extraction",
                            context=f"Doc: {filename}, Page: {page_number}",
                            error_message=f"Confidence {extracted_claim.extraction_confidence} for: {extracted_claim.subject} {extracted_claim.predicate} {extracted_claim.object}"
                        )
                        db.add(log)
                    
                    claim_text = f"{extracted_claim.subject} {extracted_claim.predicate} {extracted_claim.object}"
                    vector = embeddings.embed_query(claim_text)
                    
                    db_claim = Claim(
                        doc_id=doc_id,
                        filename=filename,
                        page_number=page_number,
                        chunk_id=chunk_id,
                        claim_type=extracted_claim.claim_type.value,
                        subject=extracted_claim.subject,
                        predicate=extracted_claim.predicate,
                        object=extracted_claim.object,
                        qualifiers=extracted_claim.qualifiers,
                        source_quote=extracted_claim.source_quote,
                        extraction_confidence=extracted_claim.extraction_confidence,
                        extraction_method=f"llm_{GEMINI_MODEL}",
                        embedding=vector
                    )
                    db.add(db_claim)
                    total_claims += 1
                    
            except Exception as e:
                log = FailureLog(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    error_type="Extraction_Error",
                    context=chunk_text[:500],
                    error_message=str(e)
                )
                db.add(log)
                total_failures += 1
                
    db.commit()
    return total_claims, total_failures

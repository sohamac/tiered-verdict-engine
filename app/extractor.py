import os
import uuid
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from thefuzz import fuzz
from sqlalchemy.orm import Session
from app.schema import ExtractionResult
from app.db import Claim, FailureLog

def process_pdf(filepath: str, db: Session):
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", temperature=0.0)
    structured_llm = llm.with_structured_output(ExtractionResult)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    
    filename = os.path.basename(filepath)
    doc_id = str(uuid.uuid4())
    
    # Page-Aware Lineage
    loader = PyPDFLoader(filepath)
    pages = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", " ", ""]
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
                # LLM Extraction
                result = structured_llm.invoke(
                    f"Extract all numerical or semantic claims from this text block.\n\nText:\n{chunk_text}"
                )
                
                # If the LLM returns None or no claims, skip
                if not result or not result.claims:
                    continue
                    
                for extracted_claim in result.claims:
                    # Fuzzy Ingestion Verifier Gate
                    similarity = fuzz.partial_ratio(extracted_claim.source_quote.lower(), chunk_text.lower())
                    if similarity < 90:
                        # Log grounding failure
                        log = FailureLog(
                            error_type="Grounding_Verification_Failed",
                            context=f"Doc: {filename}, Page: {page_number}\nChunk: {chunk_text}\nQuote: {extracted_claim.source_quote}",
                            error_message=f"Fuzzy match score {similarity}% is below 90% threshold."
                        )
                        db.add(log)
                        total_failures += 1
                        continue
                    
                    # Generate vector embedding
                    claim_text = f"{extracted_claim.subject} {extracted_claim.predicate} {extracted_claim.object} (Qualifiers: {extracted_claim.qualifiers})"
                    vector = embeddings.embed_query(claim_text)
                    
                    # Store verified claim
                    db_claim = Claim(
                        doc_id=doc_id,
                        filename=filename,
                        page_number=page_number,
                        chunk_id=chunk_id,
                        subject=extracted_claim.subject,
                        predicate=extracted_claim.predicate,
                        object=extracted_claim.object,
                        qualifiers=extracted_claim.qualifiers,
                        source_quote=extracted_claim.source_quote,
                        embedding=vector
                    )
                    db.add(db_claim)
                    total_claims += 1
                    
            except Exception as e:
                # Log extraction failure (e.g. schema parse error)
                log = FailureLog(
                    error_type="Extraction_Error",
                    context=chunk_text,
                    error_message=str(e)
                )
                db.add(log)
                total_failures += 1
                
    db.commit()
    return total_claims, total_failures

from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, ForeignKey, CheckConstraint, UniqueConstraint, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pgvector.sqlalchemy import Vector
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/knowledge_base")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    # Lineage
    doc_id = Column(String, index=True)
    filename = Column(String)
    page_number = Column(Integer)
    chunk_id = Column(String)
    
    # Agnostic Claim Data
    subject = Column(String, index=True)
    predicate = Column(String, index=True)
    object = Column(String)
    qualifiers = Column(JSON)
    
    # Evidence
    source_quote = Column(Text)
    
    # Vector Embedding (Google text-embedding-004 is 768 dims)
    embedding = Column(Vector(768))

class Verdict(Base):
    __tablename__ = "verdicts"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_a_id = Column(Integer, ForeignKey("claims.id"))
    claim_b_id = Column(Integer, ForeignKey("claims.id"))
    relationship_type = Column(String, index=True)
    reasoning = Column(Text)
    
    # Constraint 1: Canonical Ordering
    __table_args__ = (
        CheckConstraint('claim_a_id < claim_b_id', name='check_canonical_ordering'),
        UniqueConstraint('claim_a_id', 'claim_b_id', name='uq_claim_pair'),
    )

    claim_a = relationship("Claim", foreign_keys=[claim_a_id])
    claim_b = relationship("Claim", foreign_keys=[claim_b_id])

class FailureLog(Base):
    __tablename__ = "failure_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String)
    context = Column(Text)
    error_message = Column(Text)

def init_db():
    # Explicitly create the vector extension before creating tables
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

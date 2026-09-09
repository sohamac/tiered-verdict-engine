from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from enum import Enum

class VerdictType(str, Enum):
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    RECONCILED = "reconciled"
    UNRELATED = "unrelated"

class ClaimExtract(BaseModel):
    """A single structured claim extracted from text."""
    subject: str = Field(description="The main entity or subject of the claim.")
    predicate: str = Field(description="The relationship or action.")
    object: str = Field(description="The target or value of the claim.")
    qualifiers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Contextual qualifiers like time, geography, units, or scope."
    )
    source_quote: str = Field(description="The exact, verbatim quote from the text that grounds this claim.")

class ExtractionResult(BaseModel):
    """The result of an LLM extraction pass over a chunk of text."""
    claims: list[ClaimExtract] = Field(default_factory=list)

class Tier2Verdict(BaseModel):
    """The LLM's verdict when comparing two claims."""
    relationship_type: VerdictType = Field(description="The determined relationship between the two claims.")
    reasoning: str = Field(description="Step-by-step reasoning explaining the verdict.")


import pytest
from thefuzz import fuzz
from app.tier1 import tier1_filter, check_unit_mismatch, check_time_scope, check_numeric_delta
from app.schema import VerdictType

def test_fuzzy_verifier_gate():
    chunk_text = 'The company reported—during Q3—a massive "revenue" spike.\nIt was unprecedented.'
    llm_source_quote = "The company reported - during Q3 - a massive 'revenue' spike. It was unprecedented."
    assert llm_source_quote not in chunk_text
    similarity = fuzz.partial_ratio(llm_source_quote.lower(), chunk_text.lower())
    assert similarity >= 85

def test_unit_mismatch_detected():
    q_a = {"unit": "cr"}
    q_b = {"unit": "mn"}
    result = check_unit_mismatch(q_a, q_b)
    assert result is not None
    assert "mismatch" in result.lower()

def test_unit_mismatch_same():
    q_a = {"unit": "₹"}
    q_b = {"unit": "inr"}
    result = check_unit_mismatch(q_a, q_b)
    assert result is None  # Normalized to same

def test_time_scope_different_fiscal():
    q_a = {"fiscal_year": "fy24"}
    q_b = {"fiscal_year": "fy23"}
    result = check_time_scope(q_a, q_b)
    assert result is not None

def test_numeric_delta_significant():
    result = check_numeric_delta("100", "200", threshold=0.05)
    assert result is not None
    assert "50.0%" in result or "100%" in result

def test_numeric_delta_small():
    result = check_numeric_delta("100", "102", threshold=0.05)
    assert result is None

def test_tier1_rejects_different_subjects():
    class FakeClaim:
        def __init__(self, subj, pred, obj, ctype="numerical", quals=None):
            self.subject = subj
            self.predicate = pred
            self.object = obj
            self.claim_type = ctype
            self.qualifiers = quals or {}
    
    a = FakeClaim("Tesla", "revenue", "100B")
    b = FakeClaim("Apple", "revenue", "200B")
    verdict, reason = tier1_filter(a, b)
    assert verdict is None  # Different subjects = skip entirely

def test_tier1_flags_unit_mismatch():
    class FakeClaim:
        def __init__(self, subj, pred, obj, ctype="numerical", quals=None):
            self.subject = subj
            self.predicate = pred
            self.object = obj
            self.claim_type = ctype
            self.qualifiers = quals or {}
    
    a = FakeClaim("Delhivery", "revenue", "100", quals={"unit": "cr"})
    b = FakeClaim("Delhivery", "revenue", "1000", quals={"unit": "mn"})
    verdict, reason = tier1_filter(a, b)
    assert verdict == VerdictType.FLAGGED
    assert "unit" in reason.lower()

"""Tier 1: Deterministic fast filter.
Only REJECTS or FLAGS — never positively confirms corroboration.
"""

from typing import Optional, Tuple
from app.schema import VerdictType

def check_unit_mismatch(q_a: dict, q_b: dict) -> Optional[str]:
    """Check for explicit unit mismatches."""
    unit_a = str(q_a.get("unit", "")).lower().strip()
    unit_b = str(q_b.get("unit", "")).lower().strip()
    
    if not unit_a or not unit_b:
        return None
    
    # Normalize common variants
    normalize = {
        "inr": "rupees", "₹": "rupees", "rs.": "rupees", "rs": "rupees",
        "usd": "dollars", "$": "dollars",
        "cr": "crore", "crores": "crore", "crore": "crore",
        "mn": "million", "millions": "million", "million": "million",
        "bn": "billion", "billions": "billion", "billion": "billion",
    }
    unit_a = normalize.get(unit_a, unit_a)
    unit_b = normalize.get(unit_b, unit_b)
    
    if unit_a != unit_b:
        return f"Unit mismatch: {unit_a} vs {unit_b}"
    return None

def check_time_scope(q_a: dict, q_b: dict) -> Optional[str]:
    """Check for non-overlapping time scopes."""
    time_a = str(q_a.get("time_scope", "")).lower().strip()
    time_b = str(q_b.get("time_scope", "")).lower().strip()
    fiscal_a = str(q_a.get("fiscal_year", "")).lower().strip()
    fiscal_b = str(q_b.get("fiscal_year", "")).lower().strip()
    
    # If both have explicit fiscal years
    if fiscal_a and fiscal_b and fiscal_a != fiscal_b:
        return f"Different fiscal years: {fiscal_a} vs {fiscal_b}"
    
    # If both have time scopes
    if time_a and time_b and time_a != time_b:
        # Check for overlapping periods
        if "q1" in time_a and "q1" not in time_b:
            return f"Different quarters: {time_a} vs {time_b}"
        if "fy24" in time_a and "fy23" in time_b:
            return f"Different fiscal years: {time_a} vs {time_b}"
    
    return None

def check_numeric_delta(val_a: str, val_b: str, threshold: float = 0.05) -> Optional[str]:
    """Check if two numeric values differ significantly."""
    try:
        # Extract numbers from strings
        import re
        num_a = float(re.search(r"[\d,]+\.?\d*", str(val_a).replace(",", "")).group())
        num_b = float(re.search(r"[\d,]+\.?\d*", str(val_b).replace(",", "")).group())
        
        if num_a == 0 or num_b == 0:
            return None
            
        delta = abs(num_a - num_b) / max(abs(num_a), abs(num_b))
        if delta > threshold:
            return f"Numeric delta {delta:.1%} exceeds threshold {threshold:.0%}"
    except (ValueError, AttributeError):
        pass
    return None

def check_subject_overlap(subj_a: str, subj_b: str) -> bool:
    """Check if subjects refer to the same entity."""
    words_a = set(subj_a.lower().split())
    words_b = set(subj_b.lower().split())
    
    # Require at least some word overlap
    if len(words_a & words_b) == 0:
        return False
    return True

def tier1_filter(claim_a, claim_b) -> Tuple[Optional[VerdictType], Optional[str]]:
    """
    Tier 1 deterministic filter.
    Returns: (verdict_or_None, reason)
    - If returns (VerdictType, reason): reject/flag this pair
    - If returns (None, None): pass to Tier 2
    """
    # 1. Subject overlap check
    if not check_subject_overlap(claim_a.subject, claim_a.predicate):
        return None, None  # Skip entirely — different subjects
    
    q_a = claim_a.qualifiers or {}
    q_b = claim_b.qualifiers or {}
    
    # 2. Unit mismatch → flag as needing reconciliation or contradiction
    unit_issue = check_unit_mismatch(q_a, q_b)
    if unit_issue:
        return VerdictType.FLAGGED, f"TIER1_FLAG: {unit_issue}"
    
    # 3. Time scope mismatch → likely reconcilable
    time_issue = check_time_scope(q_a, q_b)
    if time_issue:
        return VerdictType.FLAGGED, f"TIER1_FLAG: {time_issue}"
    
    # 4. Numeric delta for numerical claims
    if claim_a.claim_type == "numerical" and claim_b.claim_type == "numerical":
        num_issue = check_numeric_delta(claim_a.object, claim_b.object)
        if num_issue:
            return VerdictType.FLAGGED, f"TIER1_FLAG: {num_issue}"
    
    # 5. Categorical contradiction
    if (claim_a.claim_type == "categorical" and claim_b.claim_type == "categorical" and
        claim_a.predicate == claim_b.predicate and 
        claim_a.object.lower() != claim_b.object.lower()):
        return VerdictType.FLAGGED, f"TIER1_FLAG: Categorical mismatch: '{claim_a.object}' vs '{claim_b.object}'"
    
    # Pass to Tier 2
    return None, None

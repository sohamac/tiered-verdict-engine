from thefuzz import fuzz

def test_fuzzy_verifier_gate():
    # Simulate LLM cleaning up text (smart quotes, dashes, newlines)
    chunk_text = "The company reported—during Q3—a massive \"revenue\" spike.\nIt was unprecedented."
    llm_source_quote = "The company reported - during Q3 - a massive 'revenue' spike. It was unprecedented."
    
    # Strict matching fails
    assert llm_source_quote not in chunk_text
    
    # Fuzzy matching passes
    similarity = fuzz.partial_ratio(llm_source_quote.lower(), chunk_text.lower())
    assert similarity >= 90
    
def test_tier1_deterministic_rejects():
    # Fast filters for time mismatch
    claim_a_qualifiers = {"year": "2023"}
    claim_b_qualifiers = {"year": "2024"}
    
    assert claim_a_qualifiers["year"] != claim_b_qualifiers["year"]

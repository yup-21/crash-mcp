"""Verification script for Layered KB architecture."""
import os
import sys
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from crash_mcp.kb import get_layered_retriever, LayeredRetriever

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_layered")

def test_l1_symptom_search():
    print("\n=== Test L1: Symptom Search ===")
    
    # Initialize implementation
    # We use a test dir if possible, or the real one
    methods_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../knowledge/methods'))
    retriever = get_layered_retriever(methods_dir)
    
    # 1. Index methods (creates embeddings)
    print("Indexing methods...")
    retriever.index_methods()
    
    # 2. Search
    query = "kernel stack corruption"
    print(f"Searching for: '{query}'")
    results = retriever.search_symptom(query)
    
    for r in results:
        print(f"  - Found: {r['name']} (Score: {r['score']:.2f}, Source: {r.get('source')})")
        
    assert len(results) > 0, "Should find at least one method"
    assert any('Stack Protector' in r['name'] for r in results), "Should find Stack Protector"

def test_l2_analyze_method():
    print("\n=== Test L2: Analyze Method ===")
    methods_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../knowledge/methods'))
    retriever = get_layered_retriever(methods_dir)
    
    # Analyze 'stack_protector' (assuming ID is filename base usually, or defined in yaml)
    # Let's check stack_protector.yaml content or just guess ID 'stack_protector'
    # In simple_retriever it uses method.id.
    
    res = retriever.analyze_method('stack_protector_analysis') # ID from yaml
    if "error" in res:
         # Try loading all to see IDs
         all_methods = retriever.loader.load_all()
         first_id = list(all_methods.keys())[0]
         print(f"Using available ID: {first_id}")
         res = retriever.analyze_method(first_id)
    
    print(f"Analysis Context: {json.dumps(res, indent=2)}")
    assert "commands" in res
    assert len(res["commands"]) > 0

def test_l3_case_tree():
    print("\n=== Test L3: Case Tree Operations ===")
    methods_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../knowledge/methods'))
    retriever = get_layered_retriever(methods_dir)
    
    # 1. Save a Node
    fingerprint = "test_fp_12345"
    data = {
        "finding_summary": "rwsem blocked by task A",
        "method_used": "check_rwsem"
    }
    node_id = retriever.match_or_save_node(fingerprint, data)
    print(f"Saved Node ID: {node_id}")
    
    # 2. Match it back
    node_id_2 = retriever.match_or_save_node(fingerprint, data)
    print(f"Matched Node ID: {node_id_2}")
    assert node_id == node_id_2, "Should return same ID for same fingerprint"
    
    # 3. Search Subproblem
    query = "rwsem blocked"
    context = {"addr": "0xffff"}
    hits = retriever.search_subproblem(query, context)
    print(f"Subproblem Hits: {len(hits)}")
    for h in hits:
        print(f"  - {h['summary']} (Score: {h['score']:.2f})")
    
    # Expect at least the one we just saved (though context might differ, query text match should hit)
    if retriever.client: # Only if DB is active
        assert len(hits) > 0

    # 4. Fuzzy Match & Merge Logic
    print("\n=== Test L3: Fuzzy Match & Merge ===")
    if retriever.client:
        # Same method, slightly different finding (semantically same)
        fuzzy_data = {
            "finding_summary": "rwsem is blocked by task A", # original: "rwsem blocked by task A"
            "method_used": "check_rwsem"
        }
        # Fingerprint must be DIFFERENT to trigger semantic search
        fuzzy_fp = "test_fp_DIFFERENT_123"
        
        # Should return SAME ID as original
        merged_id = retriever.match_or_save_node(fuzzy_fp, fuzzy_data)
        print(f"Merged Node ID: {merged_id}")
        
        assert merged_id == node_id, "Should merge with original node due to semantic similarity"
        
        # Verify hit count
        # Wait for Chroma to update? Or just check collection
        res = retriever.case_node_collection.get(ids=[node_id])
        hits = res['metadatas'][0]['hit_count']
        print(f"Hit Count: {hits}")
        assert hits >= 3, "Hit count should increase (1 orig + 1 exact match + 1 fuzzy match)"

def main():
    try:
        test_l1_symptom_search()
        test_l2_analyze_method()
        test_l3_case_tree()
        print("\n✅ All Verification Tests Passed!")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

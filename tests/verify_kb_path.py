
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath("src"))


from crash_mcp.server import _get_methods_dir, _get_cases_dir, kb_list_methods, kb_search_method, kb_search_case, kb_save_case
from crash_mcp.kb import get_retriever

def test_path_resolution():
    print("=== Testing Methods Path Resolution ===")
    print(f"Testing `_get_methods_dir`...")
    path = _get_methods_dir()
    print(f"Computed path: {path}")
    
    if os.path.exists(path):
        print("SUCCESS: Directory exists.")
    else:
        print("FAILURE: Directory does not exist.")
        return

    print("\nTesting `kb_list_methods` logic...")
    result = kb_list_methods()
    # print(result)
    
    if "stack_protector" in result:
        print("SUCCESS: Found stack_protector in methods list.")
    else:
        print("FAILURE: stack_protector not found.")

    print("\nTesting `kb_search_method` logic...")
    search_res = kb_search_method("stack-protector: Kernel stack is corrupted")
    
    if "Stack Protector" in search_res:
         print("SUCCESS: Found Stack Protector method.")
    else:
         print("FAILURE: Did not find Stack Protector method.")
         
    print("\n=== Testing Cases Path Resolution ===")
    print(f"Testing `_get_cases_dir`...")
    cases_path = _get_cases_dir()
    print(f"Computed path: {cases_path}")
    
    if not os.path.exists(cases_path):
        print("Creating cases dir for test if not exists (should be handled by manager but we check path)...")
        # server logic handles makedirs in manager init, let's verify manager does it.
    

    print("\nTesting `kb_save_case` logic with Tree Structure...")
    import json
    
    # 1. Save Parent Case
    parent_res = kb_save_case(
        title="Stack Protector Failure (Parent)",
        panic_signature="stack-protector: Kernel stack is corrupted",
        root_cause="Stack canary corruption in radix_tree_lookup_slot"
    )
    print(f"Parent result: {parent_res}")
    parent_id = parent_res.split(": ")[1]
    
    # 2. Save Child Case
    fingerprint = {
        "function": "radix_tree_lookup_slot",
        "offset": "0x45",
        "module": "kernel"
    }
    child_res = kb_save_case(
        title="XArray Node Corruption (Child)",
        panic_signature="xa_node corruption",
        root_cause="Concurrent modification of xarray node",
        solution="Check for race conditions in page cache",
        parent_id=parent_id,
        fingerprint_json=json.dumps(fingerprint)
    )
    print(f"Child result: {child_res}")
    child_id = child_res.split(": ")[1]
    
    print("\nVerifying Tree Structure via Manager...")
    from crash_mcp.kb.case_manager import get_case_manager
    manager = get_case_manager(_get_cases_dir())
    
    # Check Parent
    parent_case = manager.load_case(parent_id)
    if parent_case:
        print(f"SUCCESS: Loaded parent case {parent_case.id}")
    else:
        print("FAILURE: Could not load parent case")
        
    # Check Child
    child_case = manager.load_case(child_id)
    if child_case and child_case.parent_id == parent_id:
        print(f"SUCCESS: Child case loaded and links to parent {parent_id}")
    else:
        print(f"FAILURE: Child case verification failed. Parent ID: {child_case.parent_id if child_case else 'None'}")
        
    # Check Fingerprint
    if child_case and child_case.fingerprint == fingerprint:
        print("SUCCESS: Fingerprint verified.")
    else:
        print(f"FAILURE: Fingerprint mismatch. Got: {child_case.fingerprint if child_case else 'None'}")

    # Check find_children
    children = manager.find_children(parent_id)
    if len(children) >= 1 and any(c['id'] == child_id for c in children):
         print(f"SUCCESS: find_children returned {len(children)} children, including new child.")
    else:
         print(f"FAILURE: find_children failed. Children: {children}")

    print("\nTesting `kb_search_case` logic...")
    case_res = kb_search_case("stack-protector")
    print(case_res)
    
    if "Test Case Stack Protector" in case_res:
        print("SUCCESS: Found saved test case.")
    else:
        print("FAILURE: Did not find saved test case.")


if __name__ == "__main__":
    test_path_resolution()

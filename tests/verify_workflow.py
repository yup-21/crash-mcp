"""Verification script for Simplified Workflow Helper."""
import os
import sys
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from crash_mcp.kb.workflow import quick_start

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_workflow")

def test_quick_start():
    print("\n=== Test: Quick Start ===")
    
    methods_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../knowledge/methods'))
    
    print("Quick-starting with 'kernel stack corruption'...")
    res = quick_start("kernel stack corruption", methods_dir=methods_dir)
    print(f"Result: {json.dumps(res, indent=2)}")
    
    assert res['status'] == 'ready_to_execute', f"Expected ready_to_execute, got {res['status']}"
    assert 'method_id' in res
    assert 'commands' in res
    print("Quick Start: PASS")

def main():
    try:
        test_quick_start()
        print("\n✅ Workflow Verification Passed!")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

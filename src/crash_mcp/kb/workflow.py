"""Lightweight workflow helper for crash analysis.

This module provides a thin wrapper around LayeredRetriever for quick-start scenarios.
The LLM Agent is the primary state manager; this module only provides convenience functions.
"""
import logging
import uuid
from typing import Optional, Dict, Any

from .layered_retriever import get_layered_retriever

logger = logging.getLogger(__name__)


def quick_start(panic_text: str, methods_dir: str = "knowledge/methods") -> Dict[str, Any]:
    """Quick-start helper: Search symptom and return first method to execute.
    
    This is a stateless convenience function. The Agent maintains state.
    
    Returns:
        {
            "status": "ready_to_execute" | "no_method",
            "method_id": str,
            "commands": [str],
            "session_id": str  # For tracking if Agent wants
        }
    """
    retriever = get_layered_retriever(methods_dir)
    
    # L1: Symptom Search
    results = retriever.search_symptom(panic_text, top_k=1)
    
    if not results:
        return {
            "status": "no_method",
            "message": "No matching symptom found."
        }
    
    method_data = results[0]
    method_id = method_data['id']
    
    # L2: Get Method Details
    method = retriever.analyze_method(method_id)
    if "error" in method:
        return {"status": "error", "message": method['error']}
    
    return {
        "status": "ready_to_execute",
        "session_id": str(uuid.uuid4()),
        "method_id": method_id,
        "method_name": method_data.get('name', method_id),
        "commands": method['commands'],
    }


# Deprecated: AnalysisWorkflow class removed. Use atomic KB tools directly.

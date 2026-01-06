"""Knowledge Base module for crash analysis."""
from .models import AnalysisMethod, AnalysisCase, CaseNode, MethodLoader
from .layered_retriever import LayeredRetriever, get_layered_retriever

# Backward compatibility: get_retriever now uses LayeredRetriever
get_retriever = get_layered_retriever

# Deprecated: SimpleRetriever (kept for legacy, will be removed)
from .simple_retriever import SimpleRetriever

__all__ = [
    'AnalysisMethod', 'AnalysisCase', 'CaseNode', 'MethodLoader', 
    'LayeredRetriever', 'get_layered_retriever', 'get_retriever',
    'SimpleRetriever',  # deprecated
]

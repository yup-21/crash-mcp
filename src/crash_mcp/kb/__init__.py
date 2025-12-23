"""Knowledge Base module for crash analysis."""
from .models import AnalysisMethod, AnalysisCase, MethodLoader

__all__ = ['AnalysisMethod', 'AnalysisCase', 'MethodLoader']

# Lazy import retriever to avoid chromadb dependency if not needed
def get_retriever(*args, **kwargs):
    from .retriever import KnowledgeRetriever
    return KnowledgeRetriever(*args, **kwargs)

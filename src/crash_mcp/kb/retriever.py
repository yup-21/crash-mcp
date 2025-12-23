"""Knowledge retriever using ChromaDB for vector search."""
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy imports to avoid blocking if not installed
_chromadb = None
_embedder = None


def _init_chroma():
    global _chromadb
    if _chromadb is None:
        try:
            import chromadb
            _chromadb = chromadb
        except ImportError:
            logger.warning("chromadb not installed. Run: pip install chromadb")
            raise
    return _chromadb


def _init_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            logger.warning("sentence-transformers not installed")
            _embedder = None
    return _embedder


class KnowledgeRetriever:
    """知识检索器，支持向量搜索和精确匹配"""
    
    def __init__(self, persist_dir: str = "data/chroma"):
        chromadb = _init_chroma()
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedder = _init_embedder()
        
        self.methods = self.client.get_or_create_collection(
            name="methods",
            metadata={"description": "Analysis methods"}
        )
        self.cases = self.client.get_or_create_collection(
            name="cases", 
            metadata={"description": "Analysis cases"}
        )
    
    def search_method(self, query: str, top_k: int = 3) -> List[Dict]:
        """根据 panic 信息检索分析方法"""
        results = self.methods.query(
            query_texts=[query],
            n_results=top_k
        )
        
        if not results['documents'] or not results['documents'][0]:
            return []
        
        output = []
        for i, doc in enumerate(results['documents'][0]):
            output.append({
                'id': results['ids'][0][i],
                'document': doc,
                'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                'distance': results['distances'][0][i] if results.get('distances') else None
            })
        return output
    
    def search_case(self, signature: str, top_k: int = 5) -> List[Dict]:
        """检索相似案例"""
        results = self.cases.query(
            query_texts=[signature],
            n_results=top_k
        )
        
        if not results['documents'] or not results['documents'][0]:
            return []
        
        output = []
        for i, doc in enumerate(results['documents'][0]):
            output.append({
                'id': results['ids'][0][i],
                'document': doc,
                'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                'distance': results['distances'][0][i] if results.get('distances') else None
            })
        return output
    
    def add_method(self, method: Dict) -> None:
        """添加分析方法到向量库"""
        triggers = ' '.join([t.get('pattern', '') for t in method.get('triggers', [])])
        tags = ' '.join(method.get('tags', []))
        doc = f"{method['name']} {method.get('description', '')} {triggers} {tags}"
        
        self.methods.upsert(
            documents=[doc],
            metadatas=[{
                "id": method['id'],
                "name": method['name'],
                "description": method.get('description', '')
            }],
            ids=[method['id']]
        )
        logger.info(f"Added method: {method['id']}")
    
    def add_case(self, case: Dict) -> None:
        """添加案例到向量库"""
        doc = f"{case['title']} {case['panic_signature']} {case['root_cause']}"
        
        self.cases.upsert(
            documents=[doc],
            metadatas=[{
                "id": case['id'],
                "title": case['title'],
                "root_cause": case['root_cause']
            }],
            ids=[case['id']]
        )
        logger.info(f"Added case: {case['id']}")
    
    def index_methods_from_dir(self, methods_dir: str = "knowledge/methods") -> int:
        """从目录加载所有方法并索引"""
        import yaml
        
        if not os.path.isdir(methods_dir):
            logger.warning(f"Methods directory not found: {methods_dir}")
            return 0
        
        count = 0
        for filename in os.listdir(methods_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                path = os.path.join(methods_dir, filename)
                with open(path, 'r') as f:
                    method = yaml.safe_load(f)
                self.add_method(method)
                count += 1
        
        logger.info(f"Indexed {count} methods from {methods_dir}")
        return count

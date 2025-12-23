"""Layered Knowledge Retriever implementing 3-Layer Architecture."""
import os
import logging
import json
from typing import List, Dict, Optional, Any
import hashlib

from .models import AnalysisMethod, MethodLoader, CaseNode
from .simple_retriever import SimpleRetriever
from crash_mcp.config import Config

logger = logging.getLogger(__name__)

# Lazy imports
_chromadb = None
_embedder = None

def _init_chroma():
    global _chromadb
    if _chromadb is None:
        try:
            import chromadb
            _chromadb = chromadb
        except ImportError:
            logger.warning("chromadb not installed")
            return None
    return _chromadb

def _init_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(Config.KB_EMBEDDING_MODEL)
        except ImportError:
            logger.warning("sentence-transformers not installed")
            return None
    return _embedder

class LayeredRetriever:
    """Implements 3-Layer Retrieval Strategy: Symptom (L1) -> Method (L2) -> Case (L3)"""
    
    def __init__(self, methods_dir: str = "knowledge/methods", persist_dir: str = "data/chroma"):
        self.methods_dir = methods_dir
        self.persist_dir = persist_dir
        self.loader = MethodLoader(methods_dir)
        self.simple_retriever = SimpleRetriever(methods_dir)
        
        # Init Vector DB with custom embedding
        chromadb = _init_chroma()
        if chromadb:
            self.client = chromadb.PersistentClient(path=persist_dir)
            
            # Use configurable embedding model
            try:
                from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
                ef = SentenceTransformerEmbeddingFunction(model_name=Config.KB_EMBEDDING_MODEL)
            except (ImportError, ValueError) as e:
                ef = None  # Use ChromaDB default
                logger.info(f"Using default embedding function: {e}")
            
            self.symptom_collection = self.client.get_or_create_collection(
                name="symptoms", embedding_function=ef
            )
            self.case_node_collection = self.client.get_or_create_collection(
                name="case_nodes", embedding_function=ef
            )
        else:
            self.client = None
            
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            # Index methods into Vector DB if needed
            self.index_methods()
            self._loaded = True

    def index_methods(self):
        """Index all methods from YAML to ChromaDB (L1)"""
        if not self.client:
            return

        methods = self.loader.load_all()
        ids = []
        documents = []
        metadatas = []
        
        for m_id, method in methods.items():
            # Create a rich document string for embedding
            triggers = ' '.join([t.get('pattern', '') for t in method.triggers])
            doc = f"{method.name} {method.description} {triggers} {' '.join(method.tags)}"
            ids.append(m_id)
            documents.append(doc)
            metadatas.append({"name": method.name, "type": "method"})
            
        if ids:
            self.symptom_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search_symptom(self, query: str, top_k: int = 3) -> List[Dict]:
        """Layer 1: Search Symptom -> Return Methods"""
        self._ensure_loaded()
        
        results = []
        
        # 1. Try Vector Search
        if self.client:
            vec_res = self.symptom_collection.query(query_texts=[query], n_results=top_k)
            if vec_res['ids'] and vec_res['ids'][0]:
                for i, m_id in enumerate(vec_res['ids'][0]):
                    method = self.loader.get(m_id)
                    if method:
                        results.append({
                            'id': method.id,
                            'name': method.name,
                            'score': 0.9 - (vec_res['distances'][0][i] if vec_res['distances'] else 0),
                            'source': 'vector',
                            'steps': [{'command': s.command} for s in method.steps]
                        })

        # 2. Keywork/Regex Fallback (using SimpleRetriever logic)
        simple_res = self.simple_retriever.search_method(query, top_k)
        for res in simple_res:
             # Dedup
             if not any(r['id'] == res['id'] for r in results):
                 res['source'] = 'keyword'
                 res['score'] = res['score'] / 100.0 # Normalize roughly
                 results.append(res)
                 
        # Sort and return
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def get_method(self, method_id: str) -> Optional[AnalysisMethod]:
        """Layer 2: Get specific method"""
        return self.loader.get(method_id)

    def analyze_method(self, method_id: str) -> Dict:
        """Layer 2: wrapper to return method details for Agent execution"""
        method = self.get_method(method_id)
        if not method:
            return {"error": f"Method {method_id} not found"}
        
        return {
            "id": method.id,
            "commands": [s.command for s in method.steps],
            "outputs": [o.get('name') for o in method.outputs]
        }

    def search_subproblem(self, query: str, context: Dict[str, Any], top_k: int = 3) -> List[Dict]:
        """Layer 3: Search for partial case trees / sub-problems"""
        if not self.client:
            return []
            
        # Context extraction (naive)
        context_str = " ".join([f"{k}:{v}" for k, v in context.items()])
        full_query = f"{query} {context_str}"
        
        res = self.case_node_collection.query(query_texts=[full_query], n_results=top_k)
        
        hits = []
        if res['ids'] and res['ids'][0]:
             for i, nid in enumerate(res['ids'][0]):
                 hits.append({
                     "node_id": nid,
                     "summary": res['documents'][0][i],
                     "score": 1 - (res['distances'][0][i] if res['distances'] else 0)
                 })
        return hits

    def match_or_save_node(self, fingerprint: str, data: Dict) -> str:
        """Layer 3: Match existing node or save new one.
        Logic:
        1. Exact Match (Fingerprint) -> Hit
        2. Semantic Match (Similarity > 0.8 / Dist < 0.2) -> Hit (Merge)
        3. No Match -> New Node
        """
        if not self.client:
            return "no_db"
            
        # 1. Exact Fingerprint
        res = self.case_node_collection.get(where={"fingerprint": fingerprint})
        if res['ids']:
            node_id = res['ids'][0]
            # Increment hit count (stored in metadata for simple tracking)
            meta = res['metadatas'][0] if res['metadatas'] else {}
            hits = meta.get('hit_count', 1) + 1
            meta['hit_count'] = hits
            self.case_node_collection.update(ids=[node_id], metadatas=[meta])
            return node_id
            
        # 2. Semantic Match (Vector Search)
        finding_summary = data.get('finding_summary', '')
        if finding_summary:
            vec_res = self.case_node_collection.query(
                query_texts=[finding_summary], 
                n_results=1,
                where={"method": data.get('method_used', '')} # Same method context
            )
            
            if vec_res['ids'] and vec_res['ids'][0]:
                dist = vec_res['distances'][0][0]
                # Use configurable threshold
                if dist < Config.KB_SIMILARITY_THRESHOLD:
                    node_id = vec_res['ids'][0][0]
                    # Merge Logic: Add alias/fingerprint? 
                    # For now just update stats
                    meta = vec_res['metadatas'][0][0]
                    hits = meta.get('hit_count', 1) + 1
                    meta['hit_count'] = hits
                    self.case_node_collection.update(ids=[node_id], metadatas=[meta])
                    return node_id

        # 3. New Node
        node_id = hashlib.md5(fingerprint.encode()).hexdigest()
        doc = f"{data.get('finding_summary', '')} {data.get('method_used', '')}"
        
        metadata = {
            "fingerprint": fingerprint,
            "method": data.get('method_used', ''),
            "type": "case_node",
            "hit_count": 1,
            "failure_count": 0
        }
        
        self.case_node_collection.add(
            ids=[node_id],
            documents=[doc],
            metadatas=[metadata]
        )
        return node_id

    def mark_node_failed(self, node_id: str) -> bool:
        """Mark a node as failed (dead-end), incrementing failure_count."""
        if not self.client:
            return False
            
        res = self.case_node_collection.get(ids=[node_id])
        if not res['ids']:
            return False
            
        meta = res['metadatas'][0] if res['metadatas'] else {}
        meta['failure_count'] = meta.get('failure_count', 0) + 1
        self.case_node_collection.update(ids=[node_id], metadatas=[meta])
        return True

# Global instance
_layered_retriever = None

def get_layered_retriever(methods_dir: str = "knowledge/methods", data_dir: str = "data/chroma") -> LayeredRetriever:
    global _layered_retriever
    if _layered_retriever is None:
        _layered_retriever = LayeredRetriever(methods_dir, persist_dir=data_dir)
    return _layered_retriever

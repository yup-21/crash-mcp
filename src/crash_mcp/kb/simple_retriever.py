"""Simple knowledge retriever using pattern matching (no external dependencies)."""
import os
import re
import logging
from typing import List, Dict, Optional
import yaml

from .models import AnalysisMethod, MethodLoader

logger = logging.getLogger(__name__)


class SimpleRetriever:
    """简单检索器，使用模式匹配（无需外部依赖）"""
    
    def __init__(self, methods_dir: str = "knowledge/methods"):
        self.loader = MethodLoader(methods_dir)
        self._methods: Dict[str, AnalysisMethod] = {}
        self._loaded = False
    
    def _ensure_loaded(self):
        if not self._loaded:
            self._methods = self.loader.load_all()
            self._loaded = True
    
    def search_method(self, query: str, top_k: int = 3) -> List[Dict]:
        """根据 panic 信息检索分析方法（模式匹配）"""
        self._ensure_loaded()
        
        query_lower = query.lower()
        results = []
        
        for method in self._methods.values():
            score = 0
            matched_patterns = []
            
            # 检查 triggers 模式匹配
            for trigger in method.triggers:
                pattern = trigger.get('pattern', '').lower()
                if pattern and pattern in query_lower:
                    score += 10
                    matched_patterns.append(pattern)
                elif pattern and re.search(pattern, query_lower):
                    score += 8
                    matched_patterns.append(pattern)
            
            # 检查 tags 匹配
            for tag in method.tags:
                if tag.lower() in query_lower:
                    score += 3
            
            # 检查名称/描述匹配
            if method.name.lower() in query_lower:
                score += 5
            
            words = query_lower.split()
            for word in words:
                if len(word) > 3 and word in method.description.lower():
                    score += 1
            
            if score > 0:
                results.append({
                    'id': method.id,
                    'name': method.name,
                    'description': method.description,
                    'score': score,
                    'matched_patterns': matched_patterns,
                    'steps': [{'command': s.command, 'purpose': s.purpose} for s in method.steps]
                })
        
        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
    
    def get_method(self, method_id: str) -> Optional[AnalysisMethod]:
        """获取指定方法"""
        self._ensure_loaded()
        return self._methods.get(method_id)
    
    def get_next_methods(self, output_text: str, current_method_id: str) -> List[Dict]:
        """根据输出检测下一步分析方法"""
        self._ensure_loaded()
        
        method = self._methods.get(current_method_id)
        if not method:
            return []
        
        output_lower = output_text.lower()
        suggestions = []
        
        for next_method in method.next_methods:
            condition = next_method.get('condition', '').lower()
            next_id = next_method.get('method_id', '')
            
            if condition and condition in output_lower:
                next_method_obj = self._methods.get(next_id)
                if next_method_obj:
                    suggestions.append({
                        'id': next_id,
                        'name': next_method_obj.name,
                        'reason': f"检测到: {condition}"
                    })
        
        return suggestions
    
    def list_methods(self) -> List[Dict]:
        """列出所有可用方法"""
        self._ensure_loaded()
        return [
            {'id': m.id, 'name': m.name, 'description': m.description}
            for m in self._methods.values()
        ]


# Global instance
_retriever: Optional[SimpleRetriever] = None

def get_retriever(methods_dir: str = "knowledge/methods") -> SimpleRetriever:
    """获取检索器单例"""
    global _retriever
    if _retriever is None:
        _retriever = SimpleRetriever(methods_dir)
    return _retriever

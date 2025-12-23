"""Case management for storing and retrieving analysis cases."""
import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

from .models import AnalysisCase, CaseStep

logger = logging.getLogger(__name__)


class CaseManager:
    """案例管理器"""
    
    def __init__(self, cases_dir: str = "knowledge/cases"):
        self.cases_dir = cases_dir
        os.makedirs(cases_dir, exist_ok=True)
    
    def save_case(self, case: AnalysisCase) -> str:
        """保存案例"""
        case_data = case.to_dict()
        case_data['created_at'] = datetime.now().isoformat()
        
        filepath = os.path.join(self.cases_dir, f"{case.id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved case: {case.id}")
        return case.id
    
    def load_case(self, case_id: str) -> Optional[AnalysisCase]:
        """加载案例"""
        filepath = os.path.join(self.cases_dir, f"{case_id}.json")
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return AnalysisCase(
            id=data['id'],
            title=data['title'],
            panic_signature=data['panic_signature'],
            kernel_version=data.get('kernel_version', ''),
            root_cause=data['root_cause'],
            analysis_trace=[
                CaseStep(**step) for step in data.get('analysis_trace', [])
            ],
            solution=data.get('solution', ''),
            confidence=data.get('confidence', 0.5),
            hit_count=data.get('hit_count', 0)
        )
    
    def list_cases(self) -> List[Dict]:
        """列出所有案例"""
        cases = []
        for filename in os.listdir(self.cases_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.cases_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cases.append({
                    'id': data['id'],
                    'title': data['title'],
                    'root_cause': data.get('root_cause', ''),
                    'hit_count': data.get('hit_count', 0)
                })
        return cases
    
    def search_cases(self, query: str, top_k: int = 5) -> List[Dict]:
        """简单搜索案例"""
        query_lower = query.lower()
        results = []
        
        for filename in os.listdir(self.cases_dir):
            if not filename.endswith('.json'):
                continue
            
            filepath = os.path.join(self.cases_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            score = 0
            # 检查 panic_signature 匹配
            if query_lower in data.get('panic_signature', '').lower():
                score += 10
            # 检查 root_cause 匹配
            if query_lower in data.get('root_cause', '').lower():
                score += 5
            # 检查 title 匹配
            if query_lower in data.get('title', '').lower():
                score += 3
            
            if score > 0:
                results.append({
                    'id': data['id'],
                    'title': data['title'],
                    'root_cause': data.get('root_cause', ''),
                    'solution': data.get('solution', ''),
                    'score': score
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
    
    def enhance_case(self, case_id: str, new_trace: List[CaseStep] = None, 
                     additional_info: Dict = None) -> bool:
        """增强已有案例"""
        case = self.load_case(case_id)
        if not case:
            return False
        
        case.hit_count += 1
        
        if new_trace:
            # 合并新的分析轨迹
            existing_methods = {s.method_id for s in case.analysis_trace}
            for step in new_trace:
                if step.method_id not in existing_methods:
                    case.analysis_trace.append(step)
        
        self.save_case(case)
        return True


# 全局实例
_case_manager: Optional[CaseManager] = None

def get_case_manager(cases_dir: str = "knowledge/cases") -> CaseManager:
    """获取案例管理器单例"""
    global _case_manager
    if _case_manager is None:
        _case_manager = CaseManager(cases_dir)
    return _case_manager

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import yaml
import os


@dataclass
class AnalysisStep:
    """单个分析步骤"""
    order: int
    command: str
    purpose: str
    extract: Optional[List[Dict]] = None


@dataclass
class AnalysisMethod:
    """分析方法定义"""
    id: str
    name: str
    triggers: List[Dict]
    description: str
    steps: List[AnalysisStep]
    outputs: List[Dict]
    next_methods: List[Dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def from_yaml(cls, path: str) -> "AnalysisMethod":
        """从 YAML 文件加载"""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        steps = [AnalysisStep(**s) for s in data.get('steps', [])]
        return cls(
            id=data['id'],
            name=data['name'],
            triggers=data.get('triggers', []),
            description=data.get('description', ''),
            steps=steps,
            outputs=data.get('outputs', []),
            next_methods=data.get('next_methods', []),
            tags=data.get('tags', [])
        )


@dataclass
class CaseStep:
    """案例分析步骤"""
    step_id: int
    method_id: str
    findings: str
    next_step: Optional[int] = None


@dataclass
class AnalysisCase:
    """分析案例"""
    id: str
    title: str
    panic_signature: str
    kernel_version: str
    root_cause: str
    analysis_trace: List[CaseStep]
    solution: str
    confidence: float = 0.5
    hit_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'panic_signature': self.panic_signature,
            'kernel_version': self.kernel_version,
            'root_cause': self.root_cause,
            'analysis_trace': [
                {'step_id': s.step_id, 'method_id': s.method_id, 
                 'findings': s.findings, 'next_step': s.next_step}
                for s in self.analysis_trace
            ],
            'solution': self.solution,
            'confidence': self.confidence,
            'hit_count': self.hit_count
        }


class MethodLoader:
    """分析方法加载器"""
    
    def __init__(self, methods_dir: str = "knowledge/methods"):
        self.methods_dir = methods_dir
        self._cache: Dict[str, AnalysisMethod] = {}
    
    def load_all(self) -> Dict[str, AnalysisMethod]:
        """加载所有方法"""
        if not os.path.isdir(self.methods_dir):
            return {}
        
        for filename in os.listdir(self.methods_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                path = os.path.join(self.methods_dir, filename)
                method = AnalysisMethod.from_yaml(path)
                self._cache[method.id] = method
        
        return self._cache
    
    def get(self, method_id: str) -> Optional[AnalysisMethod]:
        """获取指定方法"""
        if not self._cache:
            self.load_all()
        return self._cache.get(method_id)

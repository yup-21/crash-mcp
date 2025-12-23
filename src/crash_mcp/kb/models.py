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
class CaseNode:
    """案例树节点"""
    id: str
    fingerprint: str
    finding_summary: str
    method_used: str
    children: List['CaseNode'] = field(default_factory=list)
    solution: str = ""
    hit_count: int = 1
    failure_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'fingerprint': self.fingerprint,
            'finding_summary': self.finding_summary,
            'method_used': self.method_used,
            'children': [c.to_dict() for c in self.children],
            'solution': self.solution,
            'hit_count': self.hit_count,
            'failure_count': self.failure_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CaseNode':
        children = [cls.from_dict(c) for c in data.get('children', [])]
        return cls(
            id=data['id'],
            fingerprint=data['fingerprint'],
            finding_summary=data['finding_summary'],
            method_used=data['method_used'],
            children=children,
            solution=data.get('solution', ''),
            hit_count=data.get('hit_count', 1),
            failure_count=data.get('failure_count', 0)
        )


@dataclass
class AnalysisCase:
    """分析案例 (支持树状结构)"""
    id: str
    title: str
    panic_signature: str
    kernel_version: str
    root_cause: str
    root_node: Optional[CaseNode] = None  # New: Tree Root
    analysis_trace: List[CaseStep] = field(default_factory=list) # Keep for backward compat
    solution: str = ""
    confidence: float = 0.5
    hit_count: int = 0
    
    def to_dict(self) -> Dict:
        data = {
            'id': self.id,
            'title': self.title,
            'panic_signature': self.panic_signature,
            'kernel_version': self.kernel_version,
            'root_cause': self.root_cause,
            'solution': self.solution,
            'confidence': self.confidence,
            'hit_count': self.hit_count,
            'analysis_trace': [     # Backward compat
                {'step_id': s.step_id, 'method_id': s.method_id, 
                 'findings': s.findings, 'next_step': s.next_step}
                for s in self.analysis_trace
            ]
        }
        if self.root_node:
            data['root_node'] = self.root_node.to_dict()
        return data


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

"""Workflow engine for automated crash analysis."""
import logging
import uuid
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .simple_retriever import get_retriever
from .models import AnalysisCase, CaseStep

logger = logging.getLogger(__name__)


@dataclass
class AnalysisTrace:
    """分析轨迹记录"""
    step_id: int
    method_id: str
    method_name: str
    command: str
    output: str
    findings: str = ""
    

@dataclass  
class WorkflowState:
    """工作流状态"""
    session_id: str
    panic_text: str
    traces: List[AnalysisTrace] = field(default_factory=list)
    current_method: Optional[str] = None
    is_complete: bool = False
    

class AnalysisWorkflow:
    """分析工作流引擎"""
    
    def __init__(self, session_executor=None, methods_dir: str = "knowledge/methods"):
        """
        Args:
            session_executor: 执行命令的回调函数 (command) -> output
            methods_dir: 分析方法目录
        """
        self.executor = session_executor
        self.retriever = get_retriever(methods_dir)
        self.state: Optional[WorkflowState] = None
        self._step_counter = 0
    
    def start(self, panic_text: str, session_id: str = None) -> Dict[str, Any]:
        """开始新的分析工作流"""
        self.state = WorkflowState(
            session_id=session_id or str(uuid.uuid4()),
            panic_text=panic_text
        )
        self._step_counter = 0
        
        # 搜索匹配方法
        methods = self.retriever.search_method(panic_text, top_k=1)
        
        if not methods:
            return {
                "status": "no_method",
                "message": "未找到匹配的分析方法",
                "suggestion": "请尝试手动分析或添加新的分析方法"
            }
        
        method = methods[0]
        self.state.current_method = method['id']
        
        return {
            "status": "started",
            "session_id": self.state.session_id,
            "matched_method": {
                "id": method['id'],
                "name": method['name'],
                "score": method['score'],
                "steps": method['steps']
            },
            "message": f"匹配到分析方法: {method['name']}"
        }
    
    def execute_step(self, command: str, purpose: str = "") -> Dict[str, Any]:
        """执行单个分析步骤"""
        if not self.state:
            return {"status": "error", "message": "工作流未启动"}
        
        if not self.executor:
            return {"status": "error", "message": "未配置命令执行器"}
        
        self._step_counter += 1
        
        try:
            output = self.executor(command)
        except Exception as e:
            output = f"Error: {str(e)}"
        
        trace = AnalysisTrace(
            step_id=self._step_counter,
            method_id=self.state.current_method or "manual",
            method_name=purpose,
            command=command,
            output=output
        )
        self.state.traces.append(trace)
        
        # 检查是否有后续方法建议
        suggestions = []
        if self.state.current_method:
            suggestions = self.retriever.get_next_methods(output, self.state.current_method)
        
        return {
            "status": "executed",
            "step_id": self._step_counter,
            "command": command,
            "output": output,
            "next_suggestions": suggestions
        }
    
    def switch_method(self, method_id: str) -> Dict[str, Any]:
        """切换到新的分析方法"""
        if not self.state:
            return {"status": "error", "message": "工作流未启动"}
        
        method = self.retriever.get_method(method_id)
        if not method:
            return {"status": "error", "message": f"方法 {method_id} 不存在"}
        
        self.state.current_method = method_id
        
        return {
            "status": "switched",
            "method": {
                "id": method.id,
                "name": method.name,
                "steps": [{"command": s.command, "purpose": s.purpose} for s in method.steps]
            }
        }
    
    def get_trace(self) -> List[Dict]:
        """获取分析轨迹"""
        if not self.state:
            return []
        
        return [
            {
                "step": t.step_id,
                "method": t.method_id,
                "command": t.command,
                "output_preview": t.output[:200] + "..." if len(t.output) > 200 else t.output
            }
            for t in self.state.traces
        ]
    
    def complete(self, root_cause: str, solution: str = "") -> AnalysisCase:
        """完成分析并生成案例"""
        if not self.state:
            raise ValueError("工作流未启动")
        
        self.state.is_complete = True
        
        case = AnalysisCase(
            id=str(uuid.uuid4()),
            title=f"Analysis: {self.state.panic_text[:50]}...",
            panic_signature=self.state.panic_text,
            kernel_version="",  # 可从 sys 输出提取
            root_cause=root_cause,
            analysis_trace=[
                CaseStep(
                    step_id=t.step_id,
                    method_id=t.method_id,
                    findings=t.findings or t.output[:100],
                    next_step=t.step_id + 1 if t.step_id < len(self.state.traces) else None
                )
                for t in self.state.traces
            ],
            solution=solution
        )
        
        return case


# 全局工作流实例
_workflows: Dict[str, AnalysisWorkflow] = {}

def get_workflow(session_id: str) -> Optional[AnalysisWorkflow]:
    """获取工作流实例"""
    return _workflows.get(session_id)

def create_workflow(session_id: str, executor=None, methods_dir: str = "knowledge/methods") -> AnalysisWorkflow:
    """创建新工作流"""
    workflow = AnalysisWorkflow(executor, methods_dir)
    _workflows[session_id] = workflow
    return workflow

"""
Domain Schema (数据模型)
定义 crash-mcp 的核心数据结构。
Ported from vmcore-analyzer.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
import re


class PanicType(str, Enum):
    """Panic 类型枚举"""
    KERNEL_BUG = "Kernel BUG"
    PANIC = "Panic"
    SOFT_LOCKUP = "Soft Lockup"
    HARD_LOCKUP = "Hard Lockup"
    RCU_STALL = "RCU Stall"
    HUNG_TASK = "Hung Task"
    OOM = "Out of Memory"
    OOPS = "Oops"
    GPF = "General Protection Fault"
    NPD = "Null Pointer Dereference"
    UNKNOWN = "Unknown"


@dataclass
class PanicFingerprint:
    """
    Panic 指纹 - 用于知识库检索的结构化特征
    
    支持的字段：
    - panic_type: Panic 类型（必须）
    - failing_function: 失败函数名（必须）
    - failing_module: 失败模块名（可选）
    - top_stack_frames: 顶部栈帧列表（可选）
    - lock_type: 锁类型（可选，如 mutex, rwsem）
    """
    panic_type: str
    failing_function: str
    failing_module: Optional[str] = None
    top_stack_frames: List[str] = field(default_factory=list)
    kernel_version_major: str = ""
    lock_type: Optional[str] = None
    panic_message: Optional[str] = None
    
    def get_stack_frames(self) -> List[str]:
        """获取栈帧列表"""
        return self.top_stack_frames
    
    def match_score(self, other: "PanicFingerprint") -> float:
        """
        计算与另一个指纹的匹配分数 (0.0 - 1.0)
        """
        score = 0.0
        weights = {
            "failing_function": 0.4,
            "panic_type": 0.2,
            "stack_frames": 0.3,
            "kernel_version_major": 0.1
        }
        
        # 快速完全匹配检测
        if (self.failing_function == other.failing_function and
            self.panic_type == other.panic_type and
            self.top_stack_frames == other.top_stack_frames):
            return 1.0
        
        # 函数名完全匹配
        if self.failing_function and other.failing_function:
            if self.failing_function == other.failing_function:
                score += weights["failing_function"]
            elif self.failing_function in other.failing_function or other.failing_function in self.failing_function:
                score += weights["failing_function"] * 0.5
        
        # Panic 类型匹配
        if self.panic_type == other.panic_type:
            score += weights["panic_type"]
        
        # 栈帧交集
        if self.top_stack_frames and other.top_stack_frames:
            common = set(self.top_stack_frames) & set(other.top_stack_frames)
            if common:
                ratio = len(common) / max(len(self.top_stack_frames), len(other.top_stack_frames))
                score += weights["stack_frames"] * ratio
        
        # 内核版本主版本匹配
        if self.kernel_version_major and other.kernel_version_major:
            if self.kernel_version_major == other.kernel_version_major:
                score += weights["kernel_version_major"]
        
        return score
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "panic_type": self.panic_type,
            "failing_function": self.failing_function,
            "failing_module": self.failing_module,
            "top_stack_frames": self.top_stack_frames,
            "kernel_version_major": self.kernel_version_major,
            "lock_type": self.lock_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PanicFingerprint":
        """从字典创建"""
        return cls(
            panic_type=data.get("panic_type", PanicType.UNKNOWN.value),
            failing_function=data.get("failing_function", ""),
            failing_module=data.get("failing_module"),
            top_stack_frames=data.get("top_stack_frames", []),
            kernel_version_major=data.get("kernel_version_major", ""),
            lock_type=data.get("lock_type")
        )


def extract_panic_fingerprint(panic_info: str, stack_trace: str = "") -> PanicFingerprint:
    """
    从 Panic 信息和调用栈中提取结构化指纹
    """
    # 1. 识别 Panic 类型
    panic_type = PanicType.UNKNOWN.value
    panic_lower = panic_info.lower()
    
    if "kernel bug" in panic_lower or "bug:" in panic_lower:
        panic_type = PanicType.KERNEL_BUG.value
    elif "hung_task" in panic_lower or "blocked for more than" in panic_lower:
        panic_type = PanicType.HUNG_TASK.value
    elif "soft lockup" in panic_lower:
        panic_type = PanicType.SOFT_LOCKUP.value
    elif "hard lockup" in panic_lower:
        panic_type = PanicType.HARD_LOCKUP.value
    elif "rcu" in panic_lower and ("stall" in panic_lower or "callback" in panic_lower):
        panic_type = PanicType.RCU_STALL.value
    elif "out of memory" in panic_lower or "oom" in panic_lower:
        panic_type = PanicType.OOM.value
    elif "null pointer" in panic_lower:
        panic_type = PanicType.NPD.value
    elif "general protection" in panic_lower:
        panic_type = PanicType.GPF.value
    elif "oops" in panic_lower:
        panic_type = PanicType.OOPS.value
    elif "panic" in panic_lower:
        panic_type = PanicType.PANIC.value
    
    # 2. 提取失败函数
    failing_function = ""
    
    rip_match = re.search(r'RIP:\s*\S+:\s*(\w+)\+', panic_info)
    if rip_match:
        failing_function = rip_match.group(1)
    
    if not failing_function:
        at_match = re.search(r'at\s+(\w+)\+', panic_info)
        if at_match:
            failing_function = at_match.group(1)
    
    if not failing_function:
        in_match = re.search(r'in\s+(\w+)[\s\+\[]', panic_info)
        if in_match:
            failing_function = in_match.group(1)
    
    # 3. 提取模块名
    failing_module = None
    mod_match = re.search(r'\[(\w+)\]', panic_info)
    if mod_match:
        module_name = mod_match.group(1)
        if module_name not in ["error", "warn", "info", "debug", "Tainted"]:
            failing_module = module_name
    
    # 4. 提取栈帧
    top_stack_frames = []
    combined_text = panic_info + "\n" + stack_trace
    
    frame_pattern = re.compile(r'#\d+\s+\[.*?\]\s+(\w+)\+')
    frames = frame_pattern.findall(combined_text)
    if frames:
        top_stack_frames = frames[:5]
    
    if not top_stack_frames:
        simple_pattern = re.compile(r'\s(\w{3,})\+0x[0-9a-f]+')
        frames = simple_pattern.findall(combined_text)
        if frames:
            noise = {"panic", "die", "oops", "warn", "bug", "trace", "print"}
            top_stack_frames = [f for f in frames if f.lower() not in noise][:5]
    
    # 5. 提取内核版本
    kernel_version_major = ""
    ver_match = re.search(r'(\d+\.\d+)\.\d+', panic_info)
    if ver_match:
        kernel_version_major = ver_match.group(1)
    
    return PanicFingerprint(
        panic_type=panic_type,
        failing_function=failing_function,
        failing_module=failing_module,
        top_stack_frames=top_stack_frames,
        kernel_version_major=kernel_version_major,
        panic_message=panic_info[:500] if panic_info else None
    )

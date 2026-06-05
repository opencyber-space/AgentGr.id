from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

@dataclass
class AgentTask:
    task_id: str
    job_data: Dict[str, Any] = field(default_factory=dict)
    output_ptr: Dict[str, Any] = field(default_factory=dict)
    task_metadata: Dict[str, Any] = field(default_factory=dict)
    skip: bool = field(default=False)

    def to_dict(self):
        return asdict(self)

@dataclass
class AgentPreResult:
    job: AgentTask
    task_id: str
    extra_data: Dict[str, Any] = field(default_factory=dict)
    is_error: bool = False
    error_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentContext:
    env: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentResult:
    task_id: str
    job_output: Dict[str, Any] = field(default_factory=dict)
    job_output_metadata: Dict[str, Any] = field(default_factory=dict)
    job_output_trace_data: Dict[str, Any] = field(default_factory=dict)
    is_error: bool = False
    skip: bool = False
    error_data: Dict[str, Any] = field(default_factory=dict)
# agents/base_agent.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

Status = Literal["success", "failed", "pending"]

@dataclass
class Task:
    task_id: str
    agent: str
    type: str
    session_id: str
    customer_id: Optional[str]
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ErrorDetail:
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NextAction:
    type: str  # e.g. "ASK_CUSTOMER", "CALL_AGENT"
    message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskResult:
    task_id: str
    agent: str
    status: Status
    payload: Dict[str, Any] = field(default_factory=dict)
    errors: List[ErrorDetail] = field(default_factory=list)
    next_actions: List[NextAction] = field(default_factory=list)

class BaseAgent(ABC):
    name: str

    @abstractmethod
    def handle(self, task: Task) -> TaskResult:
        ...

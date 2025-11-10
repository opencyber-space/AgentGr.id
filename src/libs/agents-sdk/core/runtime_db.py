import requests
from typing import Optional
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class RuntimeSubject:
    runtime_subject_id: str
    subject_id: str
    runtime_info: Dict[str, Any] = field(default_factory=dict)
    runtime_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runtime_subject_id": self.runtime_subject_id,
            "subject_id": self.subject_id,
            "runtime_info": self.runtime_info,
            "runtime_status": self.runtime_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeSubject":
        return cls(
            runtime_subject_id=data.get("runtime_subject_id", ""),
            subject_id=data.get("subject_id", ""),
            runtime_info=data.get("runtime_info", {}) or {},
            runtime_status=data.get("runtime_status", "") or "",
        )


class RuntimeSubjectClient:
    def __init__(self, base_url: str, session: Optional[requests.Session] = None):
       
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def get_runtime_subject(self, runtime_subject_id: str) -> RuntimeSubject:
      
        url = f"{self.base_url}/api/runtime-subjects/{runtime_subject_id}"
        resp = self.session.get(url)
        resp.raise_for_status()

        payload = resp.json()
        if not payload.get("success"):
            raise ValueError(payload.get("message", "Unknown error"))
        data = payload.get("data", {})
        return RuntimeSubject.from_dict(data)
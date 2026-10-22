from __future__ import annotations

import os
import requests
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from .runtime_db import RuntimeSubject, RuntimeSubjectClient
from .types import AgentTask

Message = Dict[str, Any]

class TaskInitiatorError(Exception):
    """Base error for TaskInitiator client."""


class APIRequestError(TaskInitiatorError):
    """Network / HTTP error (non-2xx, not a controlled 429)."""


class BlockedError(TaskInitiatorError):

    def __init__(self, stage: Optional[str], reason: Optional[Dict[str, Any]]):
        self.stage = stage
        self.reason = reason or {}
        msg = f"Request blocked at stage={stage}. Reason={self.reason}"
        super().__init__(msg)


# ---------- Data Models ----------
@dataclass
class PreProcessResult:
  
    status: str
    stage: Optional[str] = None
    reason: Dict[str, Any] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreProcessResult":
        return cls(
            status=data.get("status", ""),
            stage=data.get("stage"),
            reason=(data.get("reason") or {}) if isinstance(data.get("reason"), dict) else {},
            messages=[m for m in (data.get("messages") or []) if isinstance(m, dict)],
        )


@dataclass
class DryRunResult:
    allowed: bool                 
    stage: Optional[str] = None   
    reason: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubmitAck:
    accepted: bool                # True if 202 accepted
    result: Optional[PreProcessResult] = None
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------- Client ----------
class TaskInitiator:
   

    def __init__(
        self,
        base_url: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 15.0,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.default_headers = default_headers or {}

    # ----- Public API -----
    def healthz(self) -> bool:
        url = f"{self.base_url}/healthz"
        r = self.session.get(url, headers=self.default_headers)
        if r.status_code != 200:
            raise APIRequestError(f"healthz failed with HTTP {r.status_code}: {r.text}")
        data = r.json()
        return bool(data.get("ok"))

    def dry_run(self, *, session_id: str, message_data: Message, headers: Optional[Dict[str, str]] = None) -> DryRunResult:
       
        url = f"{self.base_url}/dryRun"
        payload = {"session_id": session_id, "message_data": message_data}

        r = self.session.post(
            url, json=payload,
            headers={**self.default_headers, **(headers or {})}
        )

        # Blocked path (server returns stage/reason)
        if r.status_code == 429:
            try:
                data = r.json()
            except Exception:
                data = {}
            raise BlockedError(stage=data.get("stage"), reason=data.get("reason"))

        # Other non-2xx
        if not r.ok:
            raise APIRequestError(f"dryRun failed with HTTP {r.status_code}: {r.text}")

        # Success path
        data = r.json()
        return DryRunResult(allowed=bool(data.get("success", False)))

    def submit_task(self, *, session_id: str, message_data: Message, headers: Optional[Dict[str, str]] = None) -> SubmitAck:
       
        url = f"{self.base_url}/submitTask"

        r = self.session.post(
            url, json=message_data,
            headers={**self.default_headers, **(headers or {})}
        )

        if r.status_code == 429:
            try:
                data = r.json()
            except Exception:
                data = {}
            raise BlockedError(stage=data.get("stage"), reason=data.get("reason"))

        if r.status_code != 202:
            raise APIRequestError(f"submitTask expected 202, got {r.status_code}: {r.text}")

        data = r.json()
        result = data.get("result") or {}
        pp = PreProcessResult.from_dict(result) if isinstance(result, dict) else None
        return SubmitAck(accepted=True, result=pp, raw=data)


class AgentDirect:

    def __init__(self, runtime_db_url: str) -> None:
        self.runtime_db_url = runtime_db_url
        self.runtime_db = RuntimeSubjectClient(base_url=self.runtime_db_url)
    
    def submit(self, to: str, session_id: str, task: AgentTask, job_data: dict):
        try:

            r_t = self.runtime_db.get_runtime_subject(to)
            executor_url = r_t.runtime_info["executor"]

            task_initiator = TaskInitiator(executor_url, timeout=0)
            task_initiator.submit_task(
                session_id=session_id,
                message_data={
                    "event_type": "task",
                    "task_id": task.task_id,
                    "task": job_data,
                    "session_id": session_id,
                    "origin": task.output_ptr
                }
            )
            
            
        except Exception as e:
            raise e

from __future__ import annotations

import os
import requests
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from .runtime_db import RuntimeSubject, RuntimeSubjectClient

Message = Dict[str, Any]

REDIS_PUBLIC_HOST = os.getenv("REDIS_PUBLIC_HOST")
REDIS_PUBLIC_PORT = int(os.getenv("REDIS_PUBLIC_PORT", "6379"))

# ---------- Exceptions ----------
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
        r = self.session.get(url, headers=self.default_headers, timeout=self.timeout)
        if r.status_code != 200:
            raise APIRequestError(f"healthz failed with HTTP {r.status_code}: {r.text}")
        data = r.json()
        return bool(data.get("ok"))

    def dry_run(self, *, session_id: str, message_data: Message, headers: Optional[Dict[str, str]] = None) -> DryRunResult:
       
        url = f"{self.base_url}/dryRun"
        payload = {"session_id": session_id, "message_data": message_data}

        r = self.session.post(
            url, json=payload,
            headers={**self.default_headers, **(headers or {})},
            timeout=self.timeout,
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
            headers={**self.default_headers, **(headers or {})},
            timeout=self.timeout,
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



def push_task_to_agent(
    *,
    runtime_db_base_url: str,
    runtime_subject_id: str,
    session_id: str,
    task_id: str,
    task_data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
) -> SubmitAck:
    
    created_local_session = False
    s = session
    if s is None:
        s = requests.Session()
        created_local_session = True

    try:
        rs_client = RuntimeSubjectClient(runtime_db_base_url, session=s)
        rs = rs_client.get_runtime_subject(runtime_subject_id)

        # 2) Extract executor URL
        executor_url = rs.runtime_info.get("executor")
        if not executor_url or not isinstance(executor_url, str):
            raise ValueError(
                f"Missing or invalid executor URL in runtime_info['executor'] for runtime_subject_id={runtime_subject_id}"
            )

        initiator = TaskInitiator(
            executor_url,
            session=s,
            timeout=None,
        )

        ack = initiator.submit_task(
            session_id=session_id,
            message_data={
                "event_type": "task",
                "task_id": task_id,
                "task": task_data,
                "session_id": session_id,
                "origin": {
                    "type": "redis",
                    "exchange_id": "delegate",
                    "host": REDIS_PUBLIC_HOST,
                    "port": REDIS_PUBLIC_PORT,
                    "output_queue": session_id
                }
            },
            headers=headers,
        )
        return ack
    finally:
        if created_local_session:
            s.close()

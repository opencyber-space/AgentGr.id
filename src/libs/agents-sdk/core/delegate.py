import logging
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class AgentDelegatorError(Exception):
    pass


class AgentDelegator:
   
    def __init__(self, base_url: str):
        if not base_url:
            raise ValueError("base_url is required")
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/api/submit-and-wait"

    def submit_and_wait(
        self,
        *,
        subject_id: str,
        session_id: str,
        task_id: str,
        task_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        redis_url: Optional[str] = None,
    ) -> Dict[str, Any]:


        session = requests.Session()
        payload = {
            "subject_id": subject_id,
            "session_id": session_id,
            "task_id": task_id,
            "task_data": task_data,
        }
        if headers:
            payload["headers"] = headers
        if redis_url:
            payload["redis_url"] = redis_url

        try:
            log.info("Submitting task to %s, task_data=%s", self.endpoint, payload)
            resp = session.post(self.endpoint, json=payload)
            resp.raise_for_status()
        except Exception as e:
            log.exception("Failed to submit: %s", e)
            raise AgentDelegatorError(f"Request failed: {e}") from e

        try:
            data = resp.json()
        except ValueError:
            raise AgentDelegatorError("Invalid JSON response")

        if not data.get("success"):
            msg = data.get("message", "unknown error")
            raise AgentDelegatorError(f"Server returned error: {msg}")

        return data

    def close(self):
        self.session.close()

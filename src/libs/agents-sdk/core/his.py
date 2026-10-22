import time
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
import requests
import os


logger = logging.getLogger("his-client")


# ------------------- DATA CLASS -------------------

@dataclass
class SubjectResponse:
    id: str
    subject_id: str
    input_data: Dict[str, Any]
    response_data: Dict[str, Any]
    status: str
    creation_time: int
    response_time: Optional[int]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubjectResponse":
        return cls(
            id=data["id"],
            subject_id=data["subject_id"],
            input_data=data.get("input_data", {}) or {},
            response_data=data.get("response_data", {}) or {},
            status=data.get("status", ""),
            creation_time=data.get("creation_time", 0),
            response_time=data.get("response_time"),
        )



class HisClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: int = 10,
        poll_interval: float = 1.0,
        max_wait: Optional[int] = 300,
    ):
        
        self.base_url = base_url.rstrip("/")

        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait


    def submit(
        self,
        *,
        input_data: Dict[str, Any],
        status: str = "pending",
    ) -> SubjectResponse:
        
        payload = {
            "subject_id": os.getenv("SUBJECT_ID"),
            "input_data": input_data,
            "status": status.lower(),
        }

        r = requests.post(
            f"{self.base_url}/subject-responses",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()

        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("error"))

        return SubjectResponse.from_dict(data["data"])


    def submit_and_wait(
        self,
        *,
        input_data: Dict[str, Any],
        status: str = "pending",
        wait_timeout: Optional[int] = None,
    ) -> SubjectResponse:
        
        obj = self.submit(
            input_data=input_data,
            status=status,
        )

        return self._poll_until_completed(
            response_id=obj.id,
            wait_timeout=wait_timeout,
        )


    def check_and_get_response(
        self,
        response_id: str,
    ) -> Optional[SubjectResponse]:
        
        obj = self._get_by_id(response_id)

        if obj.status.lower() == "completed":
            return obj

        return None


    def _get_by_id(self, response_id: str) -> SubjectResponse:
        r = requests.get(
            f"{self.base_url}/subject-responses/{response_id}",
            timeout=self.timeout,
        )
        r.raise_for_status()

        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("error"))

        return SubjectResponse.from_dict(data["data"])

    def _poll_until_completed(
        self,
        response_id: str,
        *,
        wait_timeout: Optional[int] = None,
    ) -> SubjectResponse:
        start = time.time()

        if wait_timeout is None:
            timeout = self.max_wait
        elif wait_timeout < 0:
            timeout = None  
        else:
            timeout = wait_timeout

        while True:
            obj = self._get_by_id(response_id)

            if obj.status.lower() == "completed":
                return obj

            # Timeout check (only if timeout is enabled)
            if timeout is not None and (time.time() - start) > timeout:
                raise TimeoutError(
                    f"Timeout waiting for response_id={response_id}"
                )

            time.sleep(self.poll_interval)

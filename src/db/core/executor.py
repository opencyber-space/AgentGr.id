import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExecutorsClient:
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30) -> None:
       
        self.base_url = base_url or os.getenv("EXECUTORS_API_URL", "http://localhost:5000")
        self.timeout = timeout

    def create_executor(self, subject_id: str, data: dict) -> Dict[str, Any]:
        
        url = f"{self.base_url}/executors/{subject_id}"
        try:
            resp = requests.post(url, timeout=self.timeout, json=data)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Error creating executor for {subject_id}: {e}")
            return {"success": False, "error": str(e)}

    def remove_executor(self, subject_id: str) -> Dict[str, Any]:
        
        url = f"{self.base_url}/executors/{subject_id}"
        try:
            resp = requests.delete(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Error removing executor for {subject_id}: {e}")
            return {"success": False, "error": str(e)}
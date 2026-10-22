import requests
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class ExchangeClient:
    def __init__(self, base_url: str, timeout: int = 10) -> None:
       
        self.base_url = (base_url or os.getenv("JOB_EXCHANGE_API_URL")).rstrip("/")
        self.timeout = timeout

    def set_job_result(
        self,
        exchange_id: str,
        result_body: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
      
        url = f"{self.base_url}/exchange/set-result/{exchange_id}"
        try:
            resp = requests.post(url, json=result_body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"[ExchangeClient] Failed to set job result for {exchange_id}: {e}")
            return {"success": False, "error": str(e)}
import logging
import os
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class AgentsFunctionsGraphError(Exception):
    pass


class AgentsFunctionsGraph:

    def __init__(self, base_url: str = "", timeout: float = 30.0) -> None:
        if not base_url:
            base_url = os.environ.get("POLICY_DB_URL")
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/graph/execute_graph"
        self.timeout = timeout

    def execute_graph(
        self,
        graph_uri: str,
        input_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "graph_uri": graph_uri,
            "input_data": input_data,
        }
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        try:
            log.info("Executing graph %s at %s", graph_uri, self.endpoint)
            resp = requests.post(
                self.endpoint,
                json=payload,
                headers=req_headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.exception("Failed to execute graph %s: %s", graph_uri, e)
            raise AgentsFunctionsGraphError(f"Request failed: {e}") from e

        try:
            return resp.json()
        except ValueError:
            raise AgentsFunctionsGraphError("Invalid JSON response")

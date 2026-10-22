import json
from typing import Any, Dict, List, Optional, Union

import requests
from requests import Response


class InferenceServerRegistryError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class InferenceServerRegistryClient:
  
    def __init__(self, base_url: str, default_headers: Optional[Dict[str, str]] = None, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.default_headers = default_headers or {"Content-Type": "application/json"}

    def query_inference_servers(self, query_filter: Optional[Dict[str, Any]] = None) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
      
        url = f"{self.base_url}/inference_servers"
        headers = dict(self.default_headers)

        try:
            resp: Response = self.session.post(url, data=json.dumps(query_filter or {}), headers=headers)
        except Exception as e:
            raise InferenceServerRegistryError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            raise InferenceServerRegistryError(f"HTTP {resp.status_code}", status_code=resp.status_code, response_text=_safe_text(resp))

        try:
            payload = resp.json()
        except Exception:
            raise InferenceServerRegistryError("Response not valid JSON", status_code=resp.status_code, response_text=_safe_text(resp))

        if not payload.get("success", False):
            raise InferenceServerRegistryError(f"Server error: {payload.get('error')}", status_code=resp.status_code, response_text=_safe_text(resp))

        # Return `data` directly
        return payload.get("data")

    def get_inference_server(self, server_id: str) -> Dict[str, Any]:
     
        url = f"{self.base_url}/inference_server/{server_id}"
        headers = dict(self.default_headers)
        headers.pop("Content-Type", None)  # not needed for GET

        try:
            resp: Response = self.session.get(url, headers=headers)
        except Exception as e:
            raise InferenceServerRegistryError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            raise InferenceServerRegistryError(f"HTTP {resp.status_code}", status_code=resp.status_code, response_text=_safe_text(resp))

        try:
            payload = resp.json()
        except Exception:
            raise InferenceServerRegistryError("Response not valid JSON", status_code=resp.status_code, response_text=_safe_text(resp))

        if not payload.get("success", False):
            raise InferenceServerRegistryError(f"Server error: {payload.get('error')}", status_code=resp.status_code, response_text=_safe_text(resp))

        # Return `data` directly
        return payload.get("data")


def _safe_text(resp: Response) -> str:
    try:
        return resp.text
    except Exception:
        try:
            return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return "<unavailable>"

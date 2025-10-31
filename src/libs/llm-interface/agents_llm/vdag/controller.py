import requests
from requests import Response
from typing import Any, Dict, List, Optional


class vDAGControllerRegistryError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class vDAGControllerRegistryClient:
   

    def __init__(self, base_url: str, default_headers: Optional[Dict[str, str]] = None, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.default_headers = default_headers or {}

    def get_vdag(self, vdag_uri: str) -> Dict[str, Any]:
        
        url = f"{self.base_url}/vdag/{vdag_uri}"
        headers = dict(self.default_headers)

        try:
            resp: Response = self.session.get(url, headers=headers)
        except Exception as e:
            raise vDAGControllerRegistryError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            raise vDAGControllerRegistryError(f"HTTP {resp.status_code}", status_code=resp.status_code, response_text=_safe_text(resp))

        try:
            payload = resp.json()
        except Exception:
            raise vDAGControllerRegistryError("Response not valid JSON", status_code=resp.status_code, response_text=_safe_text(resp))

        if not payload.get("success", False):
            raise vDAGControllerRegistryError(f"Server error: {payload.get('error')}", status_code=resp.status_code, response_text=_safe_text(resp))

        return payload.get("data")

    def list_vdag_controllers_by_vdag_uri(self, vdag_uri: str) -> List[Dict[str, Any]]:
      
        url = f"{self.base_url}/vdag-controllers/by-vdag-uri/{vdag_uri}"
        headers = dict(self.default_headers)

        try:
            resp: Response = self.session.get(url, headers=headers)
        except Exception as e:
            raise vDAGControllerRegistryError(f"Request failed: {e}") from e

        if not (200 <= resp.status_code < 300):
            raise vDAGControllerRegistryError(f"HTTP {resp.status_code}", status_code=resp.status_code, response_text=_safe_text(resp))

        try:
            payload = resp.json()
        except Exception:
            raise vDAGControllerRegistryError("Response not valid JSON", status_code=resp.status_code, response_text=_safe_text(resp))

        if not payload.get("success", False):
            raise vDAGControllerRegistryError(f"Server error: {payload.get('error')}", status_code=resp.status_code, response_text=_safe_text(resp))

        return payload.get("data")


def _safe_text(resp: Response) -> str:
    try:
        return resp.text
    except Exception:
        try:
            return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return "<unavailable>"

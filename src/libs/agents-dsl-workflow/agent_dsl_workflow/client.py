import requests
from typing import Optional, Dict, Any, List


class WorkflowDBError(Exception):
    pass


class WorkflowDB:

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _handle_response(self, resp: requests.Response) -> Any:
        try:
            data = resp.json()
        except Exception:
            raise WorkflowDBError(f"Invalid JSON response: {resp.text}")

        if not resp.ok or not data.get("success", False):
            raise WorkflowDBError(data.get("message") or data.get("error") or resp.text)

        return data.get("data")

    def get_workflow(self, workflow_uri: str) -> Dict[str, Any]:

        url = f"{self.base_url}/api/workflows/{workflow_uri}"
        resp = requests.get(url, timeout=self.timeout)

        return self._handle_response(resp)

  

    def replace_workflow(self, workflow_uri: str, workflow_data: Dict[str, Any]) -> Dict[str, Any]:

        url = f"{self.base_url}/api/workflows/{workflow_uri}"

        resp = requests.put(
            url,
            json=workflow_data,
            timeout=self.timeout,
        )

        return self._handle_response(resp)


    def update_workflow(
        self,
        workflow_uri: str,
        update_fields: Dict[str, Any],
    ) -> Dict[str, Any]:

        url = f"{self.base_url}/api/workflows/{workflow_uri}"

        payload = {
            "update": update_fields
        }

        resp = requests.patch(
            url,
            json=payload,
            timeout=self.timeout,
        )

        return self._handle_response(resp)

   
    def delete_workflow(self, workflow_uri: str) -> bool:

        url = f"{self.base_url}/api/workflows/{workflow_uri}"

        resp = requests.delete(
            url,
            timeout=self.timeout,
        )

        self._handle_response(resp)

        return True

   

    def list_workflows(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:

        url = f"{self.base_url}/api/workflows"

        params = {
            "limit": limit,
            "skip": skip,
        }

        resp = requests.get(
            url,
            params=params,
            timeout=self.timeout,
        )

        return self._handle_response(resp)

    def query_workflows(
        self,
        query: Dict[str, Any],
        *,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:

        url = f"{self.base_url}/api/workflows/query"

        payload = {
            "query": query,
            "projection": projection,
            "sort": sort,
            "limit": limit,
            "skip": skip,
        }

        resp = requests.post(
            url,
            json=payload,
            timeout=self.timeout,
        )

        return self._handle_response(resp)
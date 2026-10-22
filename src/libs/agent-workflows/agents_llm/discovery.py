import requests
from typing import Any, Dict, Optional


class BlockSearchClient:

    def __init__(
        self,
        base_url: str,
        *,
        template_uri: str = "Parser/V1",
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.template_uri = template_uri
        self.session = session or requests.Session()

    def search(
        self,
        *,
        policyRuleURI: str,
        filter: Dict[str, Any],
        policy_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:

        policy_params = policy_params or {}

        payload = {
            "header": {
                "templateUri": self.template_uri,
                "parameters": {}
            },
            "body": {
                "values": {
                    "matchType": "block",
                    "rankingPolicyRule": {
                        "values": {
                            "policyRuleURI": policyRuleURI,
                            "settings": {},
                            "parameters": {
                                **policy_params,
                                "filterRule": {
                                    "matchType": "block",
                                    "filter": filter
                                }
                            }
                        }
                    }
                }
            }
        }

        url = f"{self.base_url}/api/search"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        resp = self.session.post(url, json=payload, headers=req_headers)
        resp.raise_for_status()
        return resp.json()


    def filter_query(
        self,
        *,
        filter: Dict[str, Any],
        match_type: str = "block",
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:

        payload = {
            "header": {"templateUri": self.template_uri, "parameters": {}},
            "body": {
                "values": {
                    "matchType": match_type,
                    "filter": filter,
                }
            },
        }

        url = f"{self.base_url}/api/filter"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        resp = self.session.post(url, json=payload, headers=req_headers)
        resp.raise_for_status()
        return resp.json()

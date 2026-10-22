from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests


class DeployerClient:
    """HTTP client for the deployer /instances API."""

    def __init__(self, base_url: str, *, timeout: int = 30, logger: Optional[logging.Logger] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._log = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------ #
    # Public methods                                                       #
    # ------------------------------------------------------------------ #

    def create_instances(
        self,
        subject_id: str,
        count: int,
        *,
        meshes: Optional[Dict[str, Any]] = None,
        delegate_api_url: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Deploy `count` agent instances for `subject_id`.

        Returns the list of per-instance deployment results from the deployer.
        Raises RuntimeError on a non-2xx response.
        """
        payload: Dict[str, Any] = {
            "subject_id": subject_id,
            "count": count,
            "meshes": meshes or {},
            "delegate_api_url": delegate_api_url,
        }
        self._log.info("DeployerClient.create_instances subject=%s count=%d", subject_id, count)
        resp = requests.post(f"{self.base_url}/instances", json=payload, timeout=self.timeout)
        self._raise_for_status(resp, "create_instances")
        data = resp.json()
        return data.get("instances", [])

    def remove_instances(
        self,
        subject_id: str,
        instance_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Remove the given agent instances for `subject_id`.

        Returns a list of {instance_id, ok} dicts.
        Raises RuntimeError on a non-2xx response.
        """
        payload: Dict[str, Any] = {
            "subject_id": subject_id,
            "instance_ids": instance_ids,
        }
        self._log.info(
            "DeployerClient.remove_instances subject=%s ids=%s", subject_id, instance_ids
        )
        resp = requests.delete(f"{self.base_url}/instances", json=payload, timeout=self.timeout)
        self._raise_for_status(resp, "remove_instances")
        data = resp.json()
        return data.get("results", [])

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _raise_for_status(self, resp: requests.Response, op: str) -> None:
        if not resp.ok:
            body = resp.text[:300]
            raise RuntimeError(
                f"DeployerClient.{op} failed: HTTP {resp.status_code} — {body}"
            )

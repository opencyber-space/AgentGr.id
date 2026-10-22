import os
import logging
from typing import Optional

import requests
from .schema import Subject  


class SubjectDBClient:

    def __init__(self, base_url: Optional[str] = None, timeout: int = 10) -> None:
        self.base_url = base_url or os.getenv("SUBJECT_DB_URL")
        if not self.base_url:
            raise ValueError("SUBJECTS_DB_URL is not set in environment or passed explicitly")

        self.timeout = timeout
        self.session = requests.Session()
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_subject(self, subject_id: str) -> Optional[Subject]:
       
        url = f"{self.base_url}/api/subjects/{subject_id}"
        try:
            self.logger.debug("GET %s", url)
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()

            if payload.get("success") and payload.get("data"):
                return Subject.from_dict(payload["data"])
            return None
        except requests.RequestException as e:
            self.logger.error("Failed to fetch subject %s: %s", subject_id, e)
            raise

    def health_check(self) -> bool:
        
        try:
            resp = self.session.get(self.base_url, timeout=self.timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False


class SubjectUtils:

    @staticmethod
    def get_policy_by_type(policy_type: str, subject: Subject):
        policies = subject.integrations.policies
        for policy in policies:
            if policy.policy_type == policy_type:
                return policy
        return None
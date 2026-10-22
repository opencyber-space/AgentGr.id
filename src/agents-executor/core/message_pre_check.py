import os
from typing import Any, Dict, Optional, Tuple

from .policy_base import PoliciesManager

class MessagePreChecker:
  
    NAME = "message_prechecker"

    def __init__(self, policies: "PoliciesManager") -> None:
        self.policies = policies
        try:
            self.policies.add_policy(self.NAME, injects={})
        except Exception:
            pass

    def default_function(self, data):
        return {"allowed": True}

    def check(self, session_id: str, message_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        
        payload = {"session_id": session_id, "message_data": message_data}

        try:
            result = self.policies.execute(self.NAME, payload, self.default_function)
        except KeyError:
            return True, None
        except Exception:
            return True, None

        if isinstance(result, dict):
            allowed = bool(result.get("allowed", True))
            if allowed:
                return True, None
            reason = result.get("reason")
            return False, reason if isinstance(reason, dict) else {}

        if isinstance(result, bool):
            return (result, None) if result else (False, {})

        return True, None

    def is_allowed(self, session_id: str, message_data: Dict[str, Any]) -> bool:
       
        allowed, _ = self.check(session_id, message_data)
        return allowed

import hashlib
import json
import time
from typing import Optional


class PlanCache:

    def __init__(self, ttl_seconds: Optional[int] = None):
        self.cache = {}
        self.ttl = ttl_seconds

    def _make_key(self, goal, context):
        raw = json.dumps(
            {"goal": goal, "context": context},
            sort_keys=True
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, goal, context):
        key = self._make_key(goal, context)

        if key not in self.cache:
            return None

        entry = self.cache[key]

        if self.ttl:
            if time.time() - entry["timestamp"] > self.ttl:
                del self.cache[key]
                return None

        return entry["plan"]

    def set(self, goal, context, plan):
        key = self._make_key(goal, context)

        self.cache[key] = {
            "plan": plan,
            "timestamp": time.time()
        }
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import redis

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class RedisOutputListener:
   
    def __init__(
        self,
        redis_url: Optional[str] = None,
        *,
        brpop_block_seconds: int = 10,
        socket_timeout: int = 10,
        max_retries: Optional[int] = None,  
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
        decode_responses: bool = True,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.brpop_block_seconds = max(1, int(brpop_block_seconds))
        self.socket_timeout = socket_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.decode_responses = decode_responses

        self._client = None
        self._ensure_client()

    def _ensure_client(self):
        self._client = redis.from_url(
            self.redis_url
        )

    def close(self):
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def get_output(self, session_id: str) -> Dict[str, Any]:
      
        queue = str(session_id)
        attempts = 0
        backoff = self.backoff_base

        while True:
            try:
                res = self._client.brpop(queue)
                if res is None:
                    continue

                _, raw = res
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON on queue '{queue}': {raw[:200]}") from e

                if not isinstance(data, dict):
                    raise ValueError(f"Expected dict JSON, got {type(data).__name__}")

                return data

            except (redis.ConnectionError, redis.TimeoutError) as e:
                attempts += 1
                if self.max_retries is not None and attempts > self.max_retries:
                    raise

                delay = min(self.backoff_max, backoff)
                log.warning(
                    "Redis connection error (attempt %s): %s. Retrying in %.2fs",
                    attempts, repr(e), delay
                )
                time.sleep(delay)
                backoff = min(self.backoff_max, backoff * 2)

                try:
                    self._ensure_client()
                except Exception as e2:
                    log.exception("Failed to reconnect to Redis: %s", e2)
                    time.sleep(delay)

# agent_internal_client.py
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import redis


class AgentInternalClient:
  

    _conn_cache: Dict[str, redis.Redis] = {}

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=os.getenv("LOG_LEVEL", "INFO").upper(),
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )

        self.ping_retries = 5
        self.ping_backoff_initial = 0.2  # seconds
        self.ping_backoff_max = 2.0      # seconds

    def push_task(
        self,
        *,
        redis_url: str,
        queue: str,
        task: Dict[str, Any],
    ) -> bool:
       
        if not self._is_valid_task(task):
            self.logger.error("Invalid task: missing task_id")
            return False

        conn = self._get_conn(redis_url)
        if not self._ping_with_retry(conn, url=redis_url):
            self.logger.error("Ping failed, discarding task_id=%s", task.get("task_id"))
            return False

        try:
            payload = json.dumps(task, ensure_ascii=False)
            conn.lpush(queue, payload)
            self.logger.debug("LPUSH -> %s (task_id=%s)", queue, task.get("task_id"))
            return True
        except Exception as e:
            self.logger.exception("LPUSH failed: %s", e)
            return False

    def close_all(self) -> None:
        for url, conn in list(self._conn_cache.items()):
            try:
                conn.close()
            except Exception:
                pass
            finally:
                self._conn_cache.pop(url, None)

    # ---------------- Internals ----------------

    def _get_conn(self, url: str) -> redis.Redis:
        conn = self._conn_cache.get(url)
        if conn is not None:
            return conn

        conn = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )
        self._conn_cache[url] = conn
        return conn

    def _ping_with_retry(self, conn: redis.Redis, *, url: str) -> bool:
        delay = self.ping_backoff_initial
        for attempt in range(1, self.ping_retries + 1):
            try:
                if conn.ping():
                    return True
            except Exception as e:
                self.logger.warning("Ping failed (%d/%d) %s: %s", attempt, self.ping_retries, url, e)
            time.sleep(delay)
            delay = min(self.ping_backoff_max, delay * 2.0)
        return False

    @staticmethod
    def _is_valid_task(task: Dict[str, Any]) -> bool:
        tid = str(task.get("task_id") or task.get("id") or "").strip()
        return bool(tid)

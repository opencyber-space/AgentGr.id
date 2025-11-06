import json
import os
import signal
import sys
import time
from typing import Callable, Dict, Optional, Union
import logging

import redis

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("launcher")

JsonDict = Dict[str, object]
Message = Union[str, JsonDict]


class RedisBRPOPWorker:
    """
    Minimal worker that consumes a Redis LIST (queue) with BRPOP.
    No at-least-once guarantees. If the process dies mid-callback, the message is lost.
    """

    def __init__(
        self,
        *,
        redis_url: Optional[str] = None,
        queue_key: str,
        block_seconds: int = 10,
        backoff_initial_s: float = 0.5,
        backoff_max_s: float = 10.0,
        decode_responses: bool = True,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        self.queue_key = queue_key
        self.block_seconds = block_seconds
        self.backoff_initial_s = backoff_initial_s
        self.backoff_max_s = backoff_max_s
        self.decode_responses = decode_responses

        self._stop = False
        self._r: Optional[redis.Redis] = None

    def run_forever(self, callback: Callable[[Message], None]) -> None:
        self._setup_signals()

        backoff = self.backoff_initial_s
        while not self._stop:
            try:
                self._connect()
                backoff = self.backoff_initial_s

                while not self._stop:
                    # BRPOP pops from the RIGHT; producers usually LPUSH to the LEFT (LPUSH/BRPOP pattern).
                    result = self._r.brpop(self.queue_key)
                    logging.info(f"[RedisWorker] {result}")
                    
                    if not result:
                        continue  # timeout -> loop

                    _, raw_value = result  # (key, value)
                    msg = self._decode(raw_value)
                    try:
                        callback(msg)
                    except Exception as e:
                        self._log(f"Callback failed: {e}")

            except (redis.ConnectionError, redis.TimeoutError) as e:
                self._log(f"Redis connection issue: {e}. Retrying in {backoff:.1f}s")
                time.sleep(backoff)
                backoff = min(self.backoff_max_s, backoff * 2)
            except Exception as e:
                self._log(f"Worker loop error: {e}. Retrying in {backoff:.1f}s")
                time.sleep(backoff)
                backoff = min(self.backoff_max_s, backoff * 2)

        self._log("Stopped.")

    def stop(self) -> None:
        self._stop = True

    def _connect(self) -> None:
        if self._r is not None:
            try:
                self._r.ping()
                return
            except Exception:
                self._r = None
        self._r = redis.from_url(self.redis_url, decode_responses=self.decode_responses)
        self._r.ping()
        self._log("Connected to Redis.")

    def _decode(self, s: str) -> Message:
        try:
            v = json.loads(s)
            return v
        except Exception:
            return s

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except Exception:
            pass

    def _signal_handler(self, signum, frame):
        self._log(f"Received signal {signum}; stopping...")
        self.stop()

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[RedisBRPOPWorker] {msg}", file=sys.stderr)

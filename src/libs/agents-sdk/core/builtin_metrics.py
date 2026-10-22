"""
Built-in SDK metrics, registered and started automatically by AgentExecutor.

Exposes eight rolling-average Prometheus Gauges:

  agent_queue_length_{5s,1m,5m,15m}  — average LLEN of the Redis input queue
  agent_latency_{5s,1m,5m,15m}       — average on_preprocess+on_data wall time (seconds)

Rolling windows are computed from a time-stamped sample deque; old samples are
evicted lazily so the average always reflects only the most recent window.
"""

import collections
import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_WINDOWS: Dict[str, float] = {
    "5s": 5.0,
    "1m": 60.0,
    "5m": 300.0,
    "15m": 900.0,
}


class _RollingWindow:
    """Thread-safe rolling average over a fixed time window."""

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._samples: collections.deque = collections.deque()
        self._lock = threading.Lock()

    def record(self, value: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._samples.append((now, value))
            self._evict(now)

    def average(self) -> float:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if not self._samples:
                return 0.0
            return sum(v for _, v in self._samples) / len(self._samples)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


class BuiltinMetrics:
    """
    SDK-level built-in metrics.  Instantiated once via get_builtin_metrics().
    AgentExecutor calls start() to launch the background updater thread, and
    start_redis_listener calls configure_queue() with Redis coordinates so the
    thread can poll LLEN.
    """

    def __init__(self, registry) -> None:
        self._registry = registry

        self._queue_windows: Dict[str, _RollingWindow] = {
            k: _RollingWindow(v) for k, v in _WINDOWS.items()
        }
        self._latency_windows: Dict[str, _RollingWindow] = {
            k: _RollingWindow(v) for k, v in _WINDOWS.items()
        }

        self._redis_url: Optional[str] = None
        self._queue_key: Optional[str] = None
        self._cfg_lock = threading.Lock()
        self._thread_started = False

        for name in _WINDOWS:
            registry.gauge(
                f"queue_length_{name}",
                f"Rolling average input queue depth over {name}",
            )
            registry.gauge(
                f"latency_{name}",
                f"Rolling average on_preprocess+on_data latency in seconds over {name}",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure_queue(self, redis_url: str, queue_key: str) -> None:
        """Provide Redis coordinates so the monitor thread can call LLEN."""
        with self._cfg_lock:
            self._redis_url = redis_url
            self._queue_key = queue_key

    def start(self) -> None:
        """Start the background gauge-updater thread (idempotent)."""
        with self._cfg_lock:
            if self._thread_started:
                return
            self._thread_started = True
        t = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="sdk-builtin-metrics",
        )
        t.start()
        logger.debug("[BuiltinMetrics] background updater started")

    def record_latency(self, duration_s: float) -> None:
        """Record a single on_preprocess+on_data wall-clock sample."""
        for win in self._latency_windows.values():
            win.record(duration_s)

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        r = None
        last_url: Optional[str] = None

        while True:
            try:
                with self._cfg_lock:
                    redis_url = self._redis_url
                    queue_key = self._queue_key

                if redis_url and queue_key:
                    try:
                        if r is None or redis_url != last_url:
                            import redis as _redis
                            r = _redis.from_url(redis_url, decode_responses=True)
                            last_url = redis_url
                        length = r.llen(queue_key)
                        for win in self._queue_windows.values():
                            win.record(float(length))
                    except Exception as exc:
                        logger.debug("[BuiltinMetrics] llen error: %s", exc)
                        r = None

                self._flush_gauges()

            except Exception as exc:
                logger.debug("[BuiltinMetrics] loop error: %s", exc)

            time.sleep(1.0)

    def _flush_gauges(self) -> None:
        for name, win in self._queue_windows.items():
            try:
                self._registry.set_gauge(f"queue_length_{name}", win.average())
            except Exception:
                pass
        for name, win in self._latency_windows.items():
            try:
                self._registry.set_gauge(f"latency_{name}", win.average())
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[BuiltinMetrics] = None
_instance_lock = threading.Lock()


def get_builtin_metrics() -> BuiltinMetrics:
    """Return (or lazily create) the process-wide BuiltinMetrics instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from .metrics import get_registry
                _instance = BuiltinMetrics(get_registry())
    return _instance

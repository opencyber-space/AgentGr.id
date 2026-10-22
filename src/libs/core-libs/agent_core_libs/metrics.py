from __future__ import annotations

import os
import threading
import time
import json
from collections import deque
from typing import Any, Dict, Optional

import redis
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from prometheus_client.registry import REGISTRY

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False



def detect_node_id() -> str:
    return os.getenv("NODE_ID") or os.getenv("HOSTNAME") or "node-unknown"


class RollingMetric:
    def __init__(self, window_seconds: int = 900):
        self.window = window_seconds
        self.data = deque()

    def add(self, value: float):
        now = time.time()
        self.data.append((now, float(value)))
        self.cleanup(now)

    def cleanup(self, now: Optional[float] = None):
        now = now or time.time()
        w = self.window
        dq = self.data
        while dq and dq[0][0] < now - w:
            dq.popleft()

    def average(self, window: int) -> float:
        now = time.time()
        self.cleanup(now)
        vals = [v for t, v in self.data if t >= now - window]
        return (sum(vals) / len(vals)) if vals else 0.0

    def current(self) -> float:
        self.cleanup()
        return self.data[-1][1] if self.data else 0.0


class _HardwareMetrics:
    """Simple hardware metrics provider. Uses psutil if present."""
    def get_metrics(self) -> Dict[str, Any]:
        if not _HAS_PSUTIL:
            return {}
        try:
            vm = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)
            load = None
            try:
                load = os.getloadavg()
            except Exception:
                load = None
            return {
                "cpu_percent": cpu,
                "mem_total": vm.total,
                "mem_used": vm.used,
                "mem_free": vm.free,
                "mem_percent": vm.percent,
                "load_avg": list(load) if load else None,
            }
        except Exception:
            return {}


# ---- AgentsMetrics ----

class AgentsMetrics:
    """
    Agents-side metrics with:
      - Prometheus exposition (HTTP)
      - Redis push of compact JSON snapshots
      - Four standard metrics:
          latency (Histogram), queue_length (Gauge),
          tasks_processed (Counter), fps (Gauge)
      - Rolling summaries for latency/fps (1m/5m/15m)
      - Extensible custom rolling categories
    """

    def __init__(
        self,
        *,
        agent_id: Optional[str] = None,
        instance_id: Optional[str] = None,
        redis_host: str = None,
        redis_port: int = None,
        redis_db: int = 0,
        redis_list_key: str = None,
        push_interval_sec: int = 30,
        prometheus_port: Optional[int] = None,  # set to expose immediately
        histogram_buckets = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10),
    ) -> None:
        # Identity
        self.agent_id = agent_id or os.getenv("AGENT_ID", "test-agent")
        self.instance_id = instance_id or os.getenv("INSTANCE_ID", "agent-instance-001")
        self.node_id = detect_node_id()

        # Redis config
        self._redis_host = redis_host or os.getenv("METRICS_REDIS_HOST", "localhost")
        self._redis_port = int(redis_port or os.getenv("METRICS_REDIS_PORT", "6379"))
        self._redis_db = int(redis_db or os.getenv("METRICS_REDIS_DB", "0"))
        self._redis_list_key = redis_list_key or os.getenv("AGENT_METRICS_LIST", "AGENT_METRICS")
        self._push_interval = int(os.getenv("AGENT_METRICS_PUSH_INTERVAL", str(push_interval_sec)))

        self.redis_client = redis.StrictRedis(
            host=self._redis_host, port=self._redis_port, db=self._redis_db
        )

        # Prometheus metrics registry
        self.metrics: Dict[str, Any] = {}

        # Standard metrics
        self.metrics["agent_latency_seconds"] = Histogram(
            "agent_latency_seconds",
            "Agent end-to-end latency in seconds",
            labelnames=["agentID", "instanceID", "nodeID"],
            buckets=histogram_buckets,
            registry=REGISTRY,
        )
        self.metrics["agent_queue_length"] = Gauge(
            "agent_queue_length",
            "Current queue length for the agent",
            labelnames=["agentID", "instanceID", "nodeID"],
            registry=REGISTRY,
        )
        self.metrics["agent_tasks_processed_total"] = Counter(
            "agent_tasks_processed_total",
            "Total number of tasks processed by the agent",
            labelnames=["agentID", "instanceID", "nodeID"],
            registry=REGISTRY,
        )
        self.metrics["agent_fps"] = Gauge(
            "agent_fps",
            "Throughput (frames/s or items/s) reported by the agent",
            labelnames=["agentID", "instanceID", "nodeID"],
            registry=REGISTRY,
        )

        # Rolling metrics store
        self.rolling_metrics: Dict[str, RollingMetric] = {}
        self.custom_metrics: Dict[str, Dict[str, RollingMetric]] = {}

        # Hardware sampler
        self.hw = _HardwareMetrics()

        # Threads & lifecycle
        self.stop_event = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None

        # Optionally start Prometheus immediately
        if prometheus_port is not None:
            self.start_http_server(prometheus_port)

        # Start Redis writer immediately (matches your original pattern)
        self.start_writer()

    # ----- Labels helper -----

    def _labels(self):
        return dict(agentID=self.agent_id, instanceID=self.instance_id, nodeID=self.node_id)

    # ----- Public metric APIs (the 4 core ones) -----

    def observe_latency(self, seconds: float):
        self.metrics["agent_latency_seconds"].labels(**self._labels()).observe(seconds)
        self._observe_rolling("latency_seconds", seconds)

    def set_queue_length(self, n: int):
        self.metrics["agent_queue_length"].labels(**self._labels()).set(n)

    def inc_tasks_processed(self, n: int = 1):
        self.metrics["agent_tasks_processed_total"].labels(**self._labels()).inc(n)

    def set_fps(self, fps: float):
        self.metrics["agent_fps"].labels(**self._labels()).set(fps)
        self._observe_rolling("fps", fps)

    # ----- Rolling metrics (generic) -----

    def _observe_rolling(self, name: str, value: float):
        if name not in self.rolling_metrics:
            self.rolling_metrics[name] = RollingMetric()
        self.rolling_metrics[name].add(value)

    def observe_custom_rolling(self, category: str, name: str, value: float):
        self.custom_metrics.setdefault(category, {})
        if name not in self.custom_metrics[category]:
            self.custom_metrics[category][name] = RollingMetric()
        self.custom_metrics[category][name].add(value)

    def get_extended_metrics(self) -> Dict[str, Any]:
        out = {}
        for name, m in self.rolling_metrics.items():
            out[name] = {
                "current": m.current(),
                "average_1m": m.average(60),
                "average_5m": m.average(300),
                "average_15m": m.average(900),
            }
        # Include custom categories as nested objects
        if self.custom_metrics:
            out["custom"] = {}
            for cat, mm in self.custom_metrics.items():
                out["custom"][cat] = {
                    n: {
                        "current": rm.current(),
                        "average_1m": rm.average(60),
                        "average_5m": rm.average(300),
                        "average_15m": rm.average(900),
                    }
                    for n, rm in mm.items()
                }
        return out

    # ----- Prometheus HTTP -----

    def start_http_server(self, port: int = 8000):
        # honors METRICS_PORT if set
        port = int(os.getenv("METRICS_PORT", port))
        threading.Thread(target=lambda: start_http_server(port), daemon=True).start()

    # ----- Redis push loop -----

    def start_writer(self):
        if self._writer_thread and self._writer_thread.is_alive():
            return

        def _loop():
            while not self.stop_event.is_set():
                self._push_snapshot_once()
                self.stop_event.wait(self._push_interval)

        self._writer_thread = threading.Thread(target=_loop, name="AgentMetricsWriter", daemon=True)
        self._writer_thread.start()

    def stop(self, wait: bool = True):
        self.stop_event.set()
        if wait and self._writer_thread:
            self._writer_thread.join(timeout=5)

    # ----- Snapshot -----

    def _push_snapshot_once(self):
        # Collect current prometheus sample values
        metrics_data: Dict[str, Any] = {
            "agentId": self.agent_id,
            "instanceId": self.instance_id,
            "nodeId": self.node_id,
            "type": "agent",
            "timestamp": time.time(),
        }

        for name, metric in self.metrics.items():
            try:
                coll = metric.collect()
                if not coll:
                    continue
                samples = coll[0].samples
                for s in samples:
                    # skip creation timestamps
                    if s.name.endswith("_created"):
                        continue
                    # Include fully qualified sample name to avoid clashes
                    metrics_data[s.name] = s.value
            except Exception:
                # avoid crashing the loop
                continue

        # Hardware metrics
        metrics_data["hardware"] = self.hw.get_metrics()

        metrics_data.update(self.get_extended_metrics())

        try:
            self.redis_client.lpush(self._redis_list_key, json.dumps(metrics_data))
        except Exception:
            pass

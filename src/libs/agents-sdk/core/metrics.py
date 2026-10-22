import os
import time
import threading
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    Info,
    Enum,
    start_http_server,
    REGISTRY,
    CollectorRegistry,
)

logger = logging.getLogger(__name__)

_DEFAULT_LABEL_NAMES: tuple = ("subject_id", "instance_id")

# --- Registry wrapper ---

class MetricsRegistry:
    """
    Central registry for all SDK metrics. Holds named metric instances so
    callers don't register the same metric twice.

    Every metric automatically includes ``subject_id`` and ``instance_id``
    as label dimensions (or info-dict keys for Info metrics) so records can
    always be filtered by subject and deployment instance.
    """

    def __init__(self, namespace: str = "agent", registry: CollectorRegistry = REGISTRY):
        self._ns = namespace
        self._registry = registry
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._summaries: Dict[str, Summary] = {}
        self._infos: Dict[str, Info] = {}
        self._enums: Dict[str, Enum] = {}

    # -- helpers --

    def _fqn(self, name: str) -> str:
        return f"{self._ns}_{name}"

    @property
    def _default_labels(self) -> Dict[str, str]:
        return {
            "subject_id": os.environ.get("SUBJECT_ID", ""),
            "instance_id": os.environ.get("INSTANCE_ID", ""),
        }

    def _merge_labels(self, labels: Dict[str, str]) -> Dict[str, str]:
        """Merge caller-supplied labels with the registry-level defaults."""
        return {**self._default_labels, **labels}

    def _with_default_label_names(self, labels: List[str]) -> List[str]:
        """Prepend subject_id / instance_id to a label-name list, skipping duplicates."""
        extra = [n for n in _DEFAULT_LABEL_NAMES if n not in labels]
        return extra + list(labels)

    # -- counter --

    def counter(self, name: str, doc: str, labels: List[str] = []) -> Counter:
        fqn = self._fqn(name)
        if fqn not in self._counters:
            self._counters[fqn] = Counter(
                fqn, doc, self._with_default_label_names(labels), registry=self._registry
            )
        return self._counters[fqn]

    def inc(self, name: str, amount: float = 1.0, labels: Dict[str, str] = {}):
        """Increment a counter by *amount* (default 1)."""
        c = self._counters.get(self._fqn(name))
        if c is None:
            raise KeyError(f"Counter '{name}' not registered")
        c.labels(**self._merge_labels(labels)).inc(amount)

    # -- gauge --

    def gauge(self, name: str, doc: str, labels: List[str] = []) -> Gauge:
        fqn = self._fqn(name)
        if fqn not in self._gauges:
            self._gauges[fqn] = Gauge(
                fqn, doc, self._with_default_label_names(labels), registry=self._registry
            )
        return self._gauges[fqn]

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = {}):
        g = self._gauges.get(self._fqn(name))
        if g is None:
            raise KeyError(f"Gauge '{name}' not registered")
        g.labels(**self._merge_labels(labels)).set(value)

    def inc_gauge(self, name: str, amount: float = 1.0, labels: Dict[str, str] = {}):
        g = self._gauges.get(self._fqn(name))
        if g is None:
            raise KeyError(f"Gauge '{name}' not registered")
        g.labels(**self._merge_labels(labels)).inc(amount)

    def dec_gauge(self, name: str, amount: float = 1.0, labels: Dict[str, str] = {}):
        g = self._gauges.get(self._fqn(name))
        if g is None:
            raise KeyError(f"Gauge '{name}' not registered")
        g.labels(**self._merge_labels(labels)).dec(amount)

    # -- histogram --

    def histogram(
        self,
        name: str,
        doc: str,
        labels: List[str] = [],
        buckets: Optional[List[float]] = None,
    ) -> Histogram:
        fqn = self._fqn(name)
        if fqn not in self._histograms:
            kwargs: Dict[str, Any] = {"registry": self._registry}
            if buckets is not None:
                kwargs["buckets"] = buckets
            self._histograms[fqn] = Histogram(
                fqn, doc, self._with_default_label_names(labels), **kwargs
            )
        return self._histograms[fqn]

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = {}):
        h = self._histograms.get(self._fqn(name))
        if h is None:
            raise KeyError(f"Histogram '{name}' not registered")
        h.labels(**self._merge_labels(labels)).observe(value)

    # -- summary --

    def summary(self, name: str, doc: str, labels: List[str] = []) -> Summary:
        fqn = self._fqn(name)
        if fqn not in self._summaries:
            self._summaries[fqn] = Summary(
                fqn, doc, self._with_default_label_names(labels), registry=self._registry
            )
        return self._summaries[fqn]

    def observe_summary(self, name: str, value: float, labels: Dict[str, str] = {}):
        s = self._summaries.get(self._fqn(name))
        if s is None:
            raise KeyError(f"Summary '{name}' not registered")
        s.labels(**self._merge_labels(labels)).observe(value)

    # -- info --

    def info(self, name: str, doc: str) -> Info:
        fqn = self._fqn(name)
        if fqn not in self._infos:
            self._infos[fqn] = Info(fqn, doc, registry=self._registry)
        return self._infos[fqn]

    def set_info(self, name: str, data: Dict[str, str]):
        i = self._infos.get(self._fqn(name))
        if i is None:
            raise KeyError(f"Info '{name}' not registered")
        i.info({**self._default_labels, **data})

    # -- enum --

    def enum(self, name: str, doc: str, states: List[str], labels: List[str] = []) -> Enum:
        fqn = self._fqn(name)
        if fqn not in self._enums:
            self._enums[fqn] = Enum(
                fqn, doc, self._with_default_label_names(labels), states=states,
                registry=self._registry,
            )
        return self._enums[fqn]

    def set_enum(self, name: str, state: str, labels: Dict[str, str] = {}):
        e = self._enums.get(self._fqn(name))
        if e is None:
            raise KeyError(f"Enum '{name}' not registered")
        e.labels(**self._merge_labels(labels)).state(state)

    # -- timing context managers --

    @contextmanager
    def time_histogram(self, name: str, labels: Dict[str, str] = {}):
        """Measure wall-clock duration and record it in the named histogram."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.observe_histogram(name, elapsed, labels)

    @contextmanager
    def time_summary(self, name: str, labels: Dict[str, str] = {}):
        """Measure wall-clock duration and record it in the named summary."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.observe_summary(name, elapsed, labels)


# --- Tracer ---

class Span:
    """A single trace span."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.name = name
        self.parent_span_id = parent_span_id
        self.labels: Dict[str, str] = labels or {}
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.status: str = "ok"
        self.error: Optional[str] = None

    def finish(self, status: str = "ok", error: Optional[str] = None):
        self.end_time = time.perf_counter()
        self.status = status
        self.error = error

    @property
    def duration(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return self.end_time - self.start_time


class Tracer:
    """
    Lightweight tracer that records span durations and emits them as
    Prometheus metrics so they can be correlated by trace/span ID.

    Metrics emitted:
      <ns>_trace_span_duration_seconds  (histogram, labels: trace_id, span, status)
      <ns>_trace_span_total             (counter,   labels: trace_id, span, status)
    """

    def __init__(self, registry: MetricsRegistry):
        self._registry = registry
        self._active: Dict[str, Span] = {}  # span_id -> Span
        self._lock = threading.Lock()

        registry.histogram(
            "trace_span_duration_seconds",
            "Duration of trace spans in seconds",
            labels=["trace_id", "span", "status"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )
        registry.counter(
            "trace_span_total",
            "Total number of completed trace spans",
            labels=["trace_id", "span", "status"],
        )

    # -- low-level API --

    def start_span(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Span:
        span = Span(trace_id, span_id, name, parent_span_id, labels)
        with self._lock:
            self._active[span_id] = span
        logger.debug("trace start trace_id=%s span_id=%s name=%s", trace_id, span_id, name)
        return span

    def finish_span(
        self,
        span_id: str,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> Optional[Span]:
        with self._lock:
            span = self._active.pop(span_id, None)
        if span is None:
            logger.warning("finish_span: unknown span_id=%s", span_id)
            return None
        span.finish(status=status, error=error)
        lbl = {"trace_id": span.trace_id, "span": span.name, "status": span.status}
        self._registry.observe_histogram("trace_span_duration_seconds", span.duration, lbl)
        self._registry.inc("trace_span_total", labels=lbl)
        logger.debug(
            "trace finish trace_id=%s span_id=%s name=%s duration=%.4fs status=%s",
            span.trace_id, span_id, span.name, span.duration, span.status,
        )
        return span

    # -- context-manager API --

    @contextmanager
    def span(
        self,
        trace_id: str,
        name: str,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        """
        Context manager that starts a span on entry and finishes it on exit.
        Sets status='error' automatically when an exception propagates.

        Usage::

            with tracer.span("req-abc123", "do_something") as span:
                ...
        """
        import uuid
        sid = span_id or str(uuid.uuid4())
        s = self.start_span(trace_id, sid, name, parent_span_id, labels)
        try:
            yield s
        except Exception as exc:
            self.finish_span(sid, status="error", error=str(exc))
            raise
        else:
            self.finish_span(sid, status="ok")

    def trace_by_id(self, trace_id: str, name: str, labels: Optional[Dict[str, str]] = None):
        """
        Decorator that wraps a function in a span keyed by a fixed trace_id.

        Usage::

            @tracer.trace_by_id("boot", "agent_init")
            def init():
                ...
        """
        def decorator(fn):
            import functools
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                with self.span(trace_id, name, labels=labels):
                    return fn(*args, **kwargs)
            return wrapper
        return decorator


# --- Metrics server ---

_server_started = False
_server_lock = threading.Lock()


def start_metrics_server(port: int = 9090, addr: str = "0.0.0.0") -> None:
    """
    Start the Prometheus HTTP scrape endpoint.
    Safe to call multiple times — only the first call has effect.
    """
    global _server_started
    with _server_lock:
        if _server_started:
            logger.debug("metrics server already running, skipping start")
            return
        start_http_server(port, addr=addr)
        _server_started = True
        logger.info("Prometheus metrics server listening on %s:%d", addr, port)


# --- Module-level singleton ---

_default_registry: Optional[MetricsRegistry] = None
_default_tracer: Optional[Tracer] = None


def get_registry(namespace: str = "agent") -> MetricsRegistry:
    """Return (or lazily create) the module-level MetricsRegistry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = MetricsRegistry(namespace=namespace)
    return _default_registry


def get_tracer() -> Tracer:
    """Return (or lazily create) the module-level Tracer."""
    global _default_tracer
    if _default_tracer is None:
        _default_tracer = Tracer(get_registry())
    return _default_tracer

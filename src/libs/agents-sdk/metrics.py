"""
reviewer.py — exhaustive example of every metrics type and tracing pattern
in agents-sdk/core/metrics.py.

Run directly:  python reviewer.py
Scrape:        curl http://localhost:9090/metrics
"""

import time
import uuid

from core.metrics import get_registry, get_tracer, start_metrics_server

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

start_metrics_server(port=9090)
reg = get_registry(namespace="reviewer")
tracer = get_tracer()


# ---------------------------------------------------------------------------
# 1. Counter — monotonically increasing, never decreases
#    Use for: requests processed, errors seen, messages sent
# ---------------------------------------------------------------------------

reg.counter(
    "reviews_total",
    "Total number of review tasks processed",
    labels=["status"],          # label dimensions
)

def run_review(fail: bool = False):
    status = "error" if fail else "ok"
    reg.inc("reviews_total", labels={"status": status})
    reg.inc("reviews_total", amount=0)          # explicit amount (no-op here, shows API)

run_review()
run_review(fail=True)
run_review()


# ---------------------------------------------------------------------------
# 2. Gauge — current value, can go up or down
#    Use for: active connections, queue depth, cache size
# ---------------------------------------------------------------------------

reg.gauge(
    "active_reviews",
    "Number of reviews currently in progress",
)
reg.gauge(
    "queue_depth",
    "Pending tasks in the input queue",
    labels=["priority"],
)

reg.set_gauge("active_reviews", 5)
reg.inc_gauge("active_reviews", 2)          # 7
reg.dec_gauge("active_reviews", 1)          # 6

reg.set_gauge("queue_depth", 10, labels={"priority": "high"})
reg.set_gauge("queue_depth", 42, labels={"priority": "low"})


# ---------------------------------------------------------------------------
# 3. Histogram — distribution of observed values in configurable buckets
#    Use for: request latency, payload size, scoring durations
# ---------------------------------------------------------------------------

reg.histogram(
    "review_duration_seconds",
    "Time spent processing each review",
    labels=["model"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

reg.observe_histogram("review_duration_seconds", 0.08, labels={"model": "claude-sonnet-4-6"})
reg.observe_histogram("review_duration_seconds", 1.32, labels={"model": "claude-sonnet-4-6"})
reg.observe_histogram("review_duration_seconds", 0.21, labels={"model": "claude-haiku-4-5-20251001"})

# --- time_histogram context manager ---
with reg.time_histogram("review_duration_seconds", labels={"model": "claude-sonnet-4-6"}):
    time.sleep(0.05)            # simulated work


# ---------------------------------------------------------------------------
# 4. Summary — sliding-window quantiles (p50, p90, p99) without fixed buckets
#    Use for: latency percentiles when exact bucket boundaries aren't known
# ---------------------------------------------------------------------------

reg.summary(
    "scoring_latency_seconds",
    "Latency of the scoring step",
    labels=["scorer"],
)

reg.observe_summary("scoring_latency_seconds", 0.12, labels={"scorer": "relevance"})
reg.observe_summary("scoring_latency_seconds", 0.04, labels={"scorer": "relevance"})
reg.observe_summary("scoring_latency_seconds", 0.31, labels={"scorer": "quality"})

# --- time_summary context manager ---
with reg.time_summary("scoring_latency_seconds", labels={"scorer": "relevance"}):
    time.sleep(0.03)


# ---------------------------------------------------------------------------
# 5. Info — static key/value metadata (version, build info)
#    Use for: service version, git SHA, environment
# ---------------------------------------------------------------------------

reg.info("build", "Build metadata for this reviewer service")
reg.set_info("build", {
    "version":     "1.4.2",
    "git_sha":     "a3f9c12",
    "environment": "production",
})


# ---------------------------------------------------------------------------
# 6. Enum — current state from a fixed set of states
#    Use for: service health status, pipeline stage, connection state
# ---------------------------------------------------------------------------

reg.enum(
    "pipeline_state",
    "Current state of the review pipeline",
    states=["idle", "running", "degraded", "stopped"],
)

reg.set_enum("pipeline_state", "idle")
reg.set_enum("pipeline_state", "running")


# ---------------------------------------------------------------------------
# 7. Tracing — context-manager span (auto status on exception)
#    Labels on the span flow into prometheus as trace_id / span / status
# ---------------------------------------------------------------------------

trace_id = str(uuid.uuid4())

with tracer.span(trace_id, "fetch_document") as span:
    time.sleep(0.02)
    # span.trace_id, span.span_id, span.name accessible here

# Nested spans — parent_span_id links child to parent
with tracer.span(trace_id, "pipeline_root") as root:
    with tracer.span(trace_id, "preprocess", parent_span_id=root.span_id) as pre:
        time.sleep(0.01)
    with tracer.span(trace_id, "score", parent_span_id=root.span_id) as score:
        time.sleep(0.02)

# Error span — status="error" is set automatically when an exception propagates
try:
    with tracer.span(trace_id, "validate_output"):
        raise ValueError("schema mismatch")
except ValueError:
    pass    # already recorded as status=error in prometheus


# ---------------------------------------------------------------------------
# 8. Tracing — low-level start_span / finish_span for async or manual control
# ---------------------------------------------------------------------------

span_id = str(uuid.uuid4())
span = tracer.start_span(trace_id, span_id, "manual_step", labels={"stage": "final"})
time.sleep(0.01)
tracer.finish_span(span_id, status="ok")

# Finish with explicit error:
span_id_err = str(uuid.uuid4())
tracer.start_span(trace_id, span_id_err, "failing_step")
tracer.finish_span(span_id_err, status="error", error="timeout after 30s")


# ---------------------------------------------------------------------------
# 9. Tracing — trace_by_id decorator
#    Wraps a function so every call is automatically a named span
# ---------------------------------------------------------------------------

@tracer.trace_by_id(trace_id, "compute_score", labels={"model": "v2"})
def compute_score(text: str) -> float:
    time.sleep(0.01)
    return len(text) * 0.01

score = compute_score("example review text")


# ---------------------------------------------------------------------------
# Keep the metrics server alive so you can scrape /metrics
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Metrics available at http://localhost:9090/metrics")
    print("Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

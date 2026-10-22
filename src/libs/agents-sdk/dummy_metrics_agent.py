"""
dummy_metrics_agent.py

A self-contained sample agent that emits realistic dummy metrics without
calling any external services. Useful for testing the metrics pipeline,
Prometheus scraping, and dashboard wiring.

Run locally:
    SUBJECT_ID=dummy-001 INSTANCE_ID=inst-1 python dummy_metrics_agent.py

Metrics exposed at http://localhost:9090/metrics (Prometheus scrape endpoint).
"""

import random
import time
import logging
from typing import List, Optional

from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main
from core.metrics import get_registry, get_tracer, start_metrics_server

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level metrics — registered once, shared across all agent instances
# ---------------------------------------------------------------------------

_reg = get_registry(namespace="dummy_agent")
_tracer = get_tracer()

# How many tasks have been processed
_reg.counter("tasks_total", "Total tasks handled", labels=["status"])

# Tasks currently in flight
_reg.gauge("active_tasks", "Tasks currently executing")

# Wall-clock latency of the full on_data handler
_reg.histogram(
    "task_duration_seconds",
    "End-to-end task processing time",
    labels=["status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# Individual step latencies (simulated pipeline steps)
_reg.histogram(
    "step_duration_seconds",
    "Latency per simulated processing step",
    labels=["step", "status"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

# Sliding-window quantiles for the pre-processing stage
_reg.summary("preprocess_latency_seconds", "Latency of the on_preprocess step")

# Count of tasks skipped in preprocessing
_reg.counter("preprocess_skipped", "Tasks skipped during on_preprocess", labels=["reason"])

# Static agent identity (set once in __init__)
_reg.info("agent_identity", "Static identity for this dummy agent instance")

# Lifecycle state machine
_reg.enum(
    "agent_state",
    "Current lifecycle state",
    states=["initializing", "ready", "processing", "error"],
)

# Simulated business metrics
_reg.gauge("items_in_queue", "Simulated backlog depth")
_reg.counter("bytes_processed_total", "Simulated bytes processed")


# ---------------------------------------------------------------------------
# Simulated pipeline steps
# ---------------------------------------------------------------------------

_STEPS = ["validate", "transform", "enrich", "emit"]


def _simulate_step(step: str, task_id: str, parent_span_id: str) -> dict:
    """Run a fake processing step; randomly inject errors ~5% of the time."""
    status = "ok"
    with _tracer.span(task_id, step, parent_span_id=parent_span_id) as span:
        t0 = time.perf_counter()
        try:
            # Simulate variable latency: validate is fast, enrich is slower
            base_latency = {"validate": 0.01, "transform": 0.03, "enrich": 0.07, "emit": 0.02}
            jitter = random.uniform(0, base_latency.get(step, 0.05))
            time.sleep(base_latency.get(step, 0.05) + jitter)

            if random.random() < 0.05:
                raise RuntimeError(f"Simulated transient error in step '{step}'")

            return {"step": step, "result": "ok", "span_id": span.span_id}
        except Exception as exc:
            status = "error"
            raise
        finally:
            _reg.observe_histogram(
                "step_duration_seconds",
                time.perf_counter() - t0,
                labels={"step": step, "status": status},
            )


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class DummyMetricsAgent:
    """
    Minimal agent that processes synthetic tasks and emits metrics for every
    meaningful operation. No external calls — safe to run anywhere.
    """

    def __init__(self, subject, context: Context) -> None:
        _reg.set_enum("agent_state", "initializing")
        self.subject = subject

        subject_id = getattr(getattr(subject, "identity", None), "subject_id", "dummy-001")
        _reg.set_info("agent_identity", {
            "subject_id": subject_id,
            "version": "1.0.0",
            "mode": "dummy",
        })

        # Start Prometheus scrape endpoint
        start_metrics_server(port=9090)

        _reg.set_enum("agent_state", "ready")
        log.info("[DummyMetricsAgent] ready, subject_id=%s", subject_id)

    # ------------------------------------------------------------------

    def get_muxer(self):
        return None

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        with _reg.time_summary("preprocess_latency_seconds"):
            with _tracer.span(task.task_id, "on_preprocess"):
                job = task.job_data
                if not job.get("payload"):
                    log.warning("Task %s missing 'payload' — skipping", task.task_id)
                    _reg.inc("preprocess_skipped", labels={"reason": "missing_payload"})
                    return None
                return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        _reg.inc_gauge("active_tasks")
        _reg.set_enum("agent_state", "processing")
        # Simulate a fluctuating queue depth
        _reg.set_gauge("items_in_queue", max(0, random.randint(0, 50) - 1))

        status = "ok"
        t0 = time.perf_counter()

        try:
            with _tracer.span(task.task_id, "on_data") as root_span:
                step_results = []
                for step in _STEPS:
                    result = _simulate_step(step, task.task_id, root_span.span_id)
                    step_results.append(result)

                # Simulate bytes processed based on a dummy payload size
                payload = task.job_data.get("payload", "")
                _reg.inc("bytes_processed_total", amount=float(len(str(payload))))

                _reg.inc("tasks_total", labels={"status": "ok"})
                return AgentResult(
                    task_id=task.task_id,
                    job_output={
                        "steps": step_results,
                        "processed_at": time.time(),
                    },
                    job_output_metadata={"steps_run": _STEPS},
                    is_error=False,
                )

        except Exception as exc:
            status = "error"
            _reg.inc("tasks_total", labels={"status": "error"})
            _reg.set_enum("agent_state", "error")
            log.exception("Task %s failed: %s", task.task_id, exc)
            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"message": str(exc)},
            )

        finally:
            _reg.observe_histogram(
                "task_duration_seconds",
                time.perf_counter() - t0,
                labels={"status": status},
            )
            _reg.dec_gauge("active_tasks")
            if status == "ok":
                _reg.set_enum("agent_state", "ready")


# ---------------------------------------------------------------------------
# Standalone smoke-test (no SDK runtime required)
# ---------------------------------------------------------------------------

def _smoke_test():
    """Run a few synthetic tasks directly — no Redis / WebSocket needed."""
    from core.agent_executor import AgentTask

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    class _FakeIdentity:
        subject_id = "dummy-smoke-001"

    class _FakeSubject:
        identity = _FakeIdentity()

    agent = DummyMetricsAgent(subject=_FakeSubject(), context=None)

    for i in range(10):
        task = AgentTask(
            task_id=f"task-{i:04d}",
            job_data={"payload": f"synthetic payload number {i}" * random.randint(1, 20)},
        )
        tasks = agent.on_preprocess(task)
        if tasks:
            result = agent.on_data(tasks[0])
            log.info("task-%04d → error=%s", i, result.is_error)

    log.info("Smoke test complete. Metrics at http://localhost:9090/metrics")
    # Keep the server alive so you can scrape it
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import sys
    if "--smoke" in sys.argv:
        _smoke_test()
    else:
        main(DummyMetricsAgent)

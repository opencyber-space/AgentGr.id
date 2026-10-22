# Agent Application Metrics

This document describes the `AgentsMetrics` class from the `agent_core_libs` package. It collects a standard set of agent runtime metrics, exposes them in Prometheus format over HTTP, and periodically pushes JSON snapshots to Redis.

---

### Introduction

`AgentsMetrics` provides:

* **Four standard Prometheus metrics**: latency, queue length, tasks processed and throughput (FPS).
* **Rolling summaries** (current value and 1m / 5m / 15m averages) for latency, FPS and any custom series you record.
* **Push-based snapshots** to a Redis list for centralized collection.
* **Hardware metrics** (CPU, memory, load average) in each snapshot, when `psutil` is installed.
* **Automatic labels**: `agentID`, `instanceID` and `nodeID`.
* **A built-in HTTP exporter** for Prometheus scraping.

---

### Installation

`AgentsMetrics` is part of `agent_core_libs` (`libs/core-libs`), which depends on `redis` and `prometheus-client`. Install the optional `metrics-hw` extra to include hardware metrics:

```bash
pip install "./libs/core-libs[metrics-hw]"
```

### Importing

```python
from agent_core_libs.metrics import AgentsMetrics
```

---

### Standard Metrics

| Prometheus name                | Type      | Updated by                    | Description                                       |
| ------------------------------ | --------- | ----------------------------- | ------------------------------------------------- |
| `agent_latency_seconds`        | Histogram | `observe_latency(seconds)`    | End-to-end latency in seconds                     |
| `agent_queue_length`           | Gauge     | `set_queue_length(n)`         | Current queue length                              |
| `agent_tasks_processed_total`  | Counter   | `inc_tasks_processed(n=1)`    | Total number of tasks processed                   |
| `agent_fps`                    | Gauge     | `set_fps(fps)`                | Throughput (frames/s or items/s)                  |

The default histogram buckets are `(0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10)`.

Each metric carries these labels:

| Label        | Source                                           |
| ------------ | ------------------------------------------------ |
| `agentID`    | `agent_id` argument, else `AGENT_ID` env (default `test-agent`) |
| `instanceID` | `instance_id` argument, else `INSTANCE_ID` env (default `agent-instance-001`) |
| `nodeID`     | `NODE_ID` env, else `HOSTNAME` env, else `node-unknown` |

---

### Usage Examples

#### 1. Initialize

```python
metrics = AgentsMetrics(agent_id="subject-xyz", prometheus_port=8889)
```

All arguments are keyword-only and optional:

| Argument            | Default / env fallback                                  | Description                                   |
| ------------------- | ------------------------------------------------------- | --------------------------------------------- |
| `agent_id`          | `AGENT_ID` (`test-agent`)                               | Agent identifier label                        |
| `instance_id`       | `INSTANCE_ID` (`agent-instance-001`)                    | Instance identifier label                     |
| `redis_host`        | `METRICS_REDIS_HOST` (`localhost`)                      | Redis host for snapshots                      |
| `redis_port`        | `METRICS_REDIS_PORT` (`6379`)                           | Redis port                                    |
| `redis_db`          | `METRICS_REDIS_DB` (`0`)                                | Redis DB                                      |
| `redis_list_key`    | `AGENT_METRICS_LIST` (`AGENT_METRICS`)                  | Redis list that receives snapshots            |
| `push_interval_sec` | `30` (the `AGENT_METRICS_PUSH_INTERVAL` env overrides it) | Seconds between snapshots                   |
| `prometheus_port`   | `None`                                                  | If set, start the HTTP exporter immediately   |
| `histogram_buckets` | see above                                               | Latency histogram buckets                     |

> The Redis snapshot writer starts as soon as the object is created. The metrics are registered in the global Prometheus registry, so create only **one** `AgentsMetrics` per process.

---

#### 2. Update the standard metrics

```python
metrics.observe_latency(0.42)
metrics.set_queue_length(7)
metrics.inc_tasks_processed()      # +1
metrics.inc_tasks_processed(5)     # +5
metrics.set_fps(24.5)
```

`observe_latency` and `set_fps` also feed the rolling series `latency_seconds` and `fps`.

#### 3. Record custom rolling metrics

Custom series are grouped by category. They are included in snapshots, but are not exported to Prometheus.

```python
metrics.observe_custom_rolling("llm", "tokens_per_second", 85.2)
metrics.observe_custom_rolling("llm", "prompt_tokens", 512)
```

#### 4. Read rolling summaries

```python
metrics.get_extended_metrics()
```

```json
{
  "latency_seconds": { "current": 0.42, "average_1m": 0.40, "average_5m": 0.38, "average_15m": 0.37 },
  "fps":             { "current": 24.5, "average_1m": 24.1, "average_5m": 23.9, "average_15m": 24.0 },
  "custom": {
    "llm": {
      "tokens_per_second": { "current": 85.2, "average_1m": 85.2, "average_5m": 85.2, "average_15m": 85.2 }
    }
  }
}
```

Rolling series keep 15 minutes of samples.

---

### Server

#### Prometheus exporter

```python
metrics.start_http_server(port=8889)
```

This starts a Prometheus HTTP endpoint at `http://<host>:<port>/metrics` on a background thread. If `METRICS_PORT` is set in the environment, it overrides the `port` argument. Passing `prometheus_port` to the constructor does the same thing.

#### Redis snapshots

Every `push_interval_sec` seconds, a JSON snapshot is `LPUSH`ed to the Redis list (`AGENT_METRICS` by default):

```json
{
  "agentId": "subject-xyz",
  "instanceId": "agent-instance-001",
  "nodeId": "agent-node-123",
  "type": "agent",
  "timestamp": 1735689600.12,

  "agent_latency_seconds_bucket": 2.0,
  "agent_latency_seconds_count": 12.0,
  "agent_latency_seconds_sum": 4.9,
  "agent_queue_length": 7.0,
  "agent_tasks_processed_total": 6.0,
  "agent_fps": 24.5,

  "hardware": {
    "cpu_percent": 12.5,
    "mem_total": 16777216000,
    "mem_used": 8388608000,
    "mem_free": 8388608000,
    "mem_percent": 50.0,
    "load_avg": [0.5, 0.4, 0.3]
  },

  "latency_seconds": { "current": 0.42, "average_1m": 0.40, "average_5m": 0.38, "average_15m": 0.37 },
  "fps": { "current": 24.5, "average_1m": 24.1, "average_5m": 23.9, "average_15m": 24.0 },
  "custom": { "llm": { "...": "..." } }
}
```

* Prometheus samples are flattened by sample name (`_created` samples are skipped). Because sample names are the keys, only one value is kept per name; for the histogram, that is the last bucket.
* `hardware` is `{}` if `psutil` is not installed.
* Redis errors while pushing are ignored.

#### Stop

```python
metrics.stop()   # stops the Redis writer (waits up to 5 s)
```

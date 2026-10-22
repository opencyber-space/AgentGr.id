# Agent Memories

## Introduction

Agent memories let agents **store**, **retrieve**, and **share** context, knowledge, and events. There are three practical classes of memory:

1. **SDK Context Store** — namespaced key-value memory built into the agents SDK (`core.context`), backed by local Redis, a global Redis, a shared Redis or an in-process store. It includes helpers for sessions, conversation history, working memory, tool state, checkpoints and more.
2. **Agent Context Cache** — in-process key-value working state whose updates are broadcast to NATS topics (`agent_context_cache`, in `libs/agents-addons`).
3. **Memory Grid** — FrameDB-based in-memory, storage and streaming backends (see the [Memory Grid](#memory-grid-client-developer-documentation) section).

> For long-term **episodic, semantic, procedural, reflective and reward** memory, git-versioned agent files, and learning lessons from experience (mining, human review, applying lessons, feedback), see [Advanced Agent Memories](advanced-memories/index.md).

---

| Memory Type | Purpose / Use Case | Best for |
| --- | --- | --- |
| **SDK Context Store** (`core.context.store.RedisStore`) | Namespaced `get`/`set` with TTLs and automatic serialization. Local, global or shared scope. Session-structured helpers (`AgentSession`, `ConversationMemory`, `WorkingMemory`, `CheckpointManager`, …). | The agent's **primary working memory**: conversation history, active plan and steps, tool state, checkpoints. Use the global or shared store to share state between instances and agents. |
| **Agent Context Cache** (`AgentContextCache`) | Namespace-scoped in-process `get`/`set`. Every write is queued and **broadcast over NATS** to configured topics. | Small, fast-changing state that **other agents must be notified about** (coordination flags, shared context updates). Data is not persisted. |
| **Memory Grid** (`memory_type="memory-grid"`) | FrameDB-backed in-memory objects, durable storage and streams. | Large objects, durable results and event streams. |

---

## Registering Memory in Subject Specification

Memories can be recorded in the subject's `integrations.memory_systems` list using `MemoryItem`. The agents SDK does not instantiate memories from these entries automatically. Read them from `self.subject.integrations.memory_systems` and create the store in your agent.

### Data Class Reference

```python
@dataclass
class MemoryItem:
    memory_id: str
    memory_type: str = ""
    memory_backend: str = ""
    memory_custom_config: Dict[str, Any] = field(default_factory=dict)
```

### Example Configuration

```json
{
  "memory_id": "context-memory-01",
  "memory_type": "agent-context",
  "memory_backend": "redis-shared",
  "memory_custom_config": {
    "redis_url": "redis://redis.default.svc.cluster.local:6379/0",
    "namespace": "agent-alpha"
  }
}
```

### Field Descriptions

| Field                     | Type   | Description                                                                 |
| ------------------------- | ------ | --------------------------------------------------------------------------- |
| **memory\_id**            | `str`  | Unique identifier for this memory entry.                                    |
| **memory\_type**          | `str`  | Type of memory (e.g. `"agent-context"`, `"memory-grid"`).                   |
| **memory\_backend**       | `str`  | Backend the agent should create (your own convention, e.g. `"redis-local"`, `"redis-global"`, `"redis-shared"`, `"in-memory"`). |
| **memory\_custom\_config**| `dict` | Backend settings (e.g. `redis_url`, `namespace`).                           |

---

# SDK Context Store — Client Developer Documentation

## Introduction

The agents SDK includes a key-value store at `core.context.store.RedisStore`, plus higher-level memory helpers in `core.context.utils`, `core.context.io` and `core.context.workspace`. Every helper is built on `RedisStore` namespaces, so the same code works against an in-process store or Redis.

## Stores

```python
from core.context.store import RedisStore

local = RedisStore.get_local_store()                  # redis://localhost:6379 (the instance's Redis sidecar)
mem = RedisStore.get_local_store(in_memory=True)      # in-process store, no Redis needed (only if no local store exists yet)
glob = RedisStore.get_global_store()                  # Redis at REDIS_GLOBAL_STORE_HOST_URL
shared = RedisStore.get_shared_store("redis://redis.shared:6379/0")
```

| Store | Backend | Scope |
|---|---|---|
| Local (`get_local_store()`) | `redis://localhost:6379`, or an in-process dict when `in_memory=True` | One agent instance |
| Global (`get_global_store()`) | Redis at `REDIS_GLOBAL_STORE_HOST_URL` (`RuntimeError` if unset) | All agents configured with that URL |
| Shared (`get_shared_store(url)`) | Redis at `url` | Anyone with the URL |

Each store is a process-wide singleton: one local store, one global store, and one shared store per URL. The first call to `get_local_store` decides whether the local store is in-memory or Redis.

## Basic Operations

```python
store = RedisStore.get_local_store().get_namespace("agent-alpha")

store.set("plan", ["fetch", "summarize"])
store.set("token", "abc", ex=3600)        # expires in 1 hour
store.get("plan")                         # ['fetch', 'summarize']
store.get("missing", default={})          # {}
store.exists("plan")                      # True
store.pop("token")                        # get and delete
store.update({"a": 1, "b": 2.5})          # bulk set
store.keys()                              # keys in this namespace (and its sub-namespaces)
store.items(); store.values()
store.delete("a")
store.clear()                             # delete all keys under this namespace

store["mode"] = "auto"; "mode" in store; len(store); del store["mode"]
```

* `get_namespace(name)` returns a child store whose keys are prefixed `parent:name:`. Namespaces nest.
* Values keep their type: `None`, `bytes`, `str`, `bool`, `int` and `float` are stored natively; `dict`/`list`/`tuple` as JSON (tuples come back as lists); anything else is pickled.

## Memory Helpers

All helpers take a store (or a session) and keep their data in namespaces under it.

```python
from core.context.utils import (
    AgentSession, ConversationMemory, WorkingMemory, ToolState, ExecutionLock,
    InterruptState, WorkflowState, MetricsState, CheckpointManager, PromptContextBuilder,
)

session = AgentSession(RedisStore.get_global_store(), agent_id="agent-alpha", session_id="sess-1")
```

`AgentSession` stores everything under `agents:<agent_id>:sessions:<session_id>`, with sub-namespaces `meta`, `messages`, `working`, `tools`, `metrics`, `workflow`, `interrupts`, `checkpoints` and `locks`. It records `created` and `status` (`active`) on first use, and provides `status()`, `set_status()`, `touch()`, `reset()`, `export()` and `import_state()`.

| Helper | Main methods | Use for |
|---|---|---|
| `ConversationMemory(session)` | `add(role, content)`, `get_all()`, `get_recent(n)`, `update(i, content)`, `delete(i)`, `summarize(text)`, `get_summary()`, `clear()` | Conversation history and a running summary |
| `WorkingMemory(session)` | `set/get/delete`, `set_goal/get_goal`, `set_plan/get_plan`, `set_step`, `complete_step`, `state()` | Goal, plan and step tracking |
| `ToolState(session)` | `set_pending`, `resolve`, `set_history`, `history()`, `pending()`, `last_result()` | Pending tool calls and tool history |
| `ExecutionLock(session)` | `acquire(owner, ttl=60)`, `release(owner)`, `owner()`, `is_locked()`, `force_release()` | Ensuring one worker processes a session at a time |
| `InterruptState(session)` | `wait_for(event)`, `resolve(data)`, `waiting()`, `result()` | Waiting for human or external input |
| `WorkflowState(session)` | `set_current`, `complete_node`, `completed()`, `is_complete()`, `mark_complete()` | Tracking workflow progress |
| `MetricsState(session)` | `inc`, `record_latency`, `record_tokens`, `avg_latency()`, `stats()` | Per-session counters |
| `CheckpointManager(session)` | `snapshot()` → id, `restore(id)`, `list()`, `delete(id)` | Saving and restoring messages, working memory, tools, workflow and metrics |
| `PromptContextBuilder(session)` | `build(max_messages=20)`, `build_flat_text()` | Building LLM prompt context from session memory |

```python
convo = ConversationMemory(session)
convo.add("user", "Summarize the contract.")
convo.add("assistant", "Here is the summary...")

work = WorkingMemory(session)
work.set_goal("Review contract")
work.set_plan(["extract", "analyze", "report"])

cid = CheckpointManager(session).snapshot()

prompt_ctx = PromptContextBuilder(session).build(max_messages=10)
```

Other helpers built on a store:

| Helper | Module | Description |
|---|---|---|
| `IOChannel(store, name)` | `core.context.io` | Request/response channel: `submit(input)` → id, `fetch_input()`, `set_output(id, output)`, `wait_for_output(id, timeout=60)`, `get_status(id)`, `cleanup(id)` |
| `TaskQueue(store, name="default")` | `core.context.workspace` | Simple queue: `enqueue(task)` → id, `dequeue()`, `retry(id)` |
| `SharedWorkspace(store, name="global")` | `core.context.workspace` | `publish(key, value)` (keeps an event history), `subscribe(key)` |
| `StreamingBuffer(store, name)` | `core.context.workspace` | Token streaming: `start()`, `append(token)`, `complete()`, `get_partial()` |

> These helpers do read-modify-write on whole values (for example, the message list), so concurrent writers to the same session can overwrite each other. Use `ExecutionLock` when several workers may touch one session.

---

# Agent Context Cache Memory

The **Agent Context Cache** (`agent_context_cache`, in `libs/agents-addons`) keeps namespaced key-value data in process memory and broadcasts every write to NATS topics.

```python
from agent_context_cache.core.agent_context import AgentContextCache

ctx = AgentContextCache()

ctx.set("user_profile", {"name": "Alice", "age": 30})
ctx.get("user_profile")                              # {'name': 'Alice', 'age': 30}

ctx.set("session_token", "abc123", namespace="auth")
ctx.list_keys(namespace="auth")
ctx.list_namespaces()
ctx.clear_namespace("auth")

ctx.set_topics_list(["agent.context.updates"])       # broadcast topics (NATS at nats://localhost:4222)
```

Each write is published to every configured topic as:

```json
{
  "event_type": "context_update",
  "sender_subject_id": "<SUBJECT_ID>",
  "event_data": { "operation": "set", "namespace": "default", "key": "user_profile", "value": { "name": "Alice", "age": 30 } }
}
```

Data is not persisted. `enable_backup()` and `set_backup_settings()` only store configuration; no backup is performed. The package currently has import and shutdown issues. See [Agent Context Cache](concepts/agent-context-cache.md) for the full reference and known issues.

---

# Memory Grid — Client Developer Documentation

## Introduction

The **Memory Grid** is the integration layer between an agent and distributed **FrameDB** instances.
It allows the agent to maintain and access different kinds of memory through a single, consistent API.

Memory Grid supports three backend modes:

* **in-memory** — Fast, volatile storage for ephemeral data.
* **storage** — Persistent object storage for long-term retention.
* **streaming** — Ordered queues for real-time event processing.

All modes use the same `FrameDBClient` interface for storing, retrieving, streaming, and backing up data.

A typical workflow is:

1. **Declare a Memory Grid entry** in the agent’s subject specification.
2. **Initialize the FrameDB client** with cluster and routing URLs.
3. **Perform operations** according to the backend type.
4. **Optionally back up or restore** memory between instances or external storage.

---

## Registering Memory Grid in Subject Specification

A Memory Grid is declared in the subject specification using the `MemoryItem` structure.
The `memory_type` must be `"memory-grid"`, and the `memory_backend` specifies which mode to use.

---

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class MemoryItem:
    memory_id: str
    memory_type: str = "memory-grid"   # Fixed value
    memory_backend: str = ""           # "in-memory", "storage", or "streaming"
    memory_custom_config: Dict[str, Any] = field(default_factory=dict)
```

---

### Minimal Required Configuration

```json
{
  "memory_id": "memory-grid-01",
  "memory_type": "memory-grid",
  "memory_backend": "in-memory",
  "memory_custom_config": {
    "framedb_id": "framedb-inmem-1",
    "cluster_url": "http://framedb-cluster",
    "routing_url": "http://routing-service"
  }
}
```

---

### Field Descriptions

| Field                                    | Location | Type   | Description                                                         |
| ---------------------------------------- | -------- | ------ | ------------------------------------------------------------------- |
| **memory\_id**                           | root     | `str`  | Unique identifier for this memory entry in the subject spec.        |
| **memory\_type**                         | root     | `str`  | Must be `"memory-grid"` for Memory Grid integration.                |
| **memory\_backend**                      | root     | `str`  | Memory mode — `"in-memory"`, `"storage"`, or `"streaming"`.         |
| **memory\_custom\_config.framedb\_id**   | config   | `str`  | Target FrameDB instance ID.                                         |
| **memory\_custom\_config.cluster\_url**  | config   | `str`  | Base API URL for the FrameDB cluster.                               |
| **memory\_custom\_config.routing\_url**  | config   | `str`  | API URL for the FrameDB routing service.                            |
| **memory\_custom\_config.extra\_params** | config   | `dict` | Optional backend-specific settings (e.g., cache size, credentials). |

---

## Import and Setup

```python
from framedb_sdk import FrameDBClient

client = FrameDBClient(
    cluster_url="http://framedb-cluster",
    routing_url="http://routing-service"
)
```

---

## In-Memory Backend (`memory_backend="in-memory"`)

**Purpose:**
Fast, volatile memory backed by Redis for temporary state, shared context, or scratchpad data.

**Example:**

```python
client.set_object({
    "key": "session:123",
    "data": b"ephemeral binary data",
    "framedb_id": "framedb-inmem-1",
    "type": "in-memory"
})

result = client.get_object("session:123")
print(result["object"]["data"])
```

**Notes:**

* Data is not persisted after restart.
* Use `create_backup(...)` to persist important data.

---

## Storage Backend (`memory_backend="storage"`)

**Purpose:**
Persistent object storage backed by TiDB or another SQL-compatible DB.

**Example:**

```python
client.set_pythonic_object(
    key="model_snapshot_v1",
    obj={"weights": [1, 2, 3]},
    framedb_id="framedb-storage-1",
    framedb_type="storage"
)

res = client.get_pythonic_object("model_snapshot_v1")
print(res["object"]["python_object"])
```

**Notes:**

* Supports long-term retention and backups to object stores.

---

## Streaming Backend (`memory_backend="streaming"`)

**Purpose:**
Ordered queues backed by Redis Streams for event-driven workflows.

**Example — Continuous Listener:**

```python
for msg in client.listen_for_stream_data("agent-events", "framedb-stream-1"):
    print("New event:", msg)
```

**Example — Bulk Pull:**

```python
for msg in client.pull_all_stream_data("agent-events", "framedb-stream-1"):
    print("Event:", msg)
```

**Notes:**

* Maintains strict ordering.
* Suitable for live ingestion or inter-agent communication.

---

## Backup & Restore

```python
# Backup a single key
client.create_backup("session:123", "framedb-backup-1")

# Restore from backup
client.restore_from_backup(
    keys=["session:123"],
    framedb_id="framedb-inmem-1",
    framedb_type="in-memory",
    s3_credentials_dict={
        "bucket": "my-bucket",
        "access_key": "...",
        "secret_key": "...",
        "region": "ap-south-1"
    }
)
```

---

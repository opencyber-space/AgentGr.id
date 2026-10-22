# Agent P2P Module — Client Developer Documentation

## Introduction

The **Agent P2P Module** connects agents over one or more **meshes** — NATS servers that agents join to discover each other and exchange messages. It is provided by `PeersManager` in the agents SDK (`core.p2p`). Every agent instance and agent executor creates one automatically.

It supports:

* **Presence** — agents announce themselves when they join a mesh, so each agent knows which peers are reachable on which mesh.
* **Events** — broadcast an event to every agent on a mesh, or send one to a specific agent.
* **Task messages** — send a task to another agent's executor (see [Known issues](#known-issues)).

---

## Configuring Meshes

Meshes are configured when the agent is deployed (`allocation.meshes` in [`POST /api/deploy-agent`](agent-creation.md#3-deploy-the-agent)). The deployer passes them to every instance and executor in the `MESH_LIST` environment variable:

```json
{ "meshes": [ { "mesh_id": "mesh-a", "url": "nats://10.104.140.46:4222" } ] }
```

On start-up, `PeersManager` connects to each mesh's NATS URL. It subscribes to these subjects:

| NATS subject             | Subscribed by                 | Carries                                   |
| ------------------------ | ----------------------------- | ----------------------------------------- |
| `mesh`                   | instances and executors       | presence (`join` / `remove`) and broadcast events |
| `<SUBJECT_ID>__events`   | instances and executors       | events sent to this agent                 |
| `<SUBJECT_ID>__executor` | the agent executor only       | task messages for this agent              |

After subscribing, it publishes `{"event": "join", "subject_id": "<SUBJECT_ID>", "peer": <subject spec>}` on `mesh`.

---

## Using P2P in an Agent

The SDK creates the manager and exposes it as `context.p2p_manager`:

```python
from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main


class MyAgent:
    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    # Called for every custom event received from any mesh
    def on_event(self, event_name: str, event_data: dict) -> None:
        print("event", event_name, event_data)

    def on_preprocess(self, task: AgentTask):
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        p2p = self.context.p2p_manager

        # Broadcast to every agent on all meshes (or on mesh_ids=[...])
        p2p.broadcast_event_sync("task_started", {"task_id": task.task_id})

        # Send an event to one agent
        p2p.send_event_sync("need_review", {"task_id": task.task_id}, subject_id="reviewer-agent")

        return AgentResult(task_id=task.task_id, job_output={"ok": True})


main(MyAgent)
```

If the agent class defines `on_event(event_name, event_data)`, the SDK calls it for every `custom_event` received. Otherwise events are logged.

### Discovery

```python
p2p.list_meshes()   # {"mesh-a": {"http_url": "...", "nats_url": "nats://..."}}
p2p.list_agents()   # {"reviewer-agent": {"data": <peer subject spec>, "mesh_ids": ["mesh-a"]}}
```

Messages to a known agent are published only on the meshes where that agent was seen. Messages to an unknown agent go to all meshes.

### Event message formats

```json
// broadcast_event (subject "mesh")
{ "event": "custom_event", "event_name": "task_started", "event_data": {...}, "subject_id": "<sender>" }

// send_event (subject "<target>__events")
{ "event": "custom_event", "event_name": "need_review", "event_data": {...}, "from_subject_id": "<sender>" }
```

### Mesh management

```python
p2p.add_mesh_sync("mesh-b", http_url="http://mesh-b", nats_url="nats://10.0.0.9:4222")
p2p.remove_mesh_sync("mesh-b")
p2p.unregister_sync()      # announce "remove" on all meshes
p2p.close_sync()           # drain and close all connections
```

Every method has an `async` counterpart without the `_sync` suffix (for example `await p2p.broadcast_event(...)`). The `_sync` methods run on the manager's background event loop.

---

## Task Messages

```python
# Fire-and-forget: publish a task to <subject_id>__executor
p2p.send_sync(task_id="t-1", subject_id="worker-agent", task_data={"text": "hello"})

# Send and wait for a reply
reply = p2p.send_and_wait_sync(task_id="t-2", subject_id="worker-agent",
                               task_data={"text": "hello"}, timeout=30)
```

The published message is:

```json
{
  "task_id": "t-1",
  "task": { "text": "hello" },
  "origin": { "internal_task_id": "<uuid>", "sender_subject_id": "<SUBJECT_ID>" }
}
```

`send_and_wait` waits for an `{"event": "reply", "task_id": "<internal_task_id>", "status": "ok" | "error", "data": ...}` message. Use `reply_sync(...)` / `reply_error_sync(...)` to answer a task manually.

### Known issues

Task messaging over P2P does not currently complete end to end:

* The agent executor only accepts messages with `"event_type": "task"`, but `send` / `send_and_wait` don't set it. As a result the executor drops the message (`pre_process failed`).
* Replies are published on the NATS subject `<to_subject_id>`, which agent instances don't subscribe to. So `send_and_wait` waits until its `timeout` (forever without one).

To call another agent and wait for its result, use the Delegate API (`context.delegator.submit_and_wait(...)`) instead. **Events and presence** work as described above.

---

## Other Ways to Reach an Agent

| Mechanism | How | Notes |
|---|---|---|
| **Delegate API** | `context.delegator.submit_and_wait(subject_id=..., session_id=..., task_id=..., task_data=...)` or `POST <delegate>/api/submit-and-wait` | Synchronous request/response through the target's executor (uses `AGENT_DELEGATE_URL`) |
| **Direct hand-off** | `context.direct.submit(to="<subject_id>", session_id=..., task=task, job_data={...})` | Sends a task to another agent's executor with the **current task's** `output_ptr`, so the other agent replies straight to the original requester |
| **Instance WebSocket** | `ws://<instance>:8765` (port from `WS_PORT`) | Send `{"id": "1", "task": {"task_id": "t-1", "job_data": {...}}}` or `{"id": "1", "tasks": [...]}`; the reply is `{"id": "1", "ok": true, "data": {"results": [...]}}`. If `WS_BEARER_TOKEN` is set, connections must send `Authorization: Bearer <token>` |

---

# Agent Chat Server — Client Developer Documentation

## Introduction

The **Agent Chat Server** (`services/agents/chat-server`) is a FastAPI service that lets clients chat with an agent over a WebSocket. Each message is forwarded to the agent through the Delegate API (`/api/submit-and-wait`). Sessions and messages are stored in PostgreSQL (TimescaleDB when available).

---

## Configuration

| Environment variable  | Default                           | Description                         |
| --------------------- | --------------------------------- | ----------------------------------- |
| `DELEGATE_SERVER_URL` | `http://35.223.239.192:30725`     | Delegate API base URL               |
| `DATABASE_URL`        | `postgresql:///chatserver`        | PostgreSQL connection URL           |
| `HOST` / `PORT`       | `0.0.0.0` / `8080`                | Listen address                      |
| `LOG_LEVEL`           | `INFO`                            | Log level                           |

On start-up the server creates the `chat_sessions` and `chat_messages` tables (retrying the DB connection for up to about a minute). If TimescaleDB is available, `chat_messages` becomes a hypertable.

```bash
python3 main.py      # or: docker build -t chat-server . && docker run -p 8080:8080 chat-server
```

---

## WebSocket Protocol (`/ws`)

**1. Initialise** — the first message must name the agent:

```json
{ "type": "init", "subject_id": "agent-behavioral-code-creator" }
```

The server creates a session and replies:

```json
{ "type": "session", "session_id": "sess-1a2b3c4d", "subject_id": "agent-behavioral-code-creator" }
```

Any other first message gets `{"type": "error", ...}`, and the connection is closed (code 1008).

**2. Send tasks** — each subsequent message is forwarded to the agent:

```json
{ "type": "message", "task_id": "task-001", "task_data": { "user_request": "Function to add three numbers in python" } }
```

`task_id` is optional (generated if missing). `task_data` becomes the agent's `job_data`. The server waits up to 120 s for the Delegate API and replies:

```json
{ "type": "response", "task_id": "task-001", "data": { "success": true, "ack": { ... }, "output": { "job_output": { ... }, "...": "..." } } }
```

On failure it replies `{"type": "error", "task_id": "...", "message": "..."}`.

**3. Keep-alive** — `{"type": "ping"}` → `{"type": "pong"}`.

Every request, response and error is saved in `chat_messages` with `direction` = `request` / `response` / `error`.

---

## REST API

| Method & Path | Description |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /api/sessions?subject_id=<id>` | List sessions (newest first; up to 500 when not filtered) |
| `GET /api/sessions/{session_id}` | Get a session (404 if not found) |
| `GET /api/sessions/{session_id}/messages` | All messages of a session, oldest first |
| `GET /api/subjects/{subject_id}/sessions` | Sessions of one agent |

---

## Example Client

```python
import asyncio, json, websockets

async def run():
    async with websockets.connect("ws://localhost:8080/ws") as ws:
        await ws.send(json.dumps({"type": "init", "subject_id": "agent-behavioral-code-creator"}))
        print(json.loads(await ws.recv()))           # {"type": "session", ...}

        await ws.send(json.dumps({"type": "message",
                                  "task_data": {"user_request": "Function to add three numbers in python"}}))
        print(json.loads(await ws.recv()))           # {"type": "response", ...}

asyncio.run(run())
```

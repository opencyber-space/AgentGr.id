# Agent Sub-Systems

## Introduction

Agent sub-systems are modular components that extend an agent’s capabilities in a distributed AI environment.
By integrating different sub-systems, agents can delegate tasks, plan and execute behaviors, verify results, collaborate via voting, exchange messages in real time, and even communicate directly with other agents over peer-to-peer connections.

These sub-systems can be **selectively enabled** and **individually configured** in the agent’s Subject Specification, allowing a tailored setup that matches the agent’s role and responsibilities.
With them, we can achieve:

* **Scalable task delegation and orchestration**
* **LLM-powered behavior planning and decision-making**
* **Result verification workflows** for quality control
* **Collaborative decision-making** through voting systems
* **Real-time communication** via chat and event streaming
* **Direct peer-to-peer communication** without central brokers

---

| Sub-System Name                   | Purpose / Use Case                                                                                                                                                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delegation System**             | Allows an agent to delegate sub-tasks to other agents, track their execution status, and receive results. Supports REST APIs for CRUD operations and NATS for real-time task/result events.                 |
| **Behavior Controller**           | Generates and executes structured behavior plans using LLMs in two phases (planning & selection). Supports context-aware reasoning, integrates with AIOS or OpenAI, and persists results for reuse.         |
| **Verification System**           | Manages verification workflows for delegated tasks, storing results in MongoDB, and broadcasting live status via WebSocket. Supports single-agent and multi-agent verification with NATS for ad-hoc checks. |
| **Social Choice & Voting System** | Coordinates collaborative decision-making among multiple agents using voting strategies (majority, weighted, etc.). Provides REST APIs for social tasks and NATS for real-time result streaming.            |

--- 

# Agents Task Delegation — Client Developer Documentation

## Introduction

The **Agents Task Delegation** system allows one agent (the sender) to delegate sub-tasks to another agent (the target) in a distributed, event-driven environment.
It provides:

* **REST APIs** to create, update, query, and delete delegation records.
* **Status tracking** for live workflow stages.
* **NATS-based real-time communication** to send tasks and receive results.

A typical client workflow is:

1. **Create a delegation** via REST API.
2. **Notify the target agent** by publishing a `delegation_task` event on NATS.
3. **Track progress** through REST queries or WebSocket updates.
4. **Submit results** via REST or publish a `delegation_result` event.

---

## Registering Delegation System in Subject Specification

The **delegation system** can be registered as a sub-module in an agent’s **Subject Specification** by adding an entry of type `SubSystemItem`.
This configuration tells the agent where to reach the Delegations API, how to connect to the NATS messaging bus, and what defaults to apply when a delegation request does not specify all parameters.

---

### Data Class Reference

```python
@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)
```

---

### Minimal Required Configuration

Below is the minimal JSON block you need to include in the subject specification to enable the delegation system.

```json
{
  "sub_system_id": "delegation-system-01",
  "sub_system_type": "delegation-system",
  "sub_system_config": {
    "api_base_url": "http://delegations-api.default.svc.cluster.local:8080/delegations",
    "nats_url": "nats://nats.default.svc.cluster.local:4222",
    "default_workflow_level": 1,
    "default_delegation_type": "manual",
    "default_deadline_seconds": 3600
  }
}
```

---

### Field Descriptions

| Field                                              | Location | Type  | Description                                                                                              |
| -------------------------------------------------- | -------- | ----- | -------------------------------------------------------------------------------------------------------- |
| **sub\_system\_id**                                | root     | `str` | Unique identifier for this subsystem entry in the subject spec.                                          |
| **sub\_system\_type**                              | root     | `str` | Must be `"delegation-system"` for the delegation sub-module.                                             |
| **sub\_system\_config.api\_base\_url**             | config   | `str` | Base REST API URL for the Delegations service. All HTTP calls (create, update, query) will be sent here. |
| **sub\_system\_config.nats\_url**                  | config   | `str` | NATS server connection string used for sending and receiving real-time delegation events.                |
| **sub\_system\_config.default\_workflow\_level**   | config   | `int` | Default workflow stage for delegations when none is specified in a request.                              |
| **sub\_system\_config.default\_delegation\_type**  | config   | `str` | Default delegation type (`manual`, `system`, `auction`, etc.) when not specified.                        |
| **sub\_system\_config.default\_deadline\_seconds** | config   | `int` | Default allowed time (in seconds) before a delegated task expires.                                       |

---

### Example in a Subject Specification

If your **Subject Specification** is a JSON or YAML file that lists subsystems, you would add this as one entry in the `sub_systems` list:

```json
{
  "subject_id": "agent-alpha",
  "subject_type": "agent",
  "sub_systems": [
    {
      "sub_system_id": "delegation-system-01",
      "sub_system_type": "delegation-system",
      "sub_system_config": {
        "api_base_url": "http://delegations-api.default.svc.cluster.local:8080/delegations",
        "nats_url": "nats://nats.default.svc.cluster.local:4222",
        "default_workflow_level": 1,
        "default_delegation_type": "manual",
        "default_deadline_seconds": 3600
      }
    }
  ]
}
```


This ensures that when the agent needs to delegate a sub-task, it knows exactly **where** to send the API requests and **how** to communicate over NATS for event-driven updates, with safe defaults for workflow level, delegation type, and deadlines.


---

## Import and Setup

### REST Client

You can use `requests` or any HTTP library of your choice.

```python
import requests

BASE_URL = "http://<delegations-api-url>/delegations"
```

### NATS Client

Use the provided `NATSAPI` helper or `nats-py` directly.

```python
from delegation_tasks_pusher import NATSAPI

nats = NATSAPI(nats_url="nats://localhost:4222")
```

---

## Usage Guide

### Creating a Delegation

```python
payload = {
    "task_id": "task123",
    "sub_task_id": "sub456",
    "workflow_level": 1,
    "delegation_type": "manual",
    "target_subject_id": "agentB",
    "sender_subject_id": "agentA",
    "sub_task_data": {"param": "value"}
}

resp = requests.post(f"{BASE_URL}", json=payload)
print(resp.json())
```

**Expected Output:**

```json
{
  "success": true,
  "message": "Delegation created successfully"
}
```

---

### Sending a Delegation Event

```python
nats.push_event(
    topic="agentB",
    sender_subject_id="agentA",
    event_type="delegation_task",
    event_data={
        "task_id": "task123",
        "sub_task_id": "sub456",
        "delegation_id": "del789",
        "data": {"info": "Execute this subtask"}
    }
)
```

---

### Listening for Delegation Events

```python
import asyncio
import json
from nats.aio.client import Client as NATS

async def on_message(msg):
    data = json.loads(msg.data.decode())
    print(f"Received: {data}")

async def main():
    nc = NATS()
    await nc.connect("nats://localhost:4222")
    await nc.subscribe("agentB", cb=on_message)
    await asyncio.sleep(100)

asyncio.run(main())
```

---

### Fetching a Delegation by ID

```python
delegation_id = "del789"
resp = requests.get(f"{BASE_URL}/{delegation_id}")
print(resp.json())
```

---

### Querying Delegations

```python
query_payload = {"target_subject_id": "agentB"}
resp = requests.post(f"{BASE_URL}/query", json=query_payload)
print(resp.json())
```

---

### Updating Delegation Status

```python
status_payload = {
    "state": "in_progress",
    "time": 1717390000,
    "deadline": 1717400000
}
status_key = "execution"
delegation_id = "del789"

resp = requests.put(f"{BASE_URL}/{delegation_id}/status/{status_key}", json=status_payload)
print(resp.json())
```

---

### Submitting Final Result

```python
result_payload = {
    "state": "done",
    "delegation_result": "Execution completed successfully"
}

resp = requests.put(f"{BASE_URL}/submit_result/del789", json=result_payload)
print(resp.json())
```

---

### Receiving Results via NATS

If the target agent uses NATS to send back a result:

```python
nats.push_event(
    topic="agentA",
    sender_subject_id="agentB",
    event_type="delegation_result",
    event_data={
        "delegation_id": "del789",
        "result": "Execution completed successfully"
    }
)
```

---

### Deleting a Delegation

```python
delegation_id = "del789"
resp = requests.delete(f"{BASE_URL}/{delegation_id}")
print(resp.json())
```

---

# Behavior Controller — Client Developer Documentation

## Introduction

The **Behavior Controller** is a two-phase reasoning and execution module that uses Large Language Models (LLMs) to plan and select structured behaviors for an agent.
It provides:

* **REST APIs** for Phase 1 (behavior planning) and Phase 2 (behavior selection).
* **Context-aware processing** by incorporating prior results or FrameDB pointers.
* **Multiple LLM backends** (internal AIOS gRPC or external OpenAI API).
* **Persistent storage** for all task data and results to allow auditing and reuse.

A typical client workflow is:

1. **Submit a Phase 1 request** via REST API to generate a structured plan.
2. **Optionally reuse prior context** for memory-aware planning.
3. **Submit a Phase 2 request** with candidate behaviors to select the next action.
4. **Fetch results** via REST API or database queries.

---

## Registering Behavior Controller in Subject Specification

The **Behavior Controller** can be registered as a sub-module in an agent’s **Subject Specification** by adding an entry of type `SubSystemItem`.
This configuration tells the agent where to reach the Behavior Controller API and what defaults to use for LLM execution.

---

### Data Class Reference

```python
@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)
```

---

### Minimal Required Configuration

Below is the minimal JSON block you need to include in the subject specification to enable the Behavior Controller.

```json
{
  "sub_system_id": "behavior-controller-01",
  "sub_system_type": "behavior-controller",
  "sub_system_config": {
    "api_base_url": "http://behavior-controller.default.svc.cluster.local:8888",
    "llm_backend": "aios", 
    "default_phase1_template_id": "phase1-default",
    "default_phase2_template_id": "phase2-default"
  }
}
```

---

### Field Descriptions

| Field                                                 | Location | Type  | Description                                                                                                     |
| ----------------------------------------------------- | -------- | ----- | --------------------------------------------------------------------------------------------------------------- |
| **sub\_system\_id**                                   | root     | `str` | Unique identifier for this subsystem entry in the subject spec.                                                 |
| **sub\_system\_type**                                 | root     | `str` | Must be `"behavior-controller"` for the behavior control sub-module.                                            |
| **sub\_system\_config.api\_base\_url**                | config   | `str` | Base REST API URL for the Behavior Controller service. All HTTP calls (Phase 1 and Phase 2 processing) go here. |
| **sub\_system\_config.llm\_backend**                  | config   | `str` | LLM execution backend (`aios` for internal AIOS gRPC, `openai` for OpenAI API).                                 |
| **sub\_system\_config.default\_phase1\_template\_id** | config   | `str` | ID of the default Phase 1 prompt template to use when none is specified.                                        |
| **sub\_system\_config.default\_phase2\_template\_id** | config   | `str` | ID of the default Phase 2 prompt template to use when none is specified.                                        |

---

### Example in a Subject Specification

```json
{
  "subject_id": "agent-beta",
  "subject_type": "agent",
  "sub_systems": [
    {
      "sub_system_id": "behavior-controller-01",
      "sub_system_type": "behavior-controller",
      "sub_system_config": {
        "api_base_url": "http://behavior-controller.default.svc.cluster.local:8888",
        "llm_backend": "aios",
        "default_phase1_template_id": "phase1-default",
        "default_phase2_template_id": "phase2-default"
      }
    }
  ]
}
```

This ensures that when the agent needs to plan or select behaviors, it knows exactly **where** to send API requests, **which LLM backend** to use, and **which default templates** to apply.

---

## Import and Setup

### REST Client

You can use `requests` or any HTTP client library.

```python
import requests

BASE_URL = "http://<behavior-controller-api-url>"
```

---

## Usage Guide

### Submitting a Phase 1 Task (Behavior Planning)

```python
payload = {
    "search_id": "task-001",
    "phase_1_data": {
        "input_description": "Plan a 3-step workflow to process satellite imagery."
    }
}

resp = requests.post(f"{BASE_URL}/process-phase-1-task", json=payload)
print(resp.json())
```

**Expected Output:**

```json
{
  "success": true,
  "data": {
    "status": "success",
    "processed_data": {
      "plan": [
        {"task_id": "t1", "description": "Download images", "execution_type": "tool_call", "tool_id": "image_fetcher"},
        {"task_id": "t2", "description": "Preprocess images", "execution_type": "dsl", "dsl_id": "preprocess.dsl"},
        {"task_id": "t3", "description": "Run classification", "execution_type": "tool_call", "tool_id": "classifier"}
      ]
    }
  }
}
```

---

### Submitting a Phase 2 Task (Behavior Selection)

```python
payload = {
    "search_id": "task-001",
    "phase_2_data": {
        "planned_tasks": [
            {"task_id": "t1", "description": "Download images"},
            {"task_id": "t2", "description": "Preprocess images"},
            {"task_id": "t3", "description": "Run classification"}
        ]
    }
}

resp = requests.post(f"{BASE_URL}/process-phase-2-task", json=payload)
print(resp.json())
```

**Expected Output:**

```json
{
  "success": true,
  "data": {
    "status": "success",
    "processed_data": {
      "uid": "t2"
    }
  }
}
```

---

### Fetching Historical Phase 1 Results

```python
resp = requests.get(f"{BASE_URL}/phase1-results/latest?limit=5")
print(resp.json())
```

---

### Example: Switching LLM Backend in Config

If you want to use OpenAI instead of AIOS:

```json
{
  "sub_system_id": "behavior-controller-01",
  "sub_system_type": "behavior-controller",
  "sub_system_config": {
    "api_base_url": "http://behavior-controller.default.svc.cluster.local:8888",
    "llm_backend": "openai",
    "default_phase1_template_id": "phase1-default",
    "default_phase2_template_id": "phase2-default"
  }
}
```

---

# Social Choice & Voting System — Client Developer Documentation

## Introduction

The **Social Choice & Voting System** coordinates collaborative decision-making among multiple agents.
It provides:

* **REST APIs** to create and manage social tasks (voting workflows).
* **NATS integration** for receiving final voting results in real time.
* Support for **multiple voting strategies** (e.g., majority, weighted).

A typical client workflow is:

1. **Create a social voting task** via REST.
2. **Invite participants** and define the goal data.
3. **Wait for voting completion** via NATS.
4. **Retrieve and process the voting result**.

---

## Registering Social Choice & Voting System in Subject Specification

Add a `SubSystemItem` entry so the agent can connect to the social voting APIs and NATS result stream.

### Data Class Reference

```python
@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)
```

### Minimal Required Configuration

```json
{
  "sub_system_id": "social-choice-voting-01",
  "sub_system_type": "social-choice-voting",
  "sub_system_config": {
    "api_base_url": "http://social-voting-api.default.svc.cluster.local:5001",
    "nats_url": "nats://nats.default.svc.cluster.local:4222"
  }
}
```

**Fields**

* **api\_base\_url** – REST API base path for social task operations.
* **nats\_url** – NATS connection for streaming voting results.

---

## Import and Setup

```python
from agent_sdk.verification import SocialTaskService

service = SocialTaskService("http://localhost:5001")
```

---

## Usage Guide

### Creating a Social Task

```python
task = service.create_social_task(
    created_by_subject_id="agent_a",
    voting_type="majority",
    invited_subject_ids=["agent_b", "agent_c"],
    goal_data={"decision": "select_strategy"},
    status="pending",
    report={},
    voting_pqt_dsl_id="dsl_123",
    choice_evaluation_dsl="eval_dsl",
    deadline_time=1688888888
)

print("Created Social Task:", task.social_task_id)
```

### Waiting for Voting Result via NATS

```python
waiter = service.create_waiter_for_task(task_id=task.social_task_id)
result = waiter.get()
print("Voting Result:", result.voting_result)
```

--- 

# Verification System — Client Developer Documentation

## Introduction

The **Verification System** coordinates task verification workflows for agents, supporting both single-subject and multi-agent verification.
It provides:

* **REST APIs** for creating, updating, querying, and deleting verification tasks.
* **WebSocket server** for live result updates.
* **NATS integration** for ad-hoc verifications and social choice voting.

A typical client workflow is:

1. **Create a verification task** via REST.
2. **Notify or invite agents** over NATS.
3. **Wait for results** via WebSocket or NATS.
4. **Submit verification results** back to the system.

---

## Registering Verification System in Subject Specification

Add a `SubSystemItem` entry to the subject spec so the agent knows how to reach the Verification API and connect to NATS for events.

### Data Class Reference

```python
@dataclass
class SubSystemItem:
    sub_system_id: str
    sub_system_type: str = ""
    sub_system_config: Dict[str, Any] = field(default_factory=dict)
```

### Minimal Required Configuration

```json
{
  "sub_system_id": "verification-system-01",
  "sub_system_type": "verification-system",
  "sub_system_config": {
    "api_base_url": "http://verification-api.default.svc.cluster.local:5000/verifications",
    "nats_url": "nats://nats.default.svc.cluster.local:4222",
    "websocket_url": "ws://verification-api.default.svc.cluster.local:8765/ws"
  }
}
```

**Fields**

* **api\_base\_url** – REST API base path for all verification endpoints.
* **nats\_url** – NATS connection for ad-hoc verifications/voting.
* **websocket\_url** – WebSocket endpoint for real-time verification status.

---

## Import and Setup

```python
import requests
from agent_sdk.verification import VerificationClient, AdhocVerification
```

---

## Usage Guide

### Creating a Verification

```python
client = VerificationClient("http://localhost:5000")
resp = client.create_verification(
    task_id="task_123",
    subject_id="agent_a",
    verification_type="manual"
)
print(resp)
```

### Submitting a Result

```python
resp = requests.post(
    "http://localhost:5000/verifications/<verification_id>/submit-result",
    json={
        "target_subject_id": "agent_1",
        "status": "completed",
        "result_data": {
            "verification_result": {"pass": True},
            "verification_output": {"notes": "All checks passed"}
        }
    }
)
print(resp.json())
```

### Listening for Updates (WebSocket)

```python
import asyncio, websockets

async def listen():
    async with websockets.connect("ws://localhost:8765/ws/agent_a/task_123") as ws:
        while True:
            msg = await ws.recv()
            print("Update:", msg)

asyncio.run(listen())
```

### Ad-hoc Verification via NATS

```python
verifier = AdhocVerification("nats://localhost:4222")
verifier.push(
    subject="agent_a__task_123",
    event_type="start_verification",
    sender_subject_id="agent_b",
    event_data={"input": "data"}
)
verifier.close()
```

---

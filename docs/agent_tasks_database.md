# Agent Tasks Database

## Introduction

The **Agent Local Tasks DB** is a modular, MongoDB-backed storage system designed to persist and manage the full lifecycle of hierarchical AI workflows executed by autonomous agents. It enables agents to construct, store, retrieve, query, and finalize tasks that are broken down into:

* **Meta workflows**: High-level composite tasks defined by the agent's mission logic.
* **Sub-tasks**: Intermediate units representing logical steps within a meta workflow.
* **Behavior tasks**: Atomic actions or operations executed by an agent or system module.

Each component of the task hierarchy is stored as a separate document with its own schema and collection. This design promotes clarity, traceability, and decoupled processing of different task layers.

Additionally, the DB stores **output artifacts** for each task level, ensuring that:

* Intermediate and final results can be reused
* Downstream tasks have access to relevant execution context
* Agents can introspect previous behavior and reasoning steps

This DB forms the persistent memory substrate for agentic execution environments, supporting use cases such as:

* Workflow orchestration
* Behavior tracking and explanation
* Task versioning and auditability
* Fault recovery and step re-execution

The provided REST APIs allow for CRUD operations over all task entities, enabling smooth integration with agent runtimes, monitoring dashboards, or orchestration systems.

---

## Schema

### 1. `MetaWorkflowTask`

```python
@dataclass
class MetaWorkflowTask:
    task_id: str = field(default_factory=lambda: str(uuid4()))
    meta_workflow_id: str = ""
    dsl_workflow_id: str = ""
    sub_task_ids: List[str] = field(default_factory=list)
    meta_workflow_graph: Dict[str, Any] = field(default_factory=dict)
    personality_workflow_id: str = ""
    personality_type: str = ""
    is_finalized: bool = False
```

| Field                     | Type             | Description                               |
| ------------------------- | ---------------- | ----------------------------------------- |
| `task_id`                 | `str`            | Unique ID for the meta workflow           |
| `meta_workflow_id`        | `str`            | ID representing the high-level workflow   |
| `dsl_workflow_id`         | `str`            | Associated DSL workflow ID                |
| `sub_task_ids`            | `List[str]`      | Sub-task IDs under this meta-task         |
| `meta_workflow_graph`     | `Dict[str, Any]` | Workflow graph topology                   |
| `personality_workflow_id` | `str`            | ID of the associated personality workflow |
| `personality_type`        | `str`            | Category/type of the personality          |
| `is_finalized`            | `bool`           | Whether the task has been finalized       |

---

### 2. `SubTaskDefinition`

```python
@dataclass
class SubTaskDefinition:
    sub_task_id: str = field(default_factory=lambda: str(uuid4()))
    personality_workflow_id: str = ""
    personality_type: str = ""
    behavior_workflow_id: str = ""
    behavior_task_ids: List[str] = field(default_factory=list)
    behavior_dag_data: Dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    prev_sub_task_id: Optional[str] = None
    is_finalized: bool = False
```

| Field                     | Type             | Description                                   |
| ------------------------- | ---------------- | --------------------------------------------- |
| `sub_task_id`             | `str`            | Unique ID for the sub-task                    |
| `personality_workflow_id` | `str`            | Personality workflow ID                       |
| `personality_type`        | `str`            | Type of personality behavior                  |
| `behavior_workflow_id`    | `str`            | ID of behavior workflow                       |
| `behavior_task_ids`       | `List[str]`      | IDs of behavior tasks linked                  |
| `behavior_dag_data`       | `Dict[str, Any]` | DAG representation of internal behavior tasks |
| `task_id`                 | `str`            | Parent meta task ID                           |
| `prev_sub_task_id`        | `Optional[str]`  | Previous sub-task ID (for chaining)           |
| `is_finalized`            | `bool`           | Whether the sub-task is finalized             |

---

### 3. `BehaviorTaskDefinition`

```python
@dataclass
class BehaviorTaskDefinition:
    behavior_task_id: str = field(default_factory=lambda: str(uuid4()))
    sub_task_id: str = ""
    action_id: str = ""
    action_type: str = ""
    action_sub_type: str = ""
    is_finalized: bool = False
```

| Field              | Type   | Description                         |
| ------------------ | ------ | ----------------------------------- |
| `behavior_task_id` | `str`  | Unique ID for the behavior task     |
| `sub_task_id`      | `str`  | Associated sub-task ID              |
| `action_id`        | `str`  | ID of the action                    |
| `action_type`      | `str`  | Main type of action                 |
| `action_sub_type`  | `str`  | Detailed subtype of the action      |
| `is_finalized`     | `bool` | Whether the task has been finalized |

---

### 4. `TaskOutputData`

```python
@dataclass
class TaskOutputData:
    task_id: str = ""
    output_framedb_ptr: Dict[str, Any] = field(default_factory=dict)
    finalized_sub_task_ids: List[str] = field(default_factory=list)
    task_data_ptr: Dict[str, Any] = field(default_factory=dict)
```

| Field                    | Type             | Description                         |
| ------------------------ | ---------------- | ----------------------------------- |
| `task_id`                | `str`            | Meta-task ID this output belongs to |
| `output_framedb_ptr`     | `Dict[str, Any]` | Pointer to output in FrameDB        |
| `finalized_sub_task_ids` | `List[str]`      | List of finalized sub-task IDs      |
| `task_data_ptr`          | `Dict[str, Any]` | Additional task output data         |

---

### 5. `SubTaskOutputData`

```python
@dataclass
class SubTaskOutputData:
    sub_task_id: str = ""
    output_framedb_ptr: Dict[str, Any] = field(default_factory=dict)
    processor_subject_ids: List[str] = field(default_factory=list)
    processor_subjects_graph: Dict[str, Any] = field(default_factory=dict)
    is_finalized_step: bool = False
    sub_task_data_ptr: Dict[str, Any] = field(default_factory=dict)
    prev_sub_task_id: Optional[str] = None
```

| Field                      | Type             | Description                        |
| -------------------------- | ---------------- | ---------------------------------- |
| `sub_task_id`              | `str`            | Sub-task ID                        |
| `output_framedb_ptr`       | `Dict[str, Any]` | Pointer to output in FrameDB       |
| `processor_subject_ids`    | `List[str]`      | Subject IDs involved in processing |
| `processor_subjects_graph` | `Dict[str, Any]` | Graph of processor subjects        |
| `is_finalized_step`        | `bool`           | Whether the step is finalized      |
| `sub_task_data_ptr`        | `Dict[str, Any]` | Additional data                    |
| `prev_sub_task_id`         | `Optional[str]`  | Previous sub-task ID for linkage   |

---

### 6. `BehaviorTaskOutputData`

```python
@dataclass
class BehaviorTaskOutputData:
    behavior_task_id: str = ""
    output_framedb_ptr: Dict[str, Any] = field(default_factory=dict)
    processor_subject_ids: List[str] = field(default_factory=list)
    processor_subjects_graph: Dict[str, Any] = field(default_factory=dict)
    processor_modules_graph: Dict[str, Any] = field(default_factory=dict)
    is_finalized_step: bool = False
    behavior_data_ptr: Dict[str, Any] = field(default_factory=dict)
```

| Field                      | Type             | Description                           |
| -------------------------- | ---------------- | ------------------------------------- |
| `behavior_task_id`         | `str`            | Behavior task ID                      |
| `output_framedb_ptr`       | `Dict[str, Any]` | Pointer to behavior output in FrameDB |
| `processor_subject_ids`    | `List[str]`      | Subject IDs that processed this task  |
| `processor_subjects_graph` | `Dict[str, Any]` | Subject-level execution graph         |
| `processor_modules_graph`  | `Dict[str, Any]` | Module-level execution graph          |
| `is_finalized_step`        | `bool`           | Whether this step is finalized        |
| `behavior_data_ptr`        | `Dict[str, Any]` | Additional behavior task output       |

---


Certainly. Below is the updated **API documentation** for the **Agent Local Tasks DB**, now including the `GET`, `DELETE`, and `POST /query` APIs for each entity.

---

## APIs

All APIs use JSON over HTTP. Base URL assumed: `http://localhost:8000`

Each `query` endpoint accepts a JSON filter using MongoDB-style syntax.

---

### MetaWorkflowTask

#### GET `/meta-tasks/<task_id>`

**Description**: Retrieve a meta-task by ID.

```bash
curl -X GET http://localhost:8000/meta-tasks/<task_id>
```

#### DELETE `/meta-tasks/<task_id>`

**Description**: Delete a meta-task by ID.

```bash
curl -X DELETE http://localhost:8000/meta-tasks/<task_id>
```

#### POST `/meta-tasks/query`

**Description**: Query meta-tasks by filter.

```bash
curl -X POST http://localhost:8000/meta-tasks/query \
     -H "Content-Type: application/json" \
     -d '{"meta_workflow_id": "mw1"}'
```

---

### SubTaskDefinition

#### GET `/sub-tasks/<sub_task_id>`

```bash
curl -X GET http://localhost:8000/sub-tasks/<sub_task_id>
```

#### DELETE `/sub-tasks/<sub_task_id>`

```bash
curl -X DELETE http://localhost:8000/sub-tasks/<sub_task_id>
```

#### POST `/sub-tasks/query`

```bash
curl -X POST http://localhost:8000/sub-tasks/query \
     -H "Content-Type: application/json" \
     -d '{"task_id": "meta123"}'
```

---

### BehaviorTaskDefinition

#### GET `/behavior-tasks/<behavior_task_id>`

```bash
curl -X GET http://localhost:8000/behavior-tasks/<behavior_task_id>
```

#### DELETE `/behavior-tasks/<behavior_task_id>`

```bash
curl -X DELETE http://localhost:8000/behavior-tasks/<behavior_task_id>
```

#### POST `/behavior-tasks/query`

```bash
curl -X POST http://localhost:8000/behavior-tasks/query \
     -H "Content-Type: application/json" \
     -d '{"sub_task_id": "sub123"}'
```

---

### TaskOutputData

#### GET `/task-outputs/<task_id>`

```bash
curl -X GET http://localhost:8000/task-outputs/<task_id>
```

#### DELETE `/task-outputs/<task_id>`

```bash
curl -X DELETE http://localhost:8000/task-outputs/<task_id>
```

#### POST `/task-outputs/query`

```bash
curl -X POST http://localhost:8000/task-outputs/query \
     -H "Content-Type: application/json" \
     -d '{"task_id": "meta123"}'
```

---

### SubTaskOutputData

#### GET `/sub-task-outputs/<sub_task_id>`

```bash
curl -X GET http://localhost:8000/sub-task-outputs/<sub_task_id>
```

#### DELETE `/sub-task-outputs/<sub_task_id>`

```bash
curl -X DELETE http://localhost:8000/sub-task-outputs/<sub_task_id>
```

#### POST `/sub-task-outputs/query`

```bash
curl -X POST http://localhost:8000/sub-task-outputs/query \
     -H "Content-Type: application/json" \
     -d '{"is_finalized_step": true}'
```

---

### BehaviorTaskOutputData

#### GET `/behavior-task-outputs/<behavior_task_id>`

```bash
curl -X GET http://localhost:8000/behavior-task-outputs/<behavior_task_id>
```

#### DELETE `/behavior-task-outputs/<behavior_task_id>`

```bash
curl -X DELETE http://localhost:8000/behavior-task-outputs/<behavior_task_id>
```

#### POST `/behavior-task-outputs/query`

```bash
curl -X POST http://localhost:8000/behavior-task-outputs/query \
     -H "Content-Type: application/json" \
     -d '{"processor_subject_ids": {"$in": ["agent1"]}}'
```

---

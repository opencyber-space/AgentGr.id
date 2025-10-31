# Agents DB

## Introduction

This service provides a modular and extensible system for managing and searching "Subjects" and "RuntimeSubjects" in a registry. It offers both **REST APIs** and a **WebSocket-based search interface**. The platform is built to support:

* Centralized registration of declarative subject metadata
* Dynamic runtime instantiation with environment-specific metadata
* Querying and transformation of subject data using logical filters and custom DSL workflows
* Real-time DSL-driven search over both declarative and runtime subject stores

### Key Components

| Component             | Description                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| **Subject**           | Represents static metadata about an entity, including versioning, type, tags, and DSL bindings     |
| **RuntimeSubject**    | Represents a contextual instance of a Subject with additional runtime and org-specific information |
| **SubjectsDB**        | MongoDB-based CRUD layer for managing `Subject` entities                                           |
| **RuntimeSubjectsDB** | MongoDB-based CRUD layer for managing `RuntimeSubject` instances                                   |
| **Flask API Server**  | Exposes RESTful endpoints for create, update, delete, and query operations                         |
| **Search Server**     | WebSocket-based interface supporting dynamic filtering and DSL-based search                        |
| **DSL Executor**      | Executes workflow-defined logic on filtered subject datasets                                       |


Certainly — here's the **Schema** section with data classes and a detailed field explanation table for both `Subject` and `RuntimeSubject`.

---

## Schema

The system manages two core entities:

1. `Subject` – Represents a static or declarative metadata definition of an entity.
2. `RuntimeSubject` – Represents a contextual instantiation of a `Subject` with runtime metadata like execution info, database bindings, and org-level associations.

---

### `Subject` Data Class

```python
@dataclass
class SubjectVersion:
    version: str
    release_tag: str

@dataclass
class Subject:
    subject_id: str = field(init=False)
    subject_name: str
    subject_type: str
    subject_version: SubjectVersion
    subject_description: str
    subject_search_tags: List[str] = field(default_factory=list)
    subject_traits: List[str] = field(default_factory=list)
    subject_role: str = field(default_factory=str)
    subject_dsls: Dict[str, str] = field(default_factory=dict)
```

| Field                 | Type             | Description                                                    |
| --------------------- | ---------------- | -------------------------------------------------------------- |
| `subject_id`          | `str` (auto-gen) | Unique ID composed of type, name, version, and release tag     |
| `subject_name`        | `str`            | Descriptive name of the subject                                |
| `subject_type`        | `str`            | Functional type/category of the subject (e.g., agent, dataset) |
| `subject_version`     | `SubjectVersion` | Object with semantic `version` and `release_tag`               |
| `subject_description` | `str`            | Textual description                                            |
| `subject_search_tags` | `List[str]`      | Searchable tags for indexing or filtering                      |
| `subject_traits`      | `List[str]`      | Logical capabilities or tags associated with the subject       |
| `subject_role`        | `str`            | Role the subject plays (e.g., "coordinator", "worker")         |
| `subject_dsls`        | `Dict[str, str]` | Mapping from DSL types to workflow IDs                         |

---

### `RuntimeSubject` Data Class

```python
@dataclass
class RuntimeSubjectVersion:
    version: str
    release_tag: str

@dataclass
class RuntimeSubject:
    subject_id: str = field(init=False)
    subject_name: str
    subject_type: str
    subject_version: RuntimeSubjectVersion
    subject_description: str
    subject_search_tags: List[str] = field(default_factory=list)
    subject_traits: List[str] = field(default_factory=list)
    subject_role: str = field(default_factory=str)
    subject_dsls: Dict[str, str] = field(default_factory=dict)
    runtime_info: Dict[str, str] = field(default_factory=dict)
    runtime_db_info: Dict[str, str] = field(default_factory=dict)
    orgs: List[str] = field(default_factory=list)
```

| Field                 | Type                    | Description                                                                |
| --------------------- | ----------------------- | -------------------------------------------------------------------------- |
| `subject_id`          | `str` (auto-gen)        | Same format as in `Subject`                                                |
| `subject_name`        | `str`                   | Same as `Subject`                                                          |
| `subject_type`        | `str`                   | Same as `Subject`                                                          |
| `subject_version`     | `RuntimeSubjectVersion` | Identical structure to `SubjectVersion`                                    |
| `subject_description` | `str`                   | Same as `Subject`                                                          |
| `subject_search_tags` | `List[str]`             | Same as `Subject`                                                          |
| `subject_traits`      | `List[str]`             | Same as `Subject`                                                          |
| `subject_role`        | `str`                   | Same as `Subject`                                                          |
| `subject_dsls`        | `Dict[str, str]`        | Same as `Subject`                                                          |
| `runtime_info`        | `Dict[str, str]`        | Runtime-specific execution metadata (e.g., endpoint, node info, resources) |
| `runtime_db_info`     | `Dict[str, str]`        | Runtime DB bindings (e.g., cache ID, collection name)                      |
| `orgs`                | `List[str]`             | List of org IDs or names associated with this runtime subject              |

---

Certainly. Here's the **cleaned-up REST API documentation** with all emojis removed for professional formatting:

---

## APIs

This section documents the RESTful endpoints exposed by the service for managing `Subject` and `RuntimeSubject` records.

---

### GET `/subjects/<subject_id>`

Fetch a single subject by its unique ID.

#### Response

* `200 OK` with subject data on success
* `404 Not Found` if subject doesn't exist

#### cURL Example

```bash
curl -X GET http://localhost:5000/subjects/sample.subject:1.0-stable
```

---

### PUT `/subjects/<subject_id>`

Update an existing subject using partial or full field data.

#### Payload

```json
{
  "subject_description": "Updated description",
  "subject_search_tags": ["ai", "policy"]
}
```

#### cURL Example

```bash
curl -X PUT http://localhost:5000/subjects/sample.subject:1.0-stable \
     -H "Content-Type: application/json" \
     -d '{"subject_description": "Updated description", "subject_search_tags": ["ai", "policy"]}'
```

---

### DELETE `/subjects/<subject_id>`

Delete a subject by its ID.

#### cURL Example

```bash
curl -X DELETE http://localhost:5000/subjects/sample.subject:1.0-stable
```

---

### GET `/subjects`

List all registered subjects.

#### cURL Example

```bash
curl http://localhost:5000/subjects
```

---

### POST `/subjects/query`

Run a custom Mongo-style query on subjects.

#### Payload

```json
{
  "subject_type": "agent",
  "subject_role": "coordinator"
}
```

#### cURL Example

```bash
curl -X POST http://localhost:5000/subjects/query \
     -H "Content-Type: application/json" \
     -d '{"subject_type": "agent", "subject_role": "coordinator"}'
```

---

### GET `/runtime_subjects/<subject_id>`

Fetch a runtime subject by ID.

#### cURL Example

```bash
curl http://localhost:5000/runtime_subjects/sample.subject:1.0-stable
```

---

### PUT `/runtime_subjects/<subject_id>`

Update a runtime subject.

#### Payload

```json
{
  "runtime_info": {
    "host": "node-1",
    "status": "active"
  }
}
```

#### cURL Example

```bash
curl -X PUT http://localhost:5000/runtime_subjects/sample.subject:1.0-stable \
     -H "Content-Type: application/json" \
     -d '{"runtime_info": {"host": "node-1", "status": "active"}}'
```

---

### DELETE `/runtime_subjects/<subject_id>`

Delete a runtime subject.

#### cURL Example

```bash
curl -X DELETE http://localhost:5000/runtime_subjects/sample.subject:1.0-stable
```

---

### GET `/runtime_subjects`

List all runtime subjects.

#### cURL Example

```bash
curl http://localhost:5000/runtime_subjects
```

---

### POST `/runtime_subjects/query`

Query runtime subjects with a structured filter.

#### Payload

```json
{
  "subject_type": "agent"
}
```

#### cURL Example

```bash
curl -X POST http://localhost:5000/runtime_subjects/query \
     -H "Content-Type: application/json" \
     -d '{"subject_type": "agent"}'
```

---

### POST `/runtime_subjects/create`

Create a runtime version from a registered subject.

#### Payload

```json
{
  "subject_id": "sample.subject:1.0-stable",
  "runtime_data": {
    "runtime_info": {
      "host": "node-1"
    },
    "runtime_db_info": {
      "collection": "live_subjects"
    },
    "orgs": ["orgA", "orgB"]
  }
}
```

#### cURL Example

```bash
curl -X POST http://localhost:5000/runtime_subjects/create \
     -H "Content-Type: application/json" \
     -d @runtime_payload.json
```

---

### PUT `/runtime_subjects/<subject_id>/orgs`

Update organization bindings for a runtime subject.

#### Payload

```json
{
  "orgs_to_add": ["orgX"],
  "orgs_to_remove": ["orgB"]
}
```

#### cURL Example

```bash
curl -X PUT http://localhost:5000/runtime_subjects/sample.subject:1.0-stable/orgs \
     -H "Content-Type: application/json" \
     -d '{"orgs_to_add": ["orgX"], "orgs_to_remove": ["orgB"]}'
```

---


## Search Server

The Search Server enables **dynamic querying and DSL-powered transformation** over both registered `Subject` and `RuntimeSubject` data. It operates as a **WebSocket server** running on port `5001`, allowing real-time search requests with logical filters and optional DSL workflows.

---

### WebSocket Endpoint

```
ws://<host>:5001
```

---

### Message Format

#### Request Payload

```json
{
  "search_type": "registry" | "runtime_db",
  "workflow_id": "optional_workflow_id",
  "query": {
    "logicalOperator": "AND",
    "conditions": [
      {
        "variable": "subject_type",
        "operator": "==",
        "value": "agent"
      },
      {
        "variable": "subject_traits",
        "operator": "IN",
        "value": ["interactive", "autonomous"]
      }
    ]
  }
}
```

| Field         | Type   | Description                                                                          |
| ------------- | ------ | ------------------------------------------------------------------------------------ |
| `search_type` | string | Must be either `"registry"` (for `Subject`) or `"runtime_db"` (for `RuntimeSubject`) |
| `workflow_id` | string | Optional DSL workflow ID used to post-process filtered results                       |
| `query`       | object | Logical condition for filtering subjects using Mongo-style DSL                       |

---

### Supported Operators in Query

| Operator | Meaning                   | Notes                                |
| -------- | ------------------------- | ------------------------------------ |
| `==`     | Exact match               | `{"subject_type": "agent"}`          |
| `IN`     | List membership           | `{"subject_traits": {"$in": [...]}}` |
| `LIKE`   | Pattern match (regex)     | Use `"*"` as wildcard                |
| `<`/`<=` | Numeric/string comparison |                                      |
| `>`/`>=` | Numeric/string comparison |                                      |

Nested logical conditions using `AND` or `OR` are supported using:

```json
{
  "logicalOperator": "OR",
  "conditions": [
    { "variable": "subject_type", "operator": "==", "value": "agent" },
    { "variable": "subject_type", "operator": "==", "value": "tool" }
  ]
}
```

---

### Response Payload

#### On Success

```json
{
  "success": true,
  "data": [ /* filtered or DSL-transformed list of subjects */ ]
}
```

#### On Error

```json
{
  "success": false,
  "error": "error description"
}
```

---

### Example Usage (Python)

```python
import asyncio
import websockets
import json

async def query_subjects():
    uri = "ws://localhost:5001"
    async with websockets.connect(uri) as websocket:
        request = {
            "search_type": "runtime_db",
            "workflow_id": "sample_dsl_workflow",
            "query": {
                "logicalOperator": "AND",
                "conditions": [
                    {"variable": "subject_role", "operator": "==", "value": "coordinator"},
                    {"variable": "orgs", "operator": "IN", "value": ["orgA"]}
                ]
            }
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        print("Search result:", json.loads(response))

asyncio.run(query_subjects())
```

---

### Threading and Startup

The WebSocket server is automatically started as a daemon thread when the Flask server boots via:

```python
from search import run_search_server

def run_server():
    run_search_server()  # starts WebSocket in background
    app.run(host="0.0.0.0", port=5000)
```

This ensures the search server operates concurrently with the main REST API.

---

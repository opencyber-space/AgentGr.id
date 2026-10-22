# Agent Basic Utilities

## Object Storage

This document provides guidance on how to use the `ObjectStoreAPI` class to interact with an S3-compatible object storage backend (such as AWS S3, MinIO, Ceph, etc.). The class supports uploading and downloading files using various data formats (file path, bytes, or in-memory buffers).

---

### Introduction

The `ObjectStoreAPI` class provides a simple and extensible interface to:

* Upload files to an S3-compatible bucket.
* Download files from a bucket to a path, a buffer, or directly as bytes.

It supports:

* Credentials and region-based authentication.
* Multiple input and output types.
* Logging for success and error cases.

This can be extended or used with AWS S3, or with custom object storage systems that implement the S3 API (e.g., MinIO).

---

### Import

```python
from utils.object_store import ObjectStoreAPI
```

---

### Usage

#### Configuration

```python
config = {
    "aws_access_key_id": "your-access-key",
    "aws_secret_access_key": "your-secret-key",
    "region_name": "your-region"
}
```

#### Initialize the client

```python
store = ObjectStoreAPI(config)
```

#### Upload file from file path

```python
store.upload_file(bucket_name="my-bucket", object_key="my-folder/my-file.txt", data="/path/to/local/file.txt")
```

#### Upload file from bytes

```python
binary_data = b"Hello, world!"
store.upload_file(bucket_name="my-bucket", object_key="data/hello.txt", data=binary_data)
```

#### Upload file from a `BytesIO` buffer

```python
import io

buffer = io.BytesIO()
buffer.write(b"Buffered content")
buffer.seek(0)
store.upload_file(bucket_name="my-bucket", object_key="buffer/file.txt", data=buffer)
```

---

#### Download file to local path

```python
store.download_file(bucket_name="my-bucket", object_key="my-folder/my-file.txt", destination="/path/to/save/file.txt")
```

#### Download file to a `BytesIO` buffer

```python
import io

output_buffer = io.BytesIO()
store.download_file(bucket_name="my-bucket", object_key="data/hello.txt", destination=output_buffer)
print(output_buffer.getvalue())
```

#### Download file and get content as `bytes`

```python
data = store.download_file(bucket_name="my-bucket", object_key="data/hello.txt")
print(data.decode())
```

---

### Custom Object Storage

To use a custom object storage system like MinIO or Ceph:

1. Ensure it supports the **S3 API**.
2. Replace the configuration:

```python
config = {
    "aws_access_key_id": "your-key",
    "aws_secret_access_key": "your-secret",
    "region_name": "us-east-1"
}

# If using a custom endpoint:
import boto3

store = ObjectStoreAPI(config)
store.s3_client = boto3.client(
    's3',
    endpoint_url="https://your-custom-object-store.local",
    aws_access_key_id=config["aws_access_key_id"],
    aws_secret_access_key=config["aws_secret_access_key"],
    region_name=config["region_name"]
)
```

This allows you to seamlessly use the same `ObjectStoreAPI` with private or self-hosted storage systems.

---

## Agent Application Metrics

This document describes the `AgentSpaceMetrics` class, which provides a unified interface to collect, expose, and push runtime metrics in agent-based applications. It supports Prometheus-compatible counters, gauges, and histograms, and streams these metrics both via HTTP and Redis.

---

### Introduction

`AgentSpaceMetrics` enables:

* **Prometheus-compatible metrics** registration and management.
* **Push-based metric streaming** to Redis for centralized collection.
* **Custom labeling** with `subjectId`, `instanceId`, and `nodeId`.
* **Built-in exporter** via HTTP for Prometheus scraping.

It is designed for AI agents or modular services operating in distributed systems where real-time and historical visibility into system behavior is required.

---

### Importing

```python
from agent_sdk.metrics import AgentSpaceMetrics
```

---

### Metric Types

| Metric Type   | Description                                                                                              | Use Case                                            |
| ------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| **Counter**   | A cumulative metric that increases over time. It cannot be decreased.                                    | Request counts, error events, retries.              |
| **Gauge**     | A metric that represents a value that can go up and down.                                                | Active connections, memory usage, queue length.     |
| **Histogram** | A metric that samples observations into configurable buckets, and provides count, sum, and distribution. | Response latency, payload size, execution duration. |

---

### Usage Examples

#### 1. Initialize

```python
metrics = AgentSpaceMetrics(subject_id="subject-xyz")
```

If `subject_id` is not provided, it will use:

* `SUBJECT_ID` from environment variables (default: `default_subject`)
* `INSTANCE_ID` from environment variables (default: `executor`)
* Redis host from `METRICS_REDIS_HOST` (default: `localhost`)

---

#### 2. Register Metrics

```python
metrics.register_counter("block_executions", "Number of executions", labelnames=["blockId"])
metrics.register_gauge("active_sessions", "Active user sessions")
metrics.register_histogram("execution_latency", "Execution latency in seconds", buckets=[0.1, 0.5, 1, 2, 5])
```

---

#### 3. Update Metrics

```python
metrics.increment_counter("block_executions", {"blockId": "abc123"})
metrics.set_gauge("active_sessions", 7)
metrics.observe_histogram("execution_latency", 0.9)
```

Each metric automatically includes the following labels:

| Label        | Source             | Description                             |
| ------------ | ------------------ | --------------------------------------- |
| `subjectId`  | arg / `SUBJECT_ID` | Identifier for the agent subject        |
| `instanceId` | `INSTANCE_ID` env  | Unique name of the running agent        |
| `nodeId`     | `detect_node_id()` | Identifier of the physical/logical node |

---

### Server

#### Start Prometheus Exporter + Redis Writer

```python
metrics.start_http_server(port=8889)
```

This performs:

* Starting a Prometheus-compatible HTTP endpoint at `http://<host>:8889/metrics`
* Launching a background Redis writer thread that pushes current metrics every 5 seconds to:

```text
Redis List: NODE_METRICS
```

Each Redis entry is a JSON string with this structure:

```json
{
  "block_executions": {
    "sdk.instances.adhoc.block_executions_total": 5.0
  },
  "active_sessions": {
    "sdk.instances.adhoc.active_sessions": 3.0
  },
  "execution_latency": {
    "sdk.instances.adhoc.execution_latency_bucket": 2.0,
    ...
  },
  "subjectId": "subject-xyz",
  "instanceId": "executor",
  "nodeId": "agent-node-123"
}
```

---

### Summary

| Feature                | Description                                        |
| ---------------------- | -------------------------------------------------- |
| **Prometheus Metrics** | Exposed via HTTP endpoint                          |
| **Redis Integration**  | Streams labeled metrics to `NODE_METRICS` queue    |
| **Auto Labeling**      | Adds subjectId, instanceId, nodeId to every sample |
| **Threaded Execution** | Non-blocking exporter and writer threads           |

This utility provides a production-grade monitoring layer for agent systems and works seamlessly with Prometheus, Grafana, and Redis-based observability stacks.

---

Here's a more **comprehensive version** of the documentation for your graph database framework, including:

* A summary of methods under each client class
* A detailed example of porting a custom backend (Neo4j)
* Maintains structure and extensibility

---

## Graph Database Integration – `agent_sdk.graphs`

This module provides a modular and extensible interface for working with graph databases. It supports:

* **Remote Graph DBs** like JanusGraph and ArangoDB
* **Local in-memory graph engine** for testing or transient execution
* A common **abstract base class** to enable custom database backends

---

### Using Remote DBs

Remote DB clients are imported from:

```python
from agent_sdk.graphs.db import JanusGraphDBClient, ArangoDBClient
```

---

### `JanusGraphDBClient`

**Connects via:** Gremlin WebSocket
**Target DB:** JanusGraph, Apache TinkerPop-compatible stores

#### Initialization

```python
client = JanusGraphDBClient(host="localhost", port=8182)
```

#### Methods

| Method                                     | Description                                  |
| ------------------------------------------ | -------------------------------------------- |
| `add_vertex(label, properties)`            | Add a vertex with given label and properties |
| `add_edge(out_v, in_v, label, properties)` | Add an edge between two vertices             |
| `get_vertex_by_id(vertex_id)`              | Get vertex by ID                             |
| `get_edge_by_id(edge_id)`                  | Get edge by ID                               |
| `delete_vertex(vertex_id)`                 | Remove vertex from the graph                 |
| `delete_edge(edge_id)`                     | Remove edge from the graph                   |
| `execute_query(query, bindings=None)`      | Execute custom Gremlin query                 |
| `close()`                                  | Close connection                             |

---

### `ArangoDBClient`

**Connects via:** HTTP
**Target DB:** ArangoDB (Multi-model DB with AQL)

#### Initialization

```python
client = ArangoDBClient(
    host="localhost", port=8529,
    username="root", password="openSesame",
    db_name="graph_db"
)
```

#### Methods

| Method                                               | Description                |
| ---------------------------------------------------- | -------------------------- |
| `add_document(collection, document)`                 | Add document to collection |
| `get_document(collection, doc_id)`                   | Get document by ID         |
| `update_document(collection, doc_id, update_fields)` | Update document fields     |
| `delete_document(collection, doc_id)`                | Delete document            |
| `execute_query(query, bind_vars=None)`               | Execute AQL query          |
| `close()`                                            | Close connection           |

---

### Using Local In-Memory Graph

Imported from:

```python
from agent_sdk.graphs.local import InMemoryGraphDB
```

This client offers lightweight, dependency-free graph functionality, perfect for testing, simulations, or agents without external storage access.

#### Initialization

```python
graph = InMemoryGraphDB(directed=True)
```

#### Methods

| Method                                | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `add_vertex(vertex)`                  | Add vertex to the graph                        |
| `add_edge(src, dest, **properties)`   | Add edge (with optional properties)            |
| `remove_vertex(vertex)`               | Delete a vertex and all connected edges        |
| `remove_edge(src, dest)`              | Delete edge between two nodes                  |
| `find_edges_by_property(**filters)`   | Query edges by property match                  |
| `find_edges_between(src, dest)`       | Find edges between two nodes                   |
| `dfs(start_vertex)`                   | Depth-first traversal                          |
| `bfs(start_vertex)`                   | Breadth-first traversal                        |
| `find_path(start_vertex, end_vertex)` | Returns one path (if exists) between two nodes |
| `__str__()`                           | String representation of graph                 |

---

### Porting and Using Custom Graph DBs

All custom graph databases must inherit from:

```python
from agent_sdk.graphs.abs import GraphDBInterface
```

#### Abstract Interface

```python
class GraphDBInterface(ABC):
    def add_vertex(...): pass
    def add_edge(...): pass
    def get_vertex_by_id(...): pass
    def get_edge_by_id(...): pass
    def delete_vertex(...): pass
    def delete_edge(...): pass
    def execute_query(...): pass
    def close(): pass
```

Each method must be implemented to conform to your backend.

---

### Example: Porting Neo4j

Here’s how to port Neo4j using the `neo4j` Python driver:

#### Installation

```bash
pip install neo4j
```

#### Implementation

```python
from neo4j import GraphDatabase
from agent_sdk.graphs.abs import GraphDBInterface

class Neo4jDBClient(GraphDBInterface):
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def _run(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def add_vertex(self, label, properties):
        props = ', '.join(f"{k}: ${k}" for k in properties)
        query = f"CREATE (n:{label} {{{props}}}) RETURN n"
        return self._run(query, properties)

    def add_edge(self, out_v, in_v, label, properties=None):
        props = ', '.join(f"{k}: ${k}" for k in (properties or {}))
        query = (
            f"MATCH (a), (b) WHERE id(a)=$out_id AND id(b)=$in_id "
            f"CREATE (a)-[r:{label} {{{props}}}]->(b) RETURN r"
        )
        return self._run(query, {**(properties or {}), "out_id": int(out_v), "in_id": int(in_v)})

    def get_vertex_by_id(self, vertex_id):
        return self._run("MATCH (n) WHERE id(n)=$id RETURN n", {"id": int(vertex_id)})

    def get_edge_by_id(self, edge_id):
        return self._run("MATCH ()-[r]->() WHERE id(r)=$id RETURN r", {"id": int(edge_id)})

    def delete_vertex(self, vertex_id):
        return self._run("MATCH (n) WHERE id(n)=$id DETACH DELETE n", {"id": int(vertex_id)})

    def delete_edge(self, edge_id):
        return self._run("MATCH ()-[r]->() WHERE id(r)=$id DELETE r", {"id": int(edge_id)})

    def execute_query(self, query, bindings=None):
        return self._run(query, bindings)
```

#### Usage

```python
neo_client = Neo4jDBClient(uri="bolt://localhost:7687", user="neo4j", password="password")
neo_client.add_vertex("Person", {"name": "Neo"})
neo_client.close()
```

---


## Agent Config Store – `agent_sdk.config_store`

The **Agent Config Store** provides a modular configuration management system for agent-based applications. It allows developers to **register configurable modules**, **query/update parameters**, and **execute module-specific commands** through a simple REST API.

This is ideal for agents that need dynamic configurability during runtime.

---

### Introduction

Modern AI agents and services often require fine-grained, runtime-tunable configuration — for example, thresholds, operational modes, toggles, or restart/reset hooks.

This module helps expose and manage these configurations via:

* Module registration
* Key-value based config management
* Command execution (e.g., reset, print, toggle)
* RESTful API on port **7777**

---

### Importing

```python
from agent_sdk.config_store import AgentConfigManager, start_server
```

---

### Config Store Functions

#### Class: `AgentConfigManager`

This class manages all registered modules and provides helper methods to interact with them.

##### Initialization

```python
manager = AgentConfigManager()
```

##### Methods

| Method                                                       | Description                                          |
| ------------------------------------------------------------ | ---------------------------------------------------- |
| `register(module_name, module_object)`                       | Register a module with the config manager            |
| `unregister(module_name)`                                    | Unregister a module                                  |
| `get(module_name, key)`                                      | Retrieve a key’s value from the module               |
| `set(module_name, key, value)`                               | Set a key’s value inside the module                  |
| `list()`                                                     | List all modules and their available config/commands |
| `list_commands(module_name)`                                 | List commands supported by the module                |
| `execute_config_command(module_name, command, command_data)` | Execute a config command with input                  |

---

### Registering Modules

To register a module, it must implement the following methods:

```python
- get(key: str) -> Any
- set(key: str, value: Any) -> None
- list() -> List[str]
- list_commands() -> List[str]
- execute_config_command(command: str, command_data: dict) -> Any
```

#### Example

```python
class ExampleModule:
    def __init__(self):
        self.params = {"mode": "auto", "threshold": 0.75}

    def get(self, key):
        return self.params[key]

    def set(self, key, value):
        self.params[key] = value

    def list(self):
        return list(self.params.keys())

    def list_commands(self):
        return ["reset", "print_config"]

    def execute_config_command(self, command, command_data):
        if command == "reset":
            self.params = {"mode": "auto", "threshold": 0.75}
            return {"status": "reset"}
        elif command == "print_config":
            return {"config": self.params}
        raise ValueError("Invalid command")
```

```python
manager = AgentConfigManager()
manager.register("example", ExampleModule())
```

---

### Starting the Config Server

```python
from agent_sdk.config_store import start_server

start_server(port=7777)
```

This launches a Flask app on a background thread, making the REST APIs available at `http://localhost:7777`.

---

### API Endpoints and Usage

Each API returns a JSON response with `success: true/false` and optionally `data` or `message`.

#### `POST /execute`

Executes a configuration command on the specified module.

**Request body:**

```json
{
  "module_name": "example",
  "command": "reset",
  "command_data": {}
}
```

**Curl example:**

```bash
curl -X POST http://localhost:7777/execute \
  -H "Content-Type: application/json" \
  -d '{"module_name": "example", "command": "reset", "command_data": {}}'
```

---

#### `GET /get/<module_name>/<key>`

Retrieves a config key’s value.

**Curl example:**

```bash
curl http://localhost:7777/get/example/mode
```

---

#### `POST /set/<module_name>/<key>/<value>`

Sets a config key to a new value.

**Curl example:**

```bash
curl -X POST http://localhost:7777/set/example/mode/manual
```

---

#### `GET /list`

Lists all registered modules along with their parameters and commands.

**Curl example:**

```bash
curl http://localhost:7777/list
```

---

#### `GET /list_commands/<module_name>`

Lists all supported commands for a given module.

**Curl example:**

```bash
curl http://localhost:7777/list_commands/example
```

---

### Usage Example

```python
from agent_sdk.config_store import AgentConfigManager, start_server

class ThresholdModule:
    def __init__(self):
        self.config = {"threshold": 0.5, "enabled": True}

    def get(self, key):
        return self.config[key]

    def set(self, key, value):
        self.config[key] = value

    def list(self):
        return list(self.config.keys())

    def list_commands(self):
        return ["toggle", "status"]

    def execute_config_command(self, command, command_data):
        if command == "toggle":
            self.config["enabled"] = not self.config["enabled"]
            return {"enabled": self.config["enabled"]}
        elif command == "status":
            return self.config
        else:
            raise ValueError("Invalid command")

manager = AgentConfigManager()
manager.register("threshold", ThresholdModule())
start_server(port=7777)
```

Once the server starts, you can now interact with this module using REST APIs.

---

## Known Subjects Registry

### Introduction

The **Known Subjects Registry** is a dynamic agent registry that manages and tracks runtime subjects (agents, processors, components, etc.) in an intelligent system. Each subject is a versioned, semantically described runtime unit that can be discovered and invoked.

This registry supports:

* Fetching and maintaining runtime metadata from a centralized REST API
* Registering agents by name and subject ID
* Querying and listing all available runtime subjects
* Providing **LLM-compatible searchable representations** for intelligent planners

Each subject includes details like its version, tags, role, supported DSLs, and runtime traits, making it highly suitable for use in autonomous workflows and agent orchestration.

---

### Usage

#### Initialize the Registry

```python
from agent_sdk.known_subjects import KnownSubjects

known_subjects = KnownSubjects(base_url="http://runtime-db-service")
```

#### Add an Agent

```python
# subject_id = "block.image_processor:1.0-stable"
known_subjects.add_agent("image_agent", subject_id)
```

#### Remove an Agent

```python
known_subjects.remove_agent("image_agent")
```

#### List Registered Agents

```python
agents = known_subjects.list_agents()
for name, subject in agents.items():
    print(f"{name}: {subject.subject_description}")
```

#### Query All Runtime Subjects (from backend)

```python
all_subjects = known_subjects.list_runtime_subjects()
```

#### Run a Custom Query

```python
query = {"subject_type": "block", "subject_search_tags": ["text", "nlp"]}
results = known_subjects.query_runtime_subjects(query)
```

---

### Searchable Representation

The method `get_searchable_representation()` returns a list of structured records that describe each known agent. This is particularly useful for use in LLM-based planners and agent selectors.

```python
searchable = known_subjects.get_searchable_representation()
```

Each entry includes:

| Field         | Description                                                      |
| ------------- | ---------------------------------------------------------------- |
| `id`          | Unique subject identifier (`type.name:version-tag`)              |
| `name`        | Subject name                                                     |
| `type`        | Subject type (e.g., `block`, `processor`, etc.)                  |
| `description` | Human-readable description of what the subject does              |
| `tags`        | Semantic search tags                                             |
| `traits`      | Execution/environmental traits (e.g., `gpu`, `batching`)         |
| `role`        | Subject's system role (`generator`, `router`, `evaluator`, etc.) |
| `schema`      | DSL input schema (if defined)                                    |
| `agent_name`  | Name used in the registry (user-defined alias)                   |

This output can be directly used by an LLM planner to select appropriate agents for downstream tasks.

---

### Example

```python
# Initialize the registry
known_subjects = KnownSubjects("http://runtime-db-service")

# Register an agent by its unique subject_id
known_subjects.add_agent("text_summarizer", "block.summarizer:1.0-stable")

# View registered agents
print("Registered Agents:")
for name, agent in known_subjects.list_agents().items():
    print(f"{name} -> {agent.subject_description}")

# Get structured view for LLM integration
llm_input = known_subjects.get_searchable_representation()

for entry in llm_input:
    print(f"Agent {entry['agent_name']} - Role: {entry['role']} - Tags: {entry['tags']}")
```

---

## Agent Chat Server

### Introduction

The **Agents Chat Server** is a WebSocket-based real-time messaging server that enables multi-user, session-specific chat functionality. It supports persistent storage via a pluggable cache backend (`context_cache`) and real-time message broadcasting to all connected clients in a session. The server integrates with a `ChatManager` that handles message storage, retrieval, filtering, and broadcast logic.

---

### Importing

To import the required modules:

```python
from agents_sdk.chat import start_chat_server
from agents_sdk.chat.utils.chat import ChatManager
```

---

### Usage Guide

#### 1. Initialize the Chat Manager

```python
chat_manager = ChatManager()
```

Optionally, pass a cache backend that supports `.GET(key, namespace)` and `.SET(key, value, namespace)`.

#### 2. Start the Chat Server

```python
start_chat_server(chat_manager, host="0.0.0.0", port=8765)
```

This launches the WebSocket server in a daemon thread at `ws://0.0.0.0:8765`.

#### 3. WebSocket Client Communication

Clients must connect to the server and send messages using JSON format:

```json
{
  "session_id": "abc123",
  "role": "user",
  "content": "Hello, agent!"
}
```

The server will respond with the same data format after storing the message.

#### 4. Server-Initiated Message Broadcast

You can send a message from the server to all clients in a session:

```python
chat_manager.send_message("abc123", "System broadcast message.")
```

To enable this, you must set the `WebSocketServer` as the sender after startup:

```python
# Optional: register sender if you want server-initiated messages
server = WebSocketServer(chat_manager)
chat_manager.set_sender(server)
```

---

### Full Example

```python
from agents_sdk.chat import start_chat_server, WebSocketServer
from agents_sdk.chat.utils.chat import ChatManager
import time

# Step 1: Create ChatManager
chat_manager = ChatManager()

# Step 2: Start chat server in background thread
start_chat_server(chat_manager)

# Optional: Allow time for the server to boot
time.sleep(2)

# Step 3: Send a message to connected clients
chat_manager.send_message("abc123", "Welcome to the session!")
```

---

### WebSocketServer API

| Method                              | Description                                                   |
| ----------------------------------- | ------------------------------------------------------------- |
| `start()`                           | Starts the WebSocket server on the specified host and port.   |
| `send_message(session_id, message)` | Broadcasts a message to all clients connected to the session. |
| `handler(websocket, path)`          | Internal coroutine for handling client messages.              |

---

### ChatManager API

| Method                                              | Description                                         |
| --------------------------------------------------- | --------------------------------------------------- |
| `add_message(session_id, role, content, timestamp)` | Appends a message to session history.               |
| `list_messages(session_id)`                         | Lists all messages in a session.                    |
| `get_message(session_id, index)`                    | Returns message at specified index.                 |
| `delete_message(session_id, index)`                 | Deletes message at index.                           |
| `get_user_messages(session_id)`                     | Filters messages with role `"user"`.                |
| `get_system_messages(session_id)`                   | Filters messages with role `"system"`.              |
| `get_messages_by_timestamp(session_id, start, end)` | Filters messages within the timestamp range.        |
| `set_sender(sender)`                                | Registers a sender for system messages.             |
| `send_message(session_id, content)`                 | Sends system message to all clients in the session. |

---

### Notes

* Clients must handle WebSocket reconnects and JSON parsing.
* Extend `ChatManager` to integrate audit logs or external databases.
* To use Redis as `context_cache`, implement an object with `GET` and `SET` methods per session.

---

## Agent P2P Module

### Introduction

The Agent P2P module enables decentralized communication between AI agents using WebSocket and HTTP-based messaging. It provides abstractions for sending messages, dispatching API calls, exchanging files, and remote task execution through a common interface.

This module is designed to support real-time agent-to-agent coordination in a distributed AI system, where each agent can expose WebSocket and REST endpoints for peer communication.

---

### Importing

To use the module, import everything from:

```python
from agent_sdk.p2p import *
```

This gives you access to all core classes, methods, and helper functions required to initiate peer-to-peer messaging.

---

### Usage Guide

#### 1. **Start P2P Servers**

Each agent should start its WebSocket and API servers to receive tasks and messages:

```python
start_p2p_servers(
    api_port=6666,
    ws_host="0.0.0.0",
    ws_port=8766,
    max_threads=4,
    handler_function=my_task_handler  # Optional callback
)
```

#### 2. **Send and Receive Messages**

```python
p2p = P2PManager()
response = p2p.send_recv("agent_123", {"type": "ping"})
print(response)
```

#### 3. **Send API Requests**

```python
data = {"task": "classify", "payload": {...}}
response = p2p.send_api("agent_123", data)
```

#### 4. **Send Files**

```python
file = P2PFile("image.jpg", open("image.jpg", "rb").read())
response = p2p.send_api("agent_123", {"meta": "image"}, files={"file": file.file})
```

#### 5. **Estimation API Usage**

```python
estimator = AgentEstimator(base_url="http://agent_123.local:6666")
result = estimator.estimate(query={"task": "search", "keywords": ["AI", "agents"]})
```

---

### Estimator API

The `AgentEstimator` provides a wrapper around a standard REST endpoint (`/estimate`) exposed by agents.

#### Example:

```python
estimator = AgentEstimator(base_url="http://localhost:6666")
result = estimator.estimate(query={"input": "some data"})
```

#### Response:

Returns:

* `data` if `success: true`
* Raises exception otherwise

---

### Classes and Methods

#### `AgentEstimator`

| Method               | Description                                                                        |
| -------------------- | ---------------------------------------------------------------------------------- |
| `__init__(base_url)` | Initializes with the base API URL of the remote agent.                             |
| `estimate(query)`    | Sends a POST request to `/estimate` endpoint. Returns result if `success` is true. |

---

#### `P2PFile`

| Attribute  | Description                             |
| ---------- | --------------------------------------- |
| `filename` | Name of the file                        |
| `file`     | A `BytesIO` buffer holding file content |

| Method                       | Description                                                        |
| ---------------------------- | ------------------------------------------------------------------ |
| `__init__(filename, source)` | Accepts `bytes`, `BytesIO`, or file path and loads it into memory. |

---

#### `P2PManager`

Provides methods for agent-to-agent messaging.

| Method                                   | Description                                                |
| ---------------------------------------- | ---------------------------------------------------------- |
| `send_recv(subject_id, message)`         | Sends a message and waits for response (WebSocket).        |
| `send(subject_id, message)`              | Sends a fire-and-forget message (WebSocket).               |
| `send_api(subject_id, data, files=None)` | Sends an API request (HTTP).                               |
| `estimate(subject_id, query)`            | Sends a query to the estimation endpoint of another agent. |

---

#### `start_p2p_servers(...)`

| Parameter          | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `api_port`         | Port on which REST API server listens                    |
| `ws_host`          | WebSocket server host (usually "0.0.0.0" or "localhost") |
| `ws_port`          | WebSocket server port                                    |
| `max_threads`      | Max number of threads to handle tasks                    |
| `handler_function` | Optional task handler callback                           |

---

#### `register_p2p_handler_callback(name, callback_func)`

Registers a handler function under a name for dynamic invocation.
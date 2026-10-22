# Graph Database Integration — Client Developer Documentation

## Introduction

The **Graph Database** add-on gives agents access to **ArangoDB**, a multi-model (document + graph) database, through the `ArangoSDK` class in the `agent_addons` package.

`ArangoSDK` wraps `python-arango` and adds:

* **AQL queries** with bind variables.
* **Database and collection lifecycle** management, including edge collections for graphs.
* **Document CRUD** and batched insert/upsert.
* **Bulk ingestion** from Python iterables, local JSON/JSONL files, or S3 objects.
* **Admin helpers** for server status, role, cluster health and arbitrary admin endpoints.

Typical workflow:

1. **Declare an AddonItem** in the Subject Specification to record the graph database connection (optional).
2. **Create an `ArangoSDK` client** in your agent.
3. **Create collections**, **write documents and edges**, and **query with AQL**.
4. Optionally **bulk-ingest** data from files or S3.

---

## Installation

`ArangoSDK` is part of `agent_addons` (`libs/agents-addons`), which installs `python-arango`, `requests` and `boto3`.

```bash
pip install ./libs/agents-addons
```

---

## Registering Graph DB in Subject Specification

Graph databases can be recorded in the subject's `integrations.addons` list using `AddonItem`.

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class AddonItem:
    addon_id: str
    addon_type: str
    addon_config: Dict[str, Any] = field(default_factory=dict)
```

### Example Configuration

```json
{
  "addon_id": "graphs-primary",
  "addon_type": "graph_db",
  "addon_config": {
    "endpoint": "http://arangodb.default.svc.cluster.local:8529",
    "db_name": "knowledge",
    "username": "root",
    "password": "secret"
  }
}
```

### Field Descriptions

| Field              | Type             | Description                                                          |
| ------------------ | ---------------- | -------------------------------------------------------------------- |
| **addon\_id**      | `str`            | Unique identifier for this add-on.                                   |
| **addon\_type**    | `str`            | Add-on kind, e.g. `"graph_db"`.                                      |
| **addon\_config**  | `Dict[str, Any]` | Connection settings. Use the `ArangoSDK` constructor arguments as keys (see below). |

> The agents SDK does not create clients from add-on entries automatically. Read the entry from `self.subject.integrations.addons` in your agent and build the client yourself:

```python
from agent_addons.graph import ArangoSDK

class MyAgent:
    def __init__(self, subject, context):
        self.subject = subject
        self.context = context
        addon = next(a for a in subject.integrations.addons if a.addon_type == "graph_db")
        self.graph = ArangoSDK(**addon.addon_config)
```

---

## Import and Setup

```python
from agent_addons.graph import ArangoSDK

graph = ArangoSDK(
    endpoint="http://localhost:8529",
    db_name="knowledge",
    username="root",
    password="secret",
)
```

| Argument          | Default     | Description                                                         |
| ----------------- | ----------- | ------------------------------------------------------------------- |
| `endpoint`        | — (required)| ArangoDB URL (trailing `/` is removed)                              |
| `db_name`         | `"_system"` | Database to open                                                    |
| `username`        | `None`      | Username (used together with `password`)                            |
| `password`        | `None`      | Password                                                            |
| `jwt_token`       | `None`      | JWT for authentication (sent as `Authorization: Bearer ...`)        |
| `verify_ssl`      | `True`      | Verify TLS certificates for admin/HTTP calls                        |
| `default_timeout` | `60`        | Request timeout in seconds                                          |
| `extra_headers`   | `None`      | Extra HTTP headers for admin/HTTP calls                             |

The underlying `python-arango` handles are available as `graph.client` and `graph.db`.

---

## Usage Guide

### A. Databases

Database operations always run against `_system`, using the same credentials as the client.

```python
graph.list_databases()                 # ['_system', 'knowledge', ...]
graph.create_database("knowledge")     # True
graph.delete_database("old_db")        # True

graph.switch_db("knowledge")           # reuses the stored credentials
```

### B. Collections (documents and edges)

Vertices are stored in document collections; edges are stored in **edge collections** (`edge=True`).

```python
graph.create_collection("people")
graph.create_collection("knows", edge=True)

# Create only if missing
graph.ensure_collection("companies")
graph.ensure_collection("works_at", edge=True)

graph.has_collection("people")         # True
col = graph.get_collection("people")   # python-arango Collection
graph.delete_collection("old")         # ignore_missing=True by default
```

`create_collection` also accepts cluster and schema options: `replication_factor`, `write_concern`, `number_of_shards`, `shard_keys`, `key_options`, `schema`, plus any extra `python-arango` keyword arguments.

### C. Documents and edges (CRUD)

```python
graph.insert_one("people", {"_key": "alice", "name": "Alice"})
graph.insert_one("people", {"_key": "bob", "name": "Bob"})

# Edge: _from / _to reference vertex IDs ("<collection>/<key>")
graph.insert_one("knows", {"_from": "people/alice", "_to": "people/bob", "since": 2020})

graph.get_one("people", "alice")       # {'_key': 'alice', 'name': 'Alice'}  (_id/_rev stripped), or None
graph.update_one("people", {"_key": "alice", "age": 31})          # merge update
graph.replace_one("people", {"_key": "alice", "name": "Alice B."})
graph.delete_one("people", "bob")      # True / False
```

Batched writes:

```python
graph.insert_many("people", docs, overwrite=False, batch_size=1000)
# -> {"inserted": <n>, "errors": <n>}

graph.upsert_many("people", docs, on="_key", update_expr="MERGE(OLD, NEW)", batch_size=1000)
# -> number of documents processed; every doc must contain the `on` field
```

### D. Querying with AQL

```python
friends = graph.aql(
    """
    FOR v, e IN 1..2 OUTBOUND @start knows
      RETURN { name: v.name, since: e.since }
    """,
    bind_vars={"start": "people/alice"},
)
```

`aql()` returns the full result as a list.

### E. Bulk ingestion

**From Python iterables (bulk import API):**

```python
graph.http_bulk_import(
    collection="people",
    docs=docs,
    on_duplicate="update",     # "error" | "update" | "replace" | "ignore"
    batch_size=5000,
)
# -> {"created": n, "updated": n, "ignored": n, "errors": n}

graph.http_bulk_import(collection="people", jsonl_path="/data/people.jsonl")
```

**From a local file** (JSON array or JSONL):

```python
graph.ingest_from_file("people", "/data/people.jsonl")                            # insert_many
graph.ingest_from_file("people", "/data/people.json", upsert_on="_key")           # upsert
graph.ingest_from_file("people", "/data/people.jsonl", use_http_bulk=True,
                       on_duplicate="replace")                                    # bulk import
graph.ingest_from_file("people", "/data/raw.jsonl",
                       transform=lambda d: {"_key": d["id"], "name": d["full_name"]})
```

**From S3** (JSON array or JSONL object):

```python
graph.ingest_from_s3(
    "people",
    bucket="my-bucket",
    key="exports/people.jsonl",
    aws_region="us-east-1",          # else AWS_REGION / AWS_DEFAULT_REGION
    upsert_on="_key",
)
```

Credentials default to the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables. All ingest methods return a stats dict with a `method` key (`insert_many`, `upsert` or `http_bulk_import`).

### F. Admin helpers

```python
graph.server_status()     # GET  /_admin/status
graph.server_role()       # GET  /_admin/server/role
graph.cluster_health()    # GET  /_admin/cluster/health
graph.routing_reload()    # POST /_admin/routing/reload

graph.run_admin_command("/_api/version", method="GET")
```

---

## Example: Knowledge Graph in an Agent

```python
from agent_addons.graph import ArangoSDK

graph = ArangoSDK(endpoint="http://localhost:8529", db_name="knowledge",
                  username="root", password="secret")

graph.ensure_collection("entities")
graph.ensure_collection("relations", edge=True)

graph.upsert_many("entities", [
    {"_key": "acme", "type": "company", "name": "Acme Corp"},
    {"_key": "retailco", "type": "company", "name": "RetailCo"},
])
graph.insert_one("relations", {"_from": "entities/acme", "_to": "entities/retailco",
                               "type": "supplies"})

partners = graph.aql(
    "FOR v IN 1..1 ANY @start relations RETURN v.name",
    bind_vars={"start": "entities/acme"},
)
print(partners)   # ['RetailCo']
```

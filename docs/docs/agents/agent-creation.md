# Agent Creation — Subject Creation & Deployment

Creating a running agent has three steps:

1. **Create a Subject** — store the agent specification in the subjects service.
2. **Register an Agent Deployer** — install the deployer into a Kubernetes cluster (once per cluster).
3. **Deploy the Agent** — ask the deployer to run the agent's executor and instances. This creates a **Runtime Subject** that records where the agent is running.

All endpoints below are served by the subjects service. Every response has the shape `{ "success": <bool>, "data": ..., "message": "..." }`.

Set a base variable (optional):

```bash
export SUBJECT_DB_URL="http://<subjects-service-host>:<port>"
```

---

## 1) Create a Subject

The body is a full [Agent Specification](agent-specification.md). `identity.subject_version` is required. Set `info.container_image_name` to the agent's container image — the deployer runs this image for each agent instance.

### Minimal payload

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/subjects" \
  -H "Content-Type: application/json" \
  -d '{
    "identity": {
      "subject_id": "policy-researcher-1",
      "subject_name": "Policy Researcher",
      "subject_type": "researcher",
      "subject_version": { "version": "1.0.0", "release_tag": "stable" }
    },
    "info": {
      "container_image_name": "registry.example.org/agents/policy-researcher:latest"
    },
    "metadata": {
      "subject_description": "Analyzes policy proposals and drafts briefs",
      "subject_search_tags": ["policy","analysis"]
    },
    "persona": {
      "role": "Policy Analyst",
      "goal": "Summarize and critique policy drafts",
      "persona": "Pragmatic, neutral, cites sources",
      "default_system_message": "Answer with citations and balanced tone."
    },
    "prompting": {},
    "execution": { "logging_level": "INFO" },
    "integrations": {},
    "runtime": { "resources": { "device": "cpu", "cpu_cores": 1.0, "memory_mb": 2048 } },
    "owner": { "org_name": "ExampleOrg", "owners": ["owner@example.org"] }
  }'
```

`identity.subject_id` is optional. If you omit it, the service generates one (a MongoDB ObjectId string). Creating a subject with an existing `subject_id` fails with HTTP 400.

**Example response** (HTTP 201) — the stored subject, with all defaults filled in:

```json
{
  "success": true,
  "data": {
    "identity": {
      "subject_id": "policy-researcher-1",
      "subject_name": "Policy Researcher",
      "subject_type": "researcher",
      "subject_version": { "version": "1.0.0", "release_tag": "stable" }
    },
    "info": { "container_image_name": "registry.example.org/agents/policy-researcher:latest", "...": "..." },
    "metadata": { "...": "..." },
    "persona": { "...": "..." },
    "prompting": { "...": "..." },
    "execution": { "...": "..." },
    "integrations": { "...": "..." },
    "runtime": { "...": "..." },
    "owner": { "...": "..." }
  }
}
```

### Other Subject endpoints

| Method & Path | Description |
|---|---|
| `GET /api/subjects/<subject_id>` | Get a subject (404 if not found) |
| `PUT /api/subjects/<subject_id>` | Replace a subject with a full specification |
| `PATCH /api/subjects/<subject_id>` | Update fields: body `{ "update": { "identity.subject_name": "New Name" } }` |
| `DELETE /api/subjects/<subject_id>` | Delete a subject |
| `GET /api/subjects?subject_type=<type>&tags=<a,b>&limit=50&skip=0` | List subjects, optionally filtered by type and search tags (any match) |
| `POST /api/subjects/query` | Query with a MongoDB filter: body `{ "query": {...}, "projection": {...}, "sort": [...], "limit": 50, "skip": 0 }` |
| `GET /api/subjects/health` | Health check |

```bash
curl -sS "$SUBJECT_DB_URL/api/subjects/policy-researcher-1"
```

---

## 2) Register an Agent Deployer

An agent deployer is a service running inside a Kubernetes cluster that creates agent workloads. Register one per cluster:

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/agent-deployers" \
  -H "Content-Type: application/json" \
  -d '{
    "kubeconfig":          { "...": "kubeconfig of the target cluster, as JSON" },
    "deployer_id":         "deployer-111",
    "deployer_name":       "deployer-111",
    "deployer_cluster_id": "gcp-cluster-2",
    "deployer_public_ip":  "35.223.239.192"
  }'
```

| Field | Required | Description |
|---|---|---|
| `kubeconfig` | Yes | Kubeconfig (as a JSON object) used to install the deployer into the cluster |
| `deployer_id` | Yes | Unique ID of the deployer |
| `deployer_name` | Yes | Human-readable name |
| `deployer_cluster_id` | Yes | ID of the cluster |
| `deployer_public_ip` | Yes | Not checked by the API, but needed. Public IP of a cluster node. The deployer is exposed on NodePort `30777`, so its URL becomes `http://<deployer_public_ip>:30777`. Agent and workflow URLs are built from this IP |

The deployer is installed in the `agent-deployer` namespace. If saving the record fails, the installed Kubernetes resources are rolled back.

| Method & Path | Description |
|---|---|
| `GET /api/agent-deployers?cluster_id=<id>&limit=50&skip=0` | List deployers |
| `POST /api/agent-deployers/query` | Query deployers (same body as subject queries) |
| `PUT` / `PATCH /api/agent-deployers/<deployer_id>` | Replace / update a deployer record |
| `DELETE /api/agent-deployers/<deployer_id>` | Uninstall the deployer (body: `{ "kubeconfig": {...} }`) and delete its record |

---

## 3) Deploy the Agent

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/deploy-agent/deployer-111" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "policy-researcher-1",
    "allocation": {
      "delegate_api_url": "http://35.223.239.192:30725",
      "instances": [
        { "instance_id": "i1", "subject_id": "policy-researcher-1" },
        { "instance_id": "i2", "subject_id": "policy-researcher-1", "node_selector": { "pool": "cpu" } }
      ],
      "meshes": [
        { "mesh_id": "mesh-a", "url": "nats://10.104.140.46:4222" }
      ]
    }
  }'
```

| Field | Required | Description |
|---|---|---|
| `subject_id` | Yes | Subject to deploy |
| `allocation.instances` | Yes | Agent instances to create. Each needs `instance_id` and `subject_id`; `node_selector` is optional |
| `allocation.meshes` | No | P2P meshes (NATS) to join, as `{ "mesh_id", "url" }` |
| `allocation.delegate_api_url` | Yes* | Delegate API URL given to the agent instances (`AGENT_DELEGATE_URL`), used by `context.delegator`. *Not checked by the API, but agent instances built on the agents SDK fail to start without it |

The deployer creates the following in the `agents` namespace:

- **Agent executor** — one Deployment with the executor, a scouter and Redis, exposed through two `NodePort` services: executor port `9000` and scouter port `10000`. The executor receives tasks (`/submitTask`), applies the subject's policies and load-balances tasks across instances.
- **Agent instances** — one Deployment per instance, running the image from `info.container_image_name` with a Redis sidecar. Each instance gets `SUBJECT_ID`, `INSTANCE_ID`, `SUBJECT_DB_URL`, `MESH_LIST`, `AGENT_DELEGATE_URL` and `JOB_EXCHANGE_API_URL`. It exposes ports `8765` (WebSocket) and `9090` (metrics).

On success a **Runtime Subject** is stored with `runtime_subject_id = subject_id`:

```json
{
  "success": true,
  "data": {
    "runtime_subject_id": "policy-researcher-1",
    "subject_id": "policy-researcher-1",
    "runtime_status": "active",
    "runtime_info": {
      "executor": "http://35.223.239.192:31412",
      "scouter":  "http://35.223.239.192:31413",
      "deployment_data": {
        "executor": { "port": 9000,  "node_port": 31412, "...": "..." },
        "scouter":  { "port": 10000, "node_port": 31413, "...": "..." }
      }
    }
  }
}
```

`runtime_info.executor` is the URL the Delegate API uses to send tasks to this agent. Deploying a subject that already has a runtime subject fails with HTTP 400 (the record already exists).

### Remove an Agent

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/remove-agent/deployer-111/policy-researcher-1"
```

This removes the agent's executor and related Kubernetes resources and deletes the runtime subject.

---

## Querying Running Agents (Runtime Subjects API)

Deployed agents are recorded as **runtime subjects**. Use these endpoints to find where an agent is running.

### GET `/api/runtime-subjects/<runtime_subject_id>`

```bash
curl -sS "$SUBJECT_DB_URL/api/runtime-subjects/policy-researcher-1"
```

The response has the same shape as the deploy response above.

### GET `/api/runtime-subjects`

List runtime subjects. All query parameters are optional:

| Parameter | Description |
|---|---|
| `subject_id` | Filter by subject ID |
| `runtime_status` | Filter by status (e.g. `active`) |
| `sort` | `<field>:asc` or `<field>:desc` |
| `limit`, `skip` | Paging (defaults `50`, `0`) |

```bash
curl -sS "$SUBJECT_DB_URL/api/runtime-subjects?runtime_status=active&limit=20"
```

### POST `/api/runtime-subjects/query`

Query runtime subjects with a MongoDB-style filter. The filter goes in `query`:

**1) Runtime subjects of one subject that are active**

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/runtime-subjects/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": { "subject_id": "policy-researcher-1", "runtime_status": "active" }
  }'
```

**2) Runtime subjects whose ID matches a prefix (case-insensitive)**

```bash
curl -sS -X POST "$SUBJECT_DB_URL/api/runtime-subjects/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": { "runtime_subject_id": { "$regex": "^policy", "$options": "i" } },
    "limit": 10
  }'
```

### Other Runtime Subject endpoints

| Method & Path | Description |
|---|---|
| `POST /api/runtime-subjects` | Create a runtime subject: `{ "runtime_subject_id", "subject_id", "runtime_info", "runtime_status" }` |
| `PUT /api/runtime-subjects/<id>` | Replace a runtime subject |
| `PATCH /api/runtime-subjects/<id>` | Update fields: body `{ "update": { ... } }` |
| `DELETE /api/runtime-subjects/<id>` | Delete the record only (Kubernetes resources are not removed) |
| `GET /api/runtime-subjects/health` | Health check |

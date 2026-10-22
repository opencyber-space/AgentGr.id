# Workflow Onboarding Guide

> A step-by-step guide to defining, registering, deploying, and executing workflows.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Step 1 — Author the Workflow Spec (JSON)](#2-step-1-author-the-workflow-spec-json)
3. [Step 2 — Register the Workflow](#3-step-2-register-the-workflow)
4. [Step 3 — Deploy the Workflow Controller](#4-step-3-deploy-the-workflow-controller)
5. [Step 4 — Execute a Task](#5-step-4-execute-a-task)
6. [End-to-End Example](#6-end-to-end-example)
7. [Reference — Node Types](#7-reference-node-types)
8. [Reference — Graph Types](#8-reference-graph-types)
9. [Common Mistakes](#9-common-mistakes)

---

## 1. Overview

Onboarding a workflow involves four steps:

```
1. Author JSON Spec   →   Define nodes + graph in a .json file
2. Register Spec      →   POST the JSON to /api/workflows (workflow service)
3. Deploy Controller  →   POST to /api/deploy-workflow/<deployer_id> to spin up a workflow executor
4. Execute Task       →   POST to <executor url>/api/execute with your input payload
```

Each step is described in detail below.

---

## 2. Step 1 — Author the Workflow Spec (JSON)

A workflow spec is a JSON document with two top-level sections: `header` and `body`.

### 2.1 Header

The header identifies the workflow and generates its `workflow_uri` in the format:
```
{name}:{version}-{release}
```

```json
"header": {
  "workflow_id": {
    "name":    "my-workflow",
    "version": "1.0.0",
    "release": "stable"
  },
  "metadata": {
    "description": "What this workflow does",
    "owner":       "your-team",
    "created_at":  "2026-03-01"
  }
}
```

| Field | Rules |
|---|---|
| `name` | Lowercase kebab-case. E.g. `loan-approval`, `fraud-detection` |
| `version` | Semantic versioning. E.g. `1.0.0`, `2.1.0` |
| `release` | Maturity tag. Use `stable`, `beta`, or `rc1` |

> **Note:** Do not set `workflow_uri` manually — it is computed by the workflow service when the spec is registered.

---

### 2.2 Nodes

Each node in `body.nodes` is one step in the pipeline.

**Agent Node** — runs an AI agent:

```json
{
  "nodeID": "my-agent",
  "type": "agent",
  "id": "agents/my-agent-subject-id",
  "settings": {
    "model_name": "aios:qwen3-1-7b-vllm-block"
  }
}
```

**Policy Node** — runs deterministic rules or logic:

```json
{
  "nodeID": "validate-input",
  "type": "policy",
  "id": "rules/validate-v1",
  "policyType": "local",
  "settings": {},
  "parameters": { "strict_mode": true }
}
```

**Workflow Node** — delegates to another registered workflow:

```json
{
  "nodeID": "fraud-investigation-workflow",
  "type": "workflow",
  "id": "fraud-investigation:1.0.0-stable"
}
```

---

### 2.3 Graph

The graph defines how nodes connect. Two types are supported.

**Static Graph** — fixed execution order defined upfront (`"type": "static"` is optional):

```json
"graph": {
  "node-a": ["node-b", "node-c"],
  "node-b": ["node-d"],
  "node-c": ["node-d"]
}
```

**Dynamic Graph** — a router agent decides execution order at runtime:

```json
"graph": {
  "type": "dynamic",
  "nodeID": "router-agent"
}
```

---

### 2.4 Complete Spec Example

Below is the complete spec for a **Legal Contract Review Pipeline** — a linear static workflow with five agents:

```json
{
  "header": {
    "workflow_id": {
      "name": "legal-contract-review-pipeline-1",
      "version": "1.0.0",
      "release": "stable"
    },
    "metadata": {
      "description": "Multi-agent pipeline to review contracts, flag risks and produce a legal memo",
      "owner": "legal-ops-team",
      "created_at": "2026-03-09"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "clause-extractor-agent",
        "type": "agent",
        "id": "w1-clause-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "risk-identifier-agent",
        "type": "agent",
        "id": "w1-risk-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "compliance-checker-agent",
        "type": "agent",
        "id": "w1-comp-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "negotiation-advisor-agent",
        "type": "agent",
        "id": "w1-nego-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      },
      {
        "nodeID": "legal-memo-agent",
        "type": "agent",
        "id": "w1-memo-1",
        "settings": { "model_name": "aios:qwen3-1-7b-vllm-block" }
      }
    ],
    "graph": {
      "clause-extractor-agent":    ["risk-identifier-agent"],
      "risk-identifier-agent":     ["compliance-checker-agent"],
      "compliance-checker-agent":  ["negotiation-advisor-agent"],
      "negotiation-advisor-agent": ["legal-memo-agent"]
    }
  }
}
```

This produces the following pipeline:

```
clause-extractor-agent
        ↓
risk-identifier-agent
        ↓
compliance-checker-agent
        ↓
negotiation-advisor-agent
        ↓
legal-memo-agent
```

---

## 3. Step 2 — Register the Workflow

Once your spec JSON is ready, register it with the workflow service.

**Request:**

```bash
curl -X POST \
  -d @./spec.json \
  http://<HOST>:<PORT>/api/workflows
```

**What this does:**  
Stores the workflow spec in the workflow service's database (MongoDB). The service parses the header and stores the spec under the computed `workflow_uri` (e.g. `legal-contract-review-pipeline-1:1.0.0-stable`).

**Response:**

```json
{
  "success": true,
  "data": {
    "header": {
      "workflow_id":  { "name": "...", "version": "...", "release": "..." },
      "workflow_uri": "legal-contract-review-pipeline-1:1.0.0-stable",
      "metadata":     { "description": "...", "owner": "...", "created_at": "..." }
    },
    "body": { "nodes": [ ... ], "graph": { ... } }
  }
}
```

> **Notes:**
>
> - Registration does **not** validate the spec. Errors such as duplicate `nodeID`s or graph references to undefined nodes are only detected when the workflow executor loads the spec (Step 3).
> - Only the known fields are stored. Unknown keys on nodes or in `metadata` are dropped.
> - Registering a `workflow_uri` that already exists fails with HTTP 400 (`Workflow <uri> already exists`). To change an existing workflow, use `PUT /api/workflows/<workflow_uri>` (see [Managing Registered Workflows](#managing-registered-workflows)).
>
> **Tip:** Save your spec as `spec.json` in your working directory before running the command.

### Managing Registered Workflows

All endpoints are on the workflow service and return `{ "success": ..., "data": ... }` (or `"message"` on error).

| Method & Path | Description |
|---|---|
| `GET /api/workflows/<workflow_uri>` | Get a workflow spec (404 if not found) |
| `PUT /api/workflows/<workflow_uri>` | Replace a workflow spec (body: full spec JSON). The stored `workflow_uri` is kept |
| `PATCH /api/workflows/<workflow_uri>` | Update fields: body `{ "update": { "<dotted.field>": <value> } }` (MongoDB `$set`) |
| `DELETE /api/workflows/<workflow_uri>` | Delete a workflow spec |
| `GET /api/workflows?limit=50&skip=0` | List workflows |
| `POST /api/workflows/query` | Query workflows: body `{ "query": {...}, "projection": {...}, "sort": [...], "limit": 50, "skip": 0 }` |

---

## 4. Step 3 — Deploy the Workflow Controller

After registration, deploy a workflow executor that will run the workflow. The workflow service forwards the request to the agent deployer identified by `DEPLOYER_ID`, which creates a Kubernetes Deployment (one replica) and a `NodePort` Service named `<deployment_name>-svc` in the `workflows` namespace. The executor listens on port 9100.

**Request:**

```bash
curl -X POST \
  http://<HOST>:<PORT>/api/deploy-workflow/<DEPLOYER_ID> \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "<your-deployment-name>",
    "workflow_id":     "<unique-instance-id>",
    "workflow_uri":    "<name>:<version>-<release>",
    "allocation": {
      "policy_db_url":    "http://<POLICY_HOST>:<PORT>",
      "delegate_api_url": "http://<AGENT_HOST>:<PORT>"
    }
  }'
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `DEPLOYER_ID` | Yes | ID of a registered agent deployer (path param). 404 if not found |
| `deployment_name` | Yes | Name of the Kubernetes Deployment. It is lower-cased, characters other than `a-z`, `0-9` and `-` are replaced with `-`, and it is truncated to 63 characters. Deploying again with the same name replaces the existing Deployment |
| `workflow_id` | Yes | Unique ID of this runtime workflow record. Must not already exist |
| `workflow_uri` | Yes | Must match the `workflow_uri` of the registered spec exactly |
| `cluster_id` | No | Cluster identifier stored on the runtime record |
| `allocation.policy_db_url` | Yes | Base URL of the Policy DB, used by `local` policy nodes |
| `allocation.delegate_api_url` | Yes | Base URL of the agent Delegate API |

**Response:**

```json
{
  "success": true,
  "data": {
    "id":              "simple-workflow-001",
    "workflow_uri":    "legal-contract-review-pipeline-1:1.0.0-stable",
    "cluster_id":      null,
    "deployer_id":     "deployer-111",
    "deployment_name": "simple-workflow",
    "url":             "http://<deployer_ip>:<node_port>"
  }
}
```

`data.url` is the base URL of the deployed workflow executor — use it in Step 4. The record is stored as a **runtime workflow** and can be read later:

| Method & Path | Description |
|---|---|
| `GET /api/runtime-workflows/<workflow_id>` | Get a runtime workflow |
| `GET /api/runtime-workflows?workflow_uri=<uri>&cluster_id=<id>&limit=50&skip=0` | List runtime workflows (filters optional) |
| `DELETE /api/runtime-workflows/<workflow_id>` | Delete the runtime record only (does not remove the Kubernetes resources) |

**Example:**

```bash
curl -X POST \
  http://35.223.239.192:30721/api/deploy-workflow/deployer-111 \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "simple-workflow",
    "workflow_id":     "simple-workflow-001",
    "workflow_uri":    "legal-contract-review-pipeline-1:1.0.0-stable",
    "allocation": {
      "policy_db_url":    "http://34.58.1.86:30102",
      "delegate_api_url": "http://35.223.239.192:30725"
    }
  }'
```

> **Note:** The `workflow_uri` in the deploy request must exactly match the registered spec — including name, version, and release. The deploy request itself still succeeds on a mismatch. The error appears when the executor starts: it cannot fetch the spec (`WorkflowDBError`), fails to start, and Kubernetes keeps restarting it. An invalid spec (`WorkflowSpecError`, `WorkflowCycleError`) has the same effect. Check the executor pod logs in the `workflows` namespace if `/api/execute` is unreachable.

> **Known issue:** The deployer passes `delegate_api_url` to the executor as the `DELEGATE_API_URL` environment variable, but the executor reads `DELGATE_API_URL`. Until this is fixed, agent nodes use the executor's built-in default Delegate API URL rather than the value in `allocation`.

### Removing a Deployed Workflow

```bash
curl -X POST \
  http://<HOST>:<PORT>/api/remove-workflow/<DEPLOYER_ID>/<workflow_id>
```

This deletes the executor's Deployment and Service and the runtime workflow record. The registered spec is kept.

---

## 5. Step 4 — Execute a Task

With the executor deployed, submit a task to the executor URL returned by the deploy step (`data.url`).

**Request:**

```bash
curl -X POST \
  <EXECUTOR_URL>/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<your input payload>"
  }'
```

The body must be a JSON object; it becomes the workflow's `initial_input`.

**Response:**

```json
{
  "success": true,
  "data": {
    "<nodeID>": { "...": "output of that node" },
    "<nodeID>": { "...": "..." }
  }
}
```

`data` maps each executed `nodeID` to its output. For a dynamic workflow whose router returned a final-output dict, `data` is that dict instead.

**Errors** return `{ "success": false, "error": "<message>" }`:

| HTTP status | Cause |
|---|---|
| 400 | `WorkflowSpecError` — e.g. the body is not a JSON object |
| 500 | `WorkflowNodeError` (response also includes `node_id`), `WorkflowRouterError`, `WorkflowExecutionError`, `WorkflowDBError`, or any other error |

The request is synchronous — it returns only when the whole workflow has finished. The executor also exposes `GET /health`.

**Example** (here `http://35.223.239.192:30712` is the `data.url` returned by the deploy step):

```bash
curl -X POST \
  http://35.223.239.192:30712/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contract: SaaS Subscription Agreement between Acme Corp (vendor) and RetailCo (client). Key clauses: auto-renewal at 15% price increase, no SLA guarantees, data ownership ambiguous, termination requires 180-day notice, liability cap at $5,000 regardless of contract value ($2M/year). Jurisdiction: Delaware, USA."
  }'
```

The input is passed as `initial_input` to the entry node(s) of the pipeline. Each subsequent node receives the output of its parent node(s).

---

## 6. End-to-End Example

Here is the complete flow for the Legal Contract Review Pipeline:

### Step 1 — Save the spec

```bash
# Save the JSON spec from Section 2.4 as spec.json
vim spec.json
```

### Step 2 — Register

```bash
curl -X POST \
  -d @./spec.json \
  http://35.223.239.192:30721/api/workflows
```

### Step 3 — Deploy

```bash
curl -X POST \
  http://35.223.239.192:30721/api/deploy-workflow/deployer-111 \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "legal-contract-review",
    "workflow_id":     "legal-review-001",
    "workflow_uri":    "legal-contract-review-pipeline-1:1.0.0-stable",
    "allocation": {
      "policy_db_url":    "http://34.58.1.86:30102",
      "delegate_api_url": "http://35.223.239.192:30725"
    }
  }'
```

### Step 4 — Execute

Use the `data.url` returned by Step 3 as the executor URL:

```bash
curl -X POST \
  http://35.223.239.192:30712/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contract: SaaS Subscription Agreement between Acme Corp (vendor) and RetailCo (client)..."
  }'
```

### What happens next

```
Input text
    ↓
clause-extractor-agent     → extracts all clauses from the contract
    ↓
risk-identifier-agent      → identifies risky clauses
    ↓
compliance-checker-agent   → checks against legal standards
    ↓
negotiation-advisor-agent  → recommends negotiation points
    ↓
legal-memo-agent           → produces the final legal memo
```

---

## 7. Reference — Node Types

| Type | Use Case | Required Fields |
|---|---|---|
| `agent` | Run an AI agent | `nodeID`, `type`, `id` (`settings.model_name` strongly recommended) |
| `policy` | Run deterministic rules/logic | `nodeID`, `type`, `id`, `policyType` (+ `settings` required by the policy type) |
| `workflow` | Delegate to another workflow | `nodeID`, `type`, `id` (must be a valid `workflow_uri`) |

### Policy Types

| `policyType` | When to Use |
|---|---|
| `local` | Simple rule evaluated in-process |
| `central` | Rule engine hosted on a remote service |
| `function` | Serverless/function endpoint |
| `job` | Long-running batch job that requires polling |

---

## 8. Reference — Graph Types

| Type | When to Use |
|---|---|
| **Static** | Execution order is always the same. All branches always run. |
| **Dynamic** | Branches depend on output content. Loops or retries are needed. A router agent decides what runs next. |

> **Rule of thumb:** If you would need an `if` statement to decide the next step — use Dynamic.

---

## 9. Common Mistakes

| Mistake | What Goes Wrong | Fix |
|---|---|---|
| `workflow_uri` in deploy doesn't match registered spec | Executor fails at start-up with `WorkflowDBError` and keeps restarting | Copy the URI exactly from the header: `{name}:{version}-{release}` |
| Reusing a `workflow_id` in a deploy request | Deploy returns 400 (runtime workflow already exists), although the Kubernetes Deployment is created or replaced | Use a new `workflow_id`, or remove the existing deployment first |
| Duplicate `nodeID` values in `nodes` | `WorkflowSpecError` when the executor starts (not at registration) | Every node must have a unique `nodeID` |
| Graph references a `nodeID` not defined in `nodes` | `WorkflowSpecError` when the executor starts (not at registration) | Ensure all IDs in the graph match node definitions exactly |
| `policyType` missing on a `policy` node | `WorkflowSpecError` | Always set `policyType` for every policy node |
| `model_name` missing on an `agent` node | Warning at runtime, unpredictable behaviour | Always set `model_name` in `settings` |
| Sub-workflow `id` doesn't match a registered `workflow_uri` | `WorkflowNodeError` on the workflow node at runtime | Ensure the target workflow is registered before referencing it |
| An agent's `on_preprocess` returns `None` | `/api/execute` never returns | Return an error `AgentResult` instead of skipping |
| Typo in a `nodeID` string | Silent routing failure | Double-check all node IDs — copy-paste rather than retype |
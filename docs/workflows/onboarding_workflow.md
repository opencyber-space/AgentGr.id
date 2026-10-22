# Workflow Onboarding Guide

> A step-by-step guide to defining, registering, deploying, and executing workflows.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Step 1 — Author the Workflow Spec (JSON)](#2-step-1--author-the-workflow-spec-json)
3. [Step 2 — Register the Workflow](#3-step-2--register-the-workflow)
4. [Step 3 — Deploy the Workflow Controller](#4-step-3--deploy-the-workflow-controller)
5. [Step 4 — Execute a Task](#5-step-4--execute-a-task)
6. [End-to-End Example](#6-end-to-end-example)
7. [Reference — Node Types](#7-reference--node-types)
8. [Reference — Graph Types](#8-reference--graph-types)
9. [Common Mistakes](#9-common-mistakes)

---

## 1. Overview

Onboarding a workflow involves four steps:

```
1. Author JSON Spec   →   Define nodes + graph in a .json file
2. Register Spec      →   POST the JSON to /api/workflows
3. Deploy Controller  →   POST to /api/deploy-workflow to spin up the executor
4. Execute Task       →   POST to /api/execute with your input payload
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

> **Note:** Do not set `workflow_uri` manually — it is auto-computed by the executor.

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

**Static Graph** — fixed execution order defined upfront:

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
Stores the workflow spec in the database. The system parses the header and indexes it under the computed `workflow_uri` (e.g. `legal-contract-review-pipeline-1:1.0.0-stable`).

> **Tip:** Save your spec as `spec.json` in your working directory before running the command.

---

## 4. Step 3 — Deploy the Workflow Controller

After registration, deploy a controller instance that will execute the workflow.

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

| Field | Description |
|---|---|
| `DEPLOYER_ID` | ID of the deployer service (path param) |
| `deployment_name` | Human-readable name for this deployment |
| `workflow_id` | Unique identifier for this controller instance |
| `workflow_uri` | Must match the `workflow_uri` of the registered spec exactly |
| `policy_db_url` | Base URL of the policy/rules engine |
| `delegate_api_url` | Base URL of the agent delegate API |

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

> **Note:** The `workflow_uri` in the deploy request must exactly match the registered spec — including name, version, and release. A mismatch will cause a `WorkflowDBError`.

---

## 5. Step 4 — Execute a Task

With the controller deployed, submit a task for execution.

**Request:**

```bash
curl -X POST \
  http://<HOST>:<PORT>/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<your input payload>"
  }'
```

**Example:**

```bash
curl -X POST \
  http://35.223.239.192:30712/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contract: SaaS Subscription Agreement between Acme Corp (vendor) and RetailCo (client). Key clauses: auto-renewal at 15% price increase, no SLA guarantees, data ownership ambiguous, termination requires 180-day notice, liability cap at $5,000 regardless of contract value ($2M/year). Jurisdiction: Delaware, USA."
  }'
```

The input is passed as `initial_input` to the first node in the pipeline. Each subsequent node receives the output of the previous node.

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
| `agent` | Run an AI agent | `nodeID`, `type`, `id`, `settings.model_name` |
| `policy` | Run deterministic rules/logic | `nodeID`, `type`, `id`, `policyType` |
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
| `workflow_uri` in deploy doesn't match registered spec | `WorkflowDBError` at deploy time | Copy the URI exactly from the header: `{name}:{version}-{release}` |
| Duplicate `nodeID` values in `nodes` | `WorkflowSpecError` on init | Every node must have a unique `nodeID` |
| Graph references a `nodeID` not defined in `nodes` | `WorkflowSpecError` on init | Ensure all IDs in the graph match node definitions exactly |
| `policyType` missing on a `policy` node | `WorkflowSpecError` | Always set `policyType` for every policy node |
| `model_name` missing on an `agent` node | Warning at runtime, unpredictable behaviour | Always set `model_name` in `settings` |
| Sub-workflow `id` doesn't match a registered `workflow_uri` | `WorkflowDBError` at runtime | Ensure the target workflow is registered before referencing it |
| Typo in a `nodeID` string | Silent routing failure | Double-check all node IDs — copy-paste rather than retype |
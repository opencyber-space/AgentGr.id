# Workflow JSON Technical Documentation

---

## Table of Contents

1. [Schema Reference](#1-schema-reference)
2. [Guide to Creating Workflows](#2-guide-to-creating-workflows)
3. [Complete Workflow JSON Examples](#3-complete-workflow-json-examples)

---

## 1. Schema Reference

A Workflow JSON is a structured object composed of two top-level keys: `header` and `body`.

---

### 1.1 Top-Level Structure

| Field    | Type   | Required | Description                                      |
|----------|--------|----------|--------------------------------------------------|
| `header` | object | Yes      | Identity and metadata for the workflow           |
| `body`   | object | Yes      | Nodes and graph definition for the workflow      |

---

### 1.2 `header`

| Field         | Type   | Required | Description                                              |
|---------------|--------|----------|----------------------------------------------------------|
| `workflow_id` | object | Yes      | Unique identity of the workflow                          |
| `metadata`    | object | No       | Descriptive information about the workflow               |
| `workflow_uri`| string | Auto     | Computed by the workflow service as `name:version-release` when the workflow is registered. Do not set manually — any value you provide is overwritten. |

#### `header.workflow_id`

| Field     | Type   | Required | Description                                  |
|-----------|--------|----------|----------------------------------------------|
| `name`    | string | Yes      | Workflow name (e.g., `fraud-detection`)      |
| `version` | string | Yes      | Semantic version (e.g., `1.0`)               |
| `release` | string | Yes      | Release tag (e.g., `stable`, `beta`, `rc1`)  |

#### `header.metadata`

| Field         | Type   | Required | Description                                  |
|---------------|--------|----------|----------------------------------------------|
| `description` | string | No       | Human-readable purpose of the workflow       |
| `owner`       | string | No       | Team or individual responsible               |
| `created_at`  | string | No       | ISO 8601 timestamp of creation               |

> The workflow service stores only these three metadata fields; any other keys under `metadata` are dropped on registration.

---

### 1.3 `body`

| Field   | Type            | Required | Description                                                  |
|---------|-----------------|----------|--------------------------------------------------------------|
| `nodes` | array of objects| Yes      | List of all nodes (steps) in the workflow                    |
| `graph` | object          | No       | Defines execution order. If omitted (or empty), every node is an entry node: nodes run one after another in the order they are declared, and each receives the workflow's initial input. |

---

### 1.4 Node Fields (`body.nodes[]`)

Each node in the `nodes` array is an object with the following fields:

| Field        | Type   | Required            | Description                                                            |
|--------------|--------|---------------------|------------------------------------------------------------------------|
| `nodeID`     | string | Yes                 | Unique, non-empty identifier for this node within the workflow         |
| `type`       | string | Yes                 | Node type. One of: `policy`, `agent`, `workflow`                       |
| `id`         | string | Yes                 | Non-empty reference to the resource — policy rule URI, function ID, agent subject ID, or sub-workflow `workflow_uri` |
| `policyType` | string | Yes (if `type=policy`) | One of: `local`, `central`, `function`, `job`                    |
| `settings`   | object | Conditional         | Node-level configuration. Required keys depend on `policyType`         |
| `parameters` | object | No                  | Runtime arguments passed to the policy executor (used by `local`, `central` and `job` policies) |

> The workflow service persists only the fields listed above for each node. Any additional keys on a node are dropped when the workflow is registered.

#### `settings` Required Keys by `policyType`

| `policyType` | Required `settings` keys              | Optional `settings` keys                              |
|--------------|---------------------------------------|-------------------------------------------------------|
| `local`      | _(none)_                              | —                                                     |
| `central`    | `executor_id`, `endpoint`             | —                                                     |
| `function`   | `endpoint`                            | —                                                     |
| `job`        | `executor_id`, `endpoint`             | `job_name`, `node_selector`, `poll_interval`, `max_retries` |

> **Note:** `endpoint` must be a string starting with `http` (e.g. `http://…` or `https://…`).  
> `poll_interval` and `max_retries` must be positive integers.

Defaults for optional `job` settings:

| Key             | Default                              |
|-----------------|--------------------------------------|
| `job_name`      | `job-<nodeID>-<8 random hex chars>`  |
| `node_selector` | `{}`                                 |
| `poll_interval` | `2` (seconds)                        |
| `max_retries`   | `30` (polling attempts)              |

#### `settings` for `agent` nodes

| Key          | Type   | Required | Description                                |
|--------------|--------|----------|--------------------------------------------|
| `model_name` | string | No*      | Model to run the agent with. Strongly recommended. |

> *Omitting `model_name` on an agent node will log a warning but will not fail validation. The value (or an empty string) is always sent to the agent as `task_data.model_name`.

---

### 1.5 `body.graph`

The `graph` object controls how nodes are connected and in what order they execute. It supports two modes: **static** and **dynamic**.

#### Static Graph

| Field  | Type             | Required | Description                                                         |
|--------|------------------|----------|---------------------------------------------------------------------|
| `type` | string           | No       | Set to `"static"` (default if `type` is omitted). Must be `"static"` or `"dynamic"`. |
| `<nodeID>` | array of strings | No   | Each key is a parent `nodeID`; value is a list of child `nodeID`s  |

#### Dynamic Graph

| Field    | Type   | Required | Description                                                                 |
|----------|--------|----------|-----------------------------------------------------------------------------|
| `type`   | string | Yes      | Must be `"dynamic"`                                                         |
| `nodeID` | string | Yes      | The `nodeID` of the **router node** that controls execution at runtime      |

> Any other keys in a dynamic graph are ignored (a warning is logged).

---

## 2. Guide to Creating Workflows

---

### 2.1 Node Types

There are three types of nodes available in a workflow.

---

#### 2.1.1 Policy Node (`type: "policy"`)

A policy node runs a deterministic rule or function. It requires a `policyType` field, which determines which executor is used and what `settings` are needed.

| `policyType` | What it does                                                                   |
|--------------|--------------------------------------------------------------------------------|
| `local`      | Evaluates a policy rule locally using `LocalType1Evaluator`                    |
| `central`    | Calls a centralized policy executor via a remote endpoint                      |
| `function`   | Invokes a serverless/function endpoint directly                                |
| `job`        | Submits a long-running job to an executor and polls for completion             |

How each `policyType` is executed:

| `policyType` | Request made by the workflow executor | Result used |
|---|---|---|
| `local`    | Fetches the policy (code, parameters, settings) for `id` from the Policy DB at `POLICY_DB_URL`, then runs it in-process with the node input. Node `parameters` are merged with the policy's stored parameters; on a key conflict the stored policy value wins. The policy is fetched and initialised each time the node runs. | Return value of the policy |
| `central`  | `POST {endpoint}/executor/{executor_id}/execute_policy` with `{"policy_rule_uri": id, "input_data": <input>, "parameters": <parameters>}` | `data` field of the response (response must have `success: true`) |
| `function` | `POST {endpoint}/function/call_function/{id}` with the node input as the JSON body | `data` field of the response (response must have `success: true`) |
| `job`      | `POST {endpoint}/jobs/submit/{executor_id}` with `{"name": job_name, "policy_rule_uri": id, "policy_rule_parameters": <parameters>, "node_selector": ..., "inputs": <input>}`, then polls `GET {endpoint}/jobs/{job_id}` every `poll_interval` seconds, up to `max_retries` times | `data.job_output_data` once `data.job_status == "completed"`; a `TimeoutError` (reported as a node failure) otherwise |

Remote calls (`central`, `function`, job submit/poll) use a 10-second HTTP timeout.

**`local` policy** — simplest type, no remote dependencies:
```json
{
  "nodeID": "eligibility-check",
  "type": "policy",
  "id": "rules/eligibility-v1",
  "policyType": "local",
  "settings": {},
  "parameters": { "threshold": 0.8 }
}
```

**`central` policy** — delegates to a central rules engine:
```json
{
  "nodeID": "risk-score",
  "type": "policy",
  "id": "rules/risk-scoring-v2",
  "policyType": "central",
  "settings": {
    "executor_id": "central-executor-01",
    "endpoint": "https://rules-engine.internal/execute"
  },
  "parameters": { "context": "loan-application" }
}
```

**`function` policy** — calls a lightweight function endpoint:
```json
{
  "nodeID": "format-output",
  "type": "policy",
  "id": "functions/formatter",
  "policyType": "function",
  "settings": {
    "endpoint": "https://functions.internal/format"
  }
}
```

**`job` policy** — submits a batch job and waits for results:
```json
{
  "nodeID": "ml-scoring-job",
  "type": "policy",
  "id": "rules/ml-score-v3",
  "policyType": "job",
  "settings": {
    "executor_id": "job-executor-gpu",
    "endpoint": "https://jobs.internal/submit",
    "job_name": "ml-score-run-001",
    "poll_interval": 5,
    "max_retries": 60
  }
}
```

---

#### 2.1.2 Agent Node (`type: "agent"`)

An agent node delegates execution to an AI agent via the Delegate API (`/api/submit-and-wait`). The agent is identified by `id` (its `subject_id`) and the model to use is specified in `settings.model_name`.

```json
{
  "nodeID": "summarize-agent",
  "type": "agent",
  "id": "agents/summarizer-subject",
  "settings": {
    "model_name": "gpt-4o"
  }
}
```

The executor generates a `session_id` and `task_id` (both UUIDs) and posts the following to the Delegate API:

```json
{
  "subject_id": "<node id>",
  "session_id": "<uuid>",
  "task_id":    "<uuid>",
  "task_data":  { "...node input...": "...", "model_name": "<settings.model_name>" }
}
```

- The node input becomes the agent's `job_data`, with `model_name` added to it.
- If the node input is not a dict (for example, a list from multiple parents), it is wrapped as `{"data": <input>}`.
- The executor returns `output.job_output` from the Delegate API response. A missing `output.job_output` is a node failure. `is_error` in the agent result is **not** checked — an agent error result is passed downstream as its (usually empty) `job_output`.
- The Delegate API URL is read from the `DELGATE_API_URL` environment variable of the workflow executor, falling back to a built-in default.

---

#### 2.1.3 Workflow Node (`type: "workflow"`)

A workflow node runs another workflow as a sub-workflow, enabling composition and nesting. The `id` field is the `workflow_uri` of the target workflow, which is fetched from the DB at runtime.

```json
{
  "nodeID": "pre-processing-workflow",
  "type": "workflow",
  "id": "data-preprocessing:1.0-stable"
}
```

The sub-workflow is executed using a fresh `AgentDSLWorkflowExecutor` instance with this node's input (a non-dict input is wrapped as `{"data": <input>}`). Its result — the `outputs` dict, or the terminal output returned by its router if it is dynamic — becomes this node's output. Any failure inside the sub-workflow (including a fetch or spec error) is reported as a `WorkflowNodeError` on this node.

---

### 2.2 Graph Modes

---

#### 2.2.1 Static Workflow

In a static workflow the execution order is fully determined at initialization time using a **topological sort** (Kahn's algorithm). You define an adjacency list where each key is a parent node and its value is the list of nodes it feeds into.

**Input resolution rules:**
- A node with **no parents** receives the `initial_input` of the workflow. This includes nodes that do not appear in the graph at all.
- A node with **one parent** receives that parent's output directly.
- A node with **multiple parents** receives a **list** of all parent outputs.
- Nodes run one at a time, in topological order. Entry nodes start in the order they are declared in `nodes`.
- A node that returns `None` is treated as returning `{}`.
- The workflow result is a dict of `nodeID → output` for all nodes.

**Constraints:**
- No cycles allowed (will raise `WorkflowCycleError`).
- No self-loops.
- All `nodeID` references in the graph must exist in `nodes`.

```json
"graph": {
  "type": "static",
  "node-a": ["node-b", "node-c"],
  "node-b": ["node-d"],
  "node-c": ["node-d"]
}
```

This defines the execution order: `node-a → node-b, node-c → node-d`.

---

#### 2.2.2 Dynamic Workflow (Router)

In a dynamic workflow, execution order is **not predetermined**. Instead, a designated **router node** is called repeatedly at runtime. The router is called once at the start, and then once after **each batch** of nodes it returned has finished. The nodes in a batch run one after another, in the order listed.

The router receives a payload containing:

| Key                  | Description                                              |
|----------------------|----------------------------------------------------------|
| `initial_input`      | The original input passed to `execute()`                 |
| `history`            | Ordered list of all `nodeID`s executed so far            |
| `outputs`            | Map of `nodeID → output` for all completed nodes         |
| `last_executed`      | The last `{nodeID, output}` dict of the last batch (`None` on the first call) |
| `last_executed_batch`| List of all `{nodeID, output}` dicts from the last batch (`[]` on the first call) |

For an `agent` router, this payload is sent as the agent's `task_data` (with `model_name` added).

The router's output (`job_output` for an agent router) is interpreted as follows:

| Router output | Result |
|---|---|
| A non-empty **list** of `{ "nodeID": "...", "input": {...} }` steps | The steps run in order, then the router is called again |
| An **empty list**, `None`, or `{}` | The workflow is complete; the `outputs` map is returned |
| A dict with **one** key `next_steps`, `steps`, `nodes`, `data` or `result` holding a list | That list is used as the steps |
| A dict with **more than one** key | Treated as the **final output**: the workflow ends and returns this dict instead of `outputs` |

Each step's `input` defaults to `{}`; a non-dict `input` is wrapped as `{"data": <input>}`.

```json
"graph": {
  "type": "dynamic",
  "nodeID": "router-agent"
}
```

> The router node itself must be defined in `body.nodes`. It is typically an `agent` node whose underlying model decides the next steps. Each step must reference a node defined in `body.nodes`, and the router **cannot route to itself** — both raise `WorkflowRouterError`.

---

### 2.3 Validation Rules Summary

Spec validation runs when the workflow executor loads the workflow (at executor start-up). Registering a workflow with the workflow service does **not** validate it.

| Rule                                          | Error Raised              |
|-----------------------------------------------|---------------------------|
| Missing `header` or `body`                    | `WorkflowSpecError`        |
| `body.nodes` missing or not a list            | `WorkflowSpecError`        |
| Node missing `nodeID`, `type` or `id`         | `WorkflowSpecError`        |
| Missing `name`, `version`, or `release` in `workflow_id` | `WorkflowSpecError` |
| Duplicate `nodeID` values                     | `WorkflowSpecError`        |
| Unknown node `type`                           | `UnknownNodeTypeError`     |
| Policy node missing `policyType`              | `WorkflowSpecError`        |
| Unknown `policyType`                          | `UnknownPolicyTypeError`   |
| Missing required `settings` keys for policy   | `WorkflowSpecError`        |
| Invalid `endpoint` (not an HTTP URL)          | `WorkflowSpecError`        |
| `poll_interval` / `max_retries` not a positive int | `WorkflowSpecError`   |
| `graph.type` not `static` or `dynamic`        | `WorkflowSpecError`        |
| Graph references a `nodeID` not in `nodes`    | `WorkflowSpecError`        |
| Static graph value is not a list of strings   | `WorkflowSpecError`        |
| Cycle detected in static graph                | `WorkflowCycleError`       |
| Self-loop in static graph                     | `WorkflowCycleError`       |
| Dynamic graph missing `nodeID` (router)       | `WorkflowSpecError`        |
| Router node does not exist in `nodes`         | `WorkflowSpecError`        |

Errors raised while a workflow runs:

| Situation                                     | Error Raised              |
|-----------------------------------------------|---------------------------|
| A node fails (HTTP error, bad response, exception, sub-workflow failure) | `WorkflowNodeError` (carries `node_id`) |
| Router returns an invalid response, a step without `nodeID`, an unknown `nodeID`, or itself | `WorkflowRouterError` |
| Workflow spec cannot be fetched from the workflow service | `WorkflowDBError` |

`UnknownNodeTypeError` and `UnknownPolicyTypeError` are subclasses of `WorkflowSpecError`; `WorkflowCycleError` is not.

---

## 3. Complete Workflow JSON Examples

---

### 3.1 Simple Linear Static Workflow

Two policy nodes in sequence. The output of `step-1` feeds into `step-2`.

```json
{
  "header": {
    "workflow_id": {
      "name": "simple-linear",
      "version": "1.0",
      "release": "stable"
    },
    "metadata": {
      "description": "A simple two-step linear workflow",
      "owner": "platform-team",
      "created_at": "2024-01-15T10:00:00Z"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "step-1",
        "type": "policy",
        "id": "rules/validate-input-v1",
        "policyType": "local",
        "settings": {},
        "parameters": { "strict": true }
      },
      {
        "nodeID": "step-2",
        "type": "policy",
        "id": "rules/enrich-data-v2",
        "policyType": "central",
        "settings": {
          "executor_id": "central-01",
          "endpoint": "https://rules.internal/execute"
        }
      }
    ],
    "graph": {
      "type": "static",
      "step-1": ["step-2"]
    }
  }
}
```

---

### 3.2 Branching and Merging Static Workflow

`ingest` fans out to two parallel checks, which both feed into `final-decision`.

```json
{
  "header": {
    "workflow_id": {
      "name": "loan-approval",
      "version": "2.1",
      "release": "rc1"
    },
    "metadata": {
      "description": "Loan approval with parallel risk and compliance checks",
      "owner": "credit-team",
      "created_at": "2024-03-01T09:00:00Z"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "ingest",
        "type": "policy",
        "id": "rules/normalize-application",
        "policyType": "local",
        "settings": {}
      },
      {
        "nodeID": "risk-check",
        "type": "policy",
        "id": "rules/risk-score-v3",
        "policyType": "central",
        "settings": {
          "executor_id": "risk-executor",
          "endpoint": "https://risk.internal/execute"
        },
        "parameters": { "model": "xgb-v2" }
      },
      {
        "nodeID": "compliance-check",
        "type": "policy",
        "id": "rules/aml-compliance",
        "policyType": "function",
        "settings": {
          "endpoint": "https://compliance.internal/check"
        }
      },
      {
        "nodeID": "final-decision",
        "type": "agent",
        "id": "agents/loan-decision-subject",
        "settings": {
          "model_name": "gpt-4o"
        }
      }
    ],
    "graph": {
      "type": "static",
      "ingest": ["risk-check", "compliance-check"],
      "risk-check": ["final-decision"],
      "compliance-check": ["final-decision"]
    }
  }
}
```

> `final-decision` has two parents, so its input is the list `[risk-check output, compliance-check output]`. Because it is an `agent` node, the list is wrapped and the agent receives `{"data": [risk-check output, compliance-check output], "model_name": "gpt-4o"}`. Parent order follows the order of the graph entries.

---

### 3.3 Dynamic Workflow with a Router Agent

The router agent decides at runtime which nodes to invoke and in what order.

```json
{
  "header": {
    "workflow_id": {
      "name": "adaptive-support",
      "version": "1.0",
      "release": "beta"
    },
    "metadata": {
      "description": "Adaptive customer support triage with LLM-driven routing",
      "owner": "support-eng",
      "created_at": "2024-05-10T12:00:00Z"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "router-agent",
        "type": "agent",
        "id": "agents/triage-router-subject",
        "settings": {
          "model_name": "gpt-4o"
        }
      },
      {
        "nodeID": "classify-intent",
        "type": "policy",
        "id": "rules/intent-classifier",
        "policyType": "function",
        "settings": {
          "endpoint": "https://nlp.internal/classify"
        }
      },
      {
        "nodeID": "fetch-account",
        "type": "policy",
        "id": "rules/account-lookup",
        "policyType": "central",
        "settings": {
          "executor_id": "crm-executor",
          "endpoint": "https://crm.internal/execute"
        }
      },
      {
        "nodeID": "generate-response",
        "type": "agent",
        "id": "agents/response-gen-subject",
        "settings": {
          "model_name": "gpt-4o"
        }
      },
      {
        "nodeID": "escalate-to-human",
        "type": "policy",
        "id": "rules/escalation-trigger",
        "policyType": "local",
        "settings": {}
      }
    ],
    "graph": {
      "type": "dynamic",
      "nodeID": "router-agent"
    }
  }
}
```

> At runtime, `router-agent` receives the full state (history, outputs, last executed batch) and returns a list of next steps. It may choose to run `classify-intent` first, then decide between `generate-response` or `escalate-to-human` based on the result. When it returns an empty list or `None`, the workflow ends and the `outputs` map is returned.

---

### 3.4 Workflow with a Sub-Workflow Node

Calls a separately deployed workflow as a step within a larger workflow.

```json
{
  "header": {
    "workflow_id": {
      "name": "end-to-end-pipeline",
      "version": "3.0",
      "release": "stable"
    },
    "metadata": {
      "description": "Full pipeline with pre-processing delegated to a sub-workflow",
      "owner": "data-platform",
      "created_at": "2024-06-01T08:00:00Z"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "pre-process",
        "type": "workflow",
        "id": "data-preprocessing:1.2-stable"
      },
      {
        "nodeID": "score",
        "type": "policy",
        "id": "rules/ml-scoring-v4",
        "policyType": "job",
        "settings": {
          "executor_id": "gpu-executor-01",
          "endpoint": "https://jobs.internal/submit",
          "poll_interval": 10,
          "max_retries": 30
        }
      },
      {
        "nodeID": "summarize",
        "type": "agent",
        "id": "agents/summary-subject",
        "settings": {
          "model_name": "gpt-4o-mini"
        }
      }
    ],
    "graph": {
      "type": "static",
      "pre-process": ["score"],
      "score": ["summarize"]
    }
  }
}
```

> `pre-process` is an entry node, so it receives the workflow's initial input. It fetches `data-preprocessing:1.2-stable` from the workflow service, runs it in a nested executor with that input, and its complete `outputs` map becomes the input of `score`.

---


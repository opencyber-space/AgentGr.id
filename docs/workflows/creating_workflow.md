# How to Build a Workflow — User Guide

This guide walks you through building a complete workflow from scratch — from defining your header to writing a router agent for dynamic execution.

---

## Table of Contents

1. [Overview — What is a Workflow?](#1-overview)
2. [Step 1 — Define the Header](#2-step-1--define-the-header)
3. [Step 2 — Plan Your Nodes](#3-step-2--plan-your-nodes)
4. [Step 3 — Write Your Nodes](#4-step-3--write-your-nodes)
5. [Step 4 — Define the Graph](#5-step-4--define-the-graph)
6. [Step 5 — Choose: Static or Dynamic?](#6-step-5--choose-static-or-dynamic)
7. [Step 6 — Writing a Router Agent (Dynamic Workflows)](#7-step-6--writing-a-router-agent)
8. [Step 7 — Putting It All Together](#8-step-7--putting-it-all-together)
9. [Common Mistakes to Avoid](#9-common-mistakes-to-avoid)

---

## 1. Overview

A **workflow** is a JSON document that describes a pipeline of steps — called **nodes** — and how they connect to each other. The executor reads this JSON, validates it, and runs the nodes in the right order.

There are two kinds of workflows:

| Type | How execution order is decided |
|------|-------------------------------|
| **Static** | You define the order upfront as a graph. The executor computes it at initialization. |
| **Dynamic** | A **router agent** decides what runs next at runtime, after each step completes. |

A workflow JSON always has two sections:

```
workflow
├── header       ← who is this workflow, metadata
└── body
    ├── nodes    ← what steps exist
    └── graph    ← how they connect (or who decides that at runtime)
```

---

## 2. Step 1 — Define the Header

The header identifies your workflow. Every workflow must have a unique `name`, `version`, and `release`. These three are combined into a `workflow_uri` (e.g. `loan-approval:2.0-stable`) used when referencing the workflow from other places.

```json
"header": {
  "workflow_id": {
    "name":    "loan-approval",
    "version": "2.0",
    "release": "stable"
  },
  "metadata": {
    "description": "End-to-end loan risk assessment and decision workflow",
    "owner":       "credit-risk-team",
    "created_at":  "2024-06-01T09:00:00Z"
  }
}
```

**Naming tips:**
- Use lowercase kebab-case for `name` (e.g. `fraud-detection`, `data-preprocessing`)
- Use semantic versioning for `version` (e.g. `1.0`, `2.1`)
- Use `stable`, `beta`, `rc1` etc. for `release` to indicate maturity

> The `workflow_uri` is auto-computed by the executor — do not set it manually.

---

## 3. Step 2 — Plan Your Nodes

Before writing any JSON, sketch out what your workflow needs to do.

Ask yourself:
- What are the distinct steps?
- Which steps can run in parallel?
- Which steps depend on the output of others?
- Is there a conditional branch (e.g. run fraud investigation only if signals are found)?
- Does any step call another workflow?

**Example — Loan Risk Assessment:**

```
[financial-profile-agent]
        ↓
[market-risk-agent]  [collateral-evaluator-agent]   ← parallel
        ↓                      ↓
        └──── (fraud check?) ──┘
               ↓           ↓
  [fraud-investigation]  [loan-decision-agent]
```

Once you have this picture, you can decide: is this a **static** workflow (the branches are always the same) or a **dynamic** one (a router decides based on actual outputs)?

In this example, the fraud branch is **conditional on output content** — so this calls for a **dynamic workflow** with a router.

---

## 4. Step 3 — Write Your Nodes

Each node in `body.nodes` is one step in your workflow. Choose the right node type for each step.

### Node Type Quick Reference

| You want to... | Use node `type` |
|----------------|-----------------|
| Run a rule/policy | `policy` |
| Run an AI agent | `agent` |
| Delegate to another workflow | `workflow` |

---

### Writing a `policy` Node

Policy nodes run deterministic logic. Choose the `policyType` that fits your deployment:

| `policyType` | When to use it |
|---|---|
| `local` | Simple rule evaluated in-process, no external call |
| `central` | Rule engine hosted on a remote service |
| `function` | Serverless/function endpoint |
| `job` | Long-running batch job, needs polling |

**Example — local policy:**
```json
{
  "nodeID": "validate-input",
  "type": "policy",
  "id": "rules/validate-application-v1",
  "policyType": "local",
  "settings": {},
  "parameters": { "strict_mode": true }
}
```

**Example — central policy:**
```json
{
  "nodeID": "credit-score",
  "type": "policy",
  "id": "rules/credit-scoring-v3",
  "policyType": "central",
  "settings": {
    "executor_id": "central-executor-01",
    "endpoint": "https://rules.internal/execute"
  },
  "parameters": { "bureau": "equifax" }
}
```

**Example — job policy (long-running):**
```json
{
  "nodeID": "ml-risk-model",
  "type": "policy",
  "id": "rules/ml-risk-v5",
  "policyType": "job",
  "settings": {
    "executor_id": "gpu-executor",
    "endpoint": "https://jobs.internal/submit",
    "poll_interval": 5,
    "max_retries": 60
  }
}
```

---

### Writing an `agent` Node

Agent nodes send work to an AI agent via the Delegate API. You need the agent's `subject_id` and the model it should use.

```json
{
  "nodeID": "loan-decision-agent",
  "type": "agent",
  "id": "agents/loan-decision-subject-id",
  "settings": {
    "model_name": "gpt-4o"
  }
}
```

> Always provide `model_name` in settings. Omitting it will work but will generate a warning, and the agent may behave unexpectedly.

The executor automatically generates a `session_id` and `task_id` (UUIDs) for each execution. You do not need to set these.

---

### Writing a `workflow` Node

To call another workflow as a step, use `type: "workflow"`. Set `id` to the `workflow_uri` of the target workflow.

```json
{
  "nodeID": "fraud-investigation-workflow",
  "type": "workflow",
  "id": "fraud-investigation:1.0-stable"
}
```

The target workflow will be fetched from the database at runtime, executed in full with its own nested executor, and its complete outputs returned to the parent workflow.

---

## 5. Step 4 — Define the Graph

The `graph` connects your nodes. How you define it depends on whether your workflow is static or dynamic.

### Static Graph

List each node that has downstream children. The executor will topologically sort these to determine execution order.

```json
"graph": {
  "type": "static",
  "validate-input": ["credit-score", "identity-check"],
  "credit-score":   ["loan-decision-agent"],
  "identity-check": ["loan-decision-agent"]
}
```

**Rules:**
- Nodes not listed as keys (parents) but listed as children are leaf nodes — they produce final output.
- Nodes not mentioned anywhere in the graph are **entry nodes** — they receive the workflow's `initial_input`.
- Multiple parents feed a node → that node receives a **list** of parent outputs.

### Dynamic Graph

Just point to the router node. The executor calls it after every step.

```json
"graph": {
  "type": "dynamic",
  "nodeID": "router-agent"
}
```

The `router-agent` must be defined in `body.nodes` (typically as an `agent` node).

---

## 6. Step 5 — Choose: Static or Dynamic?

Use this table to decide:

| Situation | Use |
|---|---|
| Execution order is always the same | Static |
| All branches are always taken (just in different order) | Static |
| A branch depends on the **content** of a previous output | Dynamic |
| You need to loop or retry based on results | Dynamic |
| Parallel steps always both run | Static |
| Parallel steps run but only one branch continues depending on results | Dynamic |

> **Rule of thumb:** If you would need an `if` statement to decide the next step — use Dynamic.

---

## 7. Step 6 — Writing a Router Agent

The router agent is a Python class that implements the `on_data` method. It receives the workflow state after every node execution and returns a list of next steps.

### What the Router Receives

Every time the executor calls the router, it sends:

| Key | Type | Description |
|---|---|---|
| `initial_input` | dict | The original input passed to `workflow.execute()` |
| `history` | list of strings | All `nodeID`s executed so far, in order |
| `outputs` | dict | Map of `nodeID → output` for all completed nodes |
| `last_executed` | dict or None | `{ "nodeID": "...", "output": {...} }` — the most recent node. `None` on first call. |
| `last_executed_batch` | list | All steps from the most recent batch |

### What the Router Must Return

Your router's `job_output` must be one of:

| Return value | Meaning |
|---|---|
| `[{ "nodeID": "...", "input": {...} }, ...]` | Run these nodes next |
| `[]` | Nothing to run right now (used to wait for parallel nodes) |
| `None` | Workflow is complete — stop execution |

---

### Router Agent Structure

```python
from core.agent_executor import AgentResult, AgentTask, Context
from core.main import main

class RouterAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

    def on_preprocess(self, task: AgentTask):
        # Always return the task — router must always run
        if not isinstance(task.job_data, dict):
            return None
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        history       = task.job_data.get("history", [])
        outputs       = task.job_data.get("outputs", {})
        initial_input = task.job_data.get("initial_input", {})
        last_executed = task.job_data.get("last_executed")
        last_node     = last_executed["nodeID"] if last_executed else None

        next_steps = self._route(last_node, history, outputs, initial_input)

        return AgentResult(
            task_id=task.task_id,
            job_output=next_steps,
            is_error=False,
        )

    def _route(self, last_node, history, outputs, initial_input) -> list:
        # Your routing logic goes here
        ...

main(RouterAgent)
```

---

### Writing the `_route` Method

The `_route` method is where all your routing logic lives. Structure it as a series of `if` checks on `last_node` and `history`.

#### Pattern 1 — First Call (No History)

```python
# First call — no node has run yet
if last_node is None:
    return [{
        "nodeID": "financial-profile-agent",
        "input":  initial_input,
    }]
```

#### Pattern 2 — Linear Step (A → B)

```python
if last_node == "financial-profile-agent":
    profile_output = outputs.get("financial-profile-agent", {})
    return [{
        "nodeID": "market-risk-agent",
        "input":  { **initial_input, "profile": profile_output },
    }]
```

Always merge `initial_input` with any upstream outputs when building the input for the next node — downstream nodes often need both the original request and enriched data from prior steps.

#### Pattern 3 — Fork to Parallel Nodes (A → B + C)

Return multiple steps in one list to run nodes in parallel:

```python
if last_node == "financial-profile-agent":
    profile_output = outputs.get("financial-profile-agent", {})
    return [
        {
            "nodeID": "market-risk-agent",
            "input":  { **initial_input, "profile": profile_output },
        },
        {
            "nodeID": "collateral-evaluator-agent",
            "input":  { **initial_input, "profile": profile_output },
        },
    ]
```

#### Pattern 4 — Waiting for Both Parallel Nodes to Complete

When you fork to two nodes, the router is called after **each one completes**. You need to wait until both are done before continuing.

```python
# Node A finished — but B hasn't run yet. Return [] to wait.
if last_node == "market-risk-agent":
    if "collateral-evaluator-agent" not in history:
        return []   # wait — do nothing for now

# Node B finished — check if A is also done
if last_node == "collateral-evaluator-agent" or (
    last_node == "market-risk-agent" and "collateral-evaluator-agent" in history
):
    both_done = (
        "market-risk-agent" in history
        and "collateral-evaluator-agent" in history
    )
    if both_done:
        # Both parallel nodes complete — continue
        return self._decide_after_parallel(outputs, initial_input)
```

> Returning `[]` does **not** end the workflow. It just means "nothing to schedule right now." The executor continues waiting for in-flight nodes.

#### Pattern 5 — Conditional Branch Based on Output Content

Use an LLM call or any logic to inspect outputs and branch:

```python
def _decide_after_parallel(self, outputs, initial_input):
    # Use LLM to check for fraud signals in outputs
    fraud_result = call_llm_json(FRAUD_SIGNAL_PROMPT, build_user_message(outputs))
    
    combined = {
        **initial_input,
        "market_risk":  outputs.get("market-risk-agent", {}),
        "collateral":   outputs.get("collateral-evaluator-agent", {}),
    }

    if fraud_result.get("fraud_signals_detected"):
        return [{ "nodeID": "fraud-investigation-workflow", "input": combined }]
    else:
        return [{ "nodeID": "loan-decision-agent", "input": combined }]
```

#### Pattern 6 — After a Sub-Workflow

Treat sub-workflow nodes like any other node. Their full `outputs` dict is available in `outputs["nodeID"]`.

```python
if last_node == "fraud-investigation-workflow":
    fraud_output = outputs.get("fraud-investigation-workflow", {})
    return [{
        "nodeID": "loan-decision-agent",
        "input":  {
            **initial_input,
            "financial_profile": outputs.get("financial-profile-agent", {}),
            "market_risk":       outputs.get("market-risk-agent", {}),
            "collateral":        outputs.get("collateral-evaluator-agent", {}),
            "fraud_investigation": fraud_output,
        },
    }]
```

#### Pattern 7 — End the Workflow

Return `[]` after the final node to signal completion:

```python
if last_node == "loan-decision-agent":
    return []   # workflow complete
```

---

### Router Agent Best Practices

**Use constants for node IDs.** Never repeat node ID strings across your routing logic.

```python
# ✅ Good
NODE_FINANCIAL_PROFILE = "financial-profile-agent"
NODE_LOAN_DECISION     = "loan-decision-agent"

# ❌ Bad — typos cause silent routing failures
if last_node == "finacial-profile-agent":   # typo, never matches
```

**Always include a fallback.** Add a `log.warning` and `return []` at the end of `_route` for unknown states instead of letting exceptions propagate.

```python
# Always end _route with a fallback
log.warning("Router reached unknown state | last_node=%s history=%s", last_node, history)
return []
```

**Fail safe on LLM errors.** If an LLM call for conditional routing fails, default to the safer/more conservative branch rather than crashing.

```python
except OpenAIError as e:
    log.error("LLM call failed: %s — defaulting to fraud investigation", e)
    return [{ "nodeID": "fraud-investigation-workflow", "input": combined }]
```

**Build inputs explicitly.** Always construct the `input` dict for each next step explicitly. Don't pass raw `outputs` — select and name only what the next node needs.

```python
# ✅ Good — explicit, predictable
"input": {
    "application_id":   initial_input["application_id"],
    "financial_profile": outputs.get("financial-profile-agent", {}),
    "market_risk":       outputs.get("market-risk-agent", {}),
}

# ❌ Bad — passes everything indiscriminately, next node may break
"input": outputs
```

---

## 8. Step 7 — Putting It All Together

Here is the complete workflow JSON for the Loan Risk Assessment example built through this guide.

```json
{
  "header": {
    "workflow_id": {
      "name":    "loan-risk-assessment",
      "version": "1.0",
      "release": "stable"
    },
    "metadata": {
      "description": "Dynamic loan risk assessment with parallel checks and conditional fraud investigation",
      "owner":       "credit-risk-team",
      "created_at":  "2024-06-01T09:00:00Z"
    }
  },
  "body": {
    "nodes": [
      {
        "nodeID": "router-agent",
        "type": "agent",
        "id": "agents/loan-router-subject-id",
        "settings": { "model_name": "gpt-4o" }
      },
      {
        "nodeID": "financial-profile-agent",
        "type": "agent",
        "id": "agents/financial-profile-subject-id",
        "settings": { "model_name": "gpt-4o" }
      },
      {
        "nodeID": "market-risk-agent",
        "type": "agent",
        "id": "agents/market-risk-subject-id",
        "settings": { "model_name": "gpt-4o" }
      },
      {
        "nodeID": "collateral-evaluator-agent",
        "type": "agent",
        "id": "agents/collateral-evaluator-subject-id",
        "settings": { "model_name": "gpt-4o" }
      },
      {
        "nodeID": "fraud-investigation-workflow",
        "type": "workflow",
        "id": "fraud-investigation:1.0-stable"
      },
      {
        "nodeID": "loan-decision-agent",
        "type": "agent",
        "id": "agents/loan-decision-subject-id",
        "settings": { "model_name": "gpt-4o" }
      }
    ],
    "graph": {
      "type": "dynamic",
      "nodeID": "router-agent"
    }
  }
}
```

And the corresponding router's `_route` logic maps to this execution flow:

```
First call
    └─→ financial-profile-agent

After financial-profile-agent
    └─→ market-risk-agent  +  collateral-evaluator-agent  (parallel)

After market-risk-agent (collateral not done)
    └─→ []  (wait)

After collateral-evaluator-agent (both done)
    ├─→ fraud-investigation-workflow   (if fraud signals detected)
    └─→ loan-decision-agent            (if no fraud signals)

After fraud-investigation-workflow
    └─→ loan-decision-agent

After loan-decision-agent
    └─→ []  (done)
```

---

## 9. Common Mistakes to Avoid

| Mistake | What goes wrong | Fix |
|---|---|---|
| Duplicate `nodeID` values | `WorkflowSpecError` on init | Every node must have a unique `nodeID` |
| Graph references a `nodeID` not in `nodes` | `WorkflowSpecError` on init | Double-check all IDs in your graph match nodes exactly |
| `policyType` missing on a `policy` node | `WorkflowSpecError` | Always set `policyType` for every policy node |
| Missing `endpoint` in `central`/`function`/`job` settings | `WorkflowSpecError` | Check required settings per `policyType` |
| Router returns `[]` intending to end the workflow | Workflow hangs waiting for in-flight nodes | Use `[]` only to wait for parallel nodes; use `None` or final `[]` after your last real step |
| Router routes to itself | `WorkflowRouterError` | The router node cannot appear in its own response |
| Not merging `initial_input` into downstream node inputs | Later nodes lose the original request data | Always spread `initial_input` into every step's `input` dict |
| Typo in `nodeID` string in router | Silent routing failure — router never matches, returns `[]` immediately | Use constants for all node ID strings |
| `model_name` missing on agent node | Warning at runtime, unpredictable agent behaviour | Always set `model_name` in agent `settings` |
| Sub-workflow `id` doesn't match a registered `workflow_uri` | `WorkflowDBError` at runtime | Ensure the target workflow is registered in the DB with the exact URI |

---


# Agent DSL Manager — Client Developer Documentation

## Introduction

The **DSL Manager** module provides a unified interface to **register**, **describe**, and **execute** DSL-based workflows. It also includes utilities to **render LLM-readable task descriptions** and to **plan** which DSL/agent/tool to use for a goal.

It provides:

* **Pluggable workflow backends** (local loader / remote registry / custom)
* **Consistent execution API** (`execute`, `deploy`, `execute_command`, etc.)
* **LLM-friendly descriptions** via `DSLPlanner`
* **Optional human-in-the-loop** through NATS helpers

A typical workflow is:

1. **Declare a `DSLItem`** in the subject spec.
2. **Build/resolve a DSL executor** from the item.
3. **Register the executor** in `DSLWorkflowsManager`.
4. **Describe DSLs** with `DSLPlanner`, optionally plan with `Planner`.
5. **Execute** the chosen DSL and collect results/feedback.

---

## Registering DSLs in Subject Specification

DSLs are registered using a `DSLItem`.

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class DSLItem:
    dsl_type: str                 # e.g. "registry", "local", "remote"
    dsl_workflow_id: str          # workflow identifier/URI
    dsl_parameters: Dict[str, Any] = field(default_factory=dict)
```

> `dsl_type`: Application specific type
> `dsl_workflow_id` is the logical route/URI (e.g., `"registry:add-workflow@1.0"`, `"local:math.add"`, `"remote://dsl-executor/add"`).
> `dsl_parameters` carries backend-specific settings (e.g., registry URL, module path, auth headers, timeouts).

---

### Minimal Required Configuration

```json
{
  "dsl_type": "registry",
  "dsl_workflow_id": "add-workflow@1.0",
  "dsl_parameters": {
    "registry_url": "http://dsl-registry-service"
  }
}
```

---

### Field Descriptions

| Field                 | Location | Type   | Description                                                                                          |
| --------------------- | -------- | ------ | ---------------------------------------------------------------------------------------------------- |
| **dsl\_type**         | root     | `str`  | Loader/executor type: `"registry"`, `"local"`, or `"remote"`.                                        |
| **dsl\_workflow\_id** | root     | `str`  | Workflow name/URI/version.                                                                           |
| **dsl\_parameters**   | root     | `dict` | Backend-specific config: `registry_url`, `module_path`, `executor_url`, `headers`, `timeout_s`, etc. |

---

### Example in a Subject Specification

```json
{
  "subject_id": "agent-dsl-executor",
  "subject_type": "agent",
  "dsls": [
    {
      "dsl_type": "registry",
      "dsl_workflow_id": "add-workflow@1.0",
      "dsl_parameters": {
        "registry_url": "http://dsl-registry-service",
        "extras": { "x": 10 }
      }
    },
    {
      "dsl_type": "local",
      "dsl_workflow_id": "math.add",
      "dsl_parameters": {
        "module_path": "agents.dsl.math.add",
        "output_module": "default_output"
      }
    },
    {
      "dsl_type": "remote",
      "dsl_workflow_id": "transform.text.summarize",
      "dsl_parameters": {
        "executor_url": "http://dsl-executor.svc.cluster.local:8080/execute",
        "headers": { "Authorization": "Bearer $RUNTIME_TOKEN" },
        "timeout_s": 20
      }
    }
  ]
}
```

---

## Import and Setup

```python
from agent_sdk.utils.dsl_manager import (
    DSLWorkflowsManager,
    DSLPlanner,
    HumanInteractionClient
)

from agent_sdk.utils.planner import Planner  # LLM-based planning
```

---

## Building an Executor from a `DSLItem`

```python
def build_executor_from_dsl_item(item: dict):
    dsl_type = item["dsl_type"]
    workflow_id = item["dsl_workflow_id"]
    params = item.get("dsl_parameters", {})

    if dsl_type == "registry":
        # Resolve via Registry service
        registry_url = params["registry_url"]
        return DSLWorkflowsManager(registry_url).get_workflow(workflow_id)

    if dsl_type == "local":
        # Dynamically import & construct local executor
        module_path = params["module_path"]  # e.g. "agents.dsl.math.add"
        from importlib import import_module
        mod = import_module(module_path)
        return getattr(mod, "Executor")(**params)

    if dsl_type == "remote":
        # Wrap a remote HTTP/gRPC executor
        from agent_sdk.utils.remote_dsl import RemoteDSLWorkflowExecutor
        return RemoteDSLWorkflowExecutor(
            executor_url=params["executor_url"],
            headers=params.get("headers"),
            timeout_s=params.get("timeout_s", 15)
        )

    raise NotImplementedError(f"Unknown dsl_type: {dsl_type}")
```

---

## DSLWorkflowsManager

```python
manager = DSLWorkflowsManager("http://dsl-registry-service")

# Register
manager.register_new_dsl_workflow("add_workflow", "add-workflow@1.0", extras={"x": 10})

# Execute (returns output of the workflow's configured output module)
result = manager.execute("add_workflow", {"x": 5}, output_module="default_output")

# Other operations
manager.deploy("add_workflow")             # preload modules / warmup
manager.check_execute("add_workflow")      # dry-run validation
manager.execute_command("add_workflow", "reindex", {"force": True})
wf = manager.get_workflow("add_workflow")  # access underlying executor
all_dsls = manager.list()                  # list registered
search_meta = manager.get_searchable_representation()
manager.unregister_dsl_workflow("add_workflow")
```

**Common parameters**

* `name`: local alias in the manager’s registry.
* `workflow_id`: backing workflow reference (same as `dsl_workflow_id`).
* `output_module`: which terminal output node/module to read from if multiple.
* `extras`: optional config passed to executor (e.g., constants, defaults).

---

## DSLPlanner

Use `DSLPlanner` to generate **LLM- and human-readable** summaries of your available DSLs and how to call them.

```python
planner = DSLPlanner(dsl_workflows_manager=manager)
planner.prepare_dsl_descriptions()                 # scans manager & builds schema overview
planner.add_task_description("Add two numbers")    # free-form task
planner.add_input_conversion({"x": 5})             # example input mapping
full = planner.get_full_description()              # feed to an LLM or show to users
print(full)
```

**What it does**

* Renders each registered DSL’s name, purpose, inputs/outputs, and example calls.
* Helps LLMs choose between DSLs based on a task description.

---

## Planner (LLM-integrated DSL Selector)

`Planner` composes job metadata + DSL descriptions + agents/tools into a **single prompt** and calls a **behavior controller** (LLM) to propose a plan (e.g., “Use `add_workflow` with inputs {x: 5, y: 8}”).

```python
planner = Planner(
    behavior_controller_url="http://behavior.svc/planner",
    known_subjects=[...],
    tools_functions_registry=[...]
)

planner.set_custom_description("project_type", "NLP utilities")

final_input = planner.generate_final_input(
    job_goal={"intent": "summarization"},
    job_objectives={"accuracy": "high"},
    job_steerability_data={"style": "concise"},
    task_description="Summarize customer reviews"
)

plan_response = planner.create_plan("Summarize customer reviews")
```

**Highlights**

* **Prompt construction** with job goal/objectives + DSL/agent/tool metadata.
* **Behavior controller call** via `TaskProcessorClient` (implementation detail).
* **Hooks** via `set_custom_job_transformer` for custom formatting/filters.

---

## Human Interaction (Optional)

Use these if a workflow requires approval, data fixes, or confirmations:

```python
hic = HumanInteractionClient(nats_url="nats://nats:4222", topic="dsl.human")
# Send question → await response via MessageResponseWaiter (internal utility)
```

---

## Writing a Custom DSL Executor

Implement a simple interface (`execute`, optional `deploy`/`check_execute`/`execute_command`):

```python
class MyCustomDSLExecutor:
    def __init__(self, **kwargs):
        ...

    def deploy(self):
        # module preload / cache warmup
        ...

    def check_execute(self, input_data: dict) -> bool:
        # validate inputs; return True/raise
        return True

    def execute(self, input_data: dict, output_module: str = None):
        # perform the workflow logic and return output
        return {"result": ...}

    def execute_command(self, command_name: str, data: dict):
        # custom control-plane actions (e.g., reindex)
        return {"ok": True}
```

Register with the manager:

```python
executor = MyCustomDSLExecutor(...)
manager.register_new_dsl_workflow("custom.flow", "custom.flow@1.0", extras={"mode": "fast"})
manager.deploy("custom.flow")
out = manager.execute("custom.flow", {"x": 1, "y": 2})
```

---

## Quick Subject Spec Example (two DSLs)

```json
{
  "subject_id": "agent-dsl",
  "subject_type": "agent",
  "dsls": [
    {
      "dsl_type": "registry",
      "dsl_workflow_id": "add-workflow@1.0",
      "dsl_parameters": {
        "registry_url": "http://dsl-registry-service"
      }
    },
    {
      "dsl_type": "remote",
      "dsl_workflow_id": "transform.text.summarize",
      "dsl_parameters": {
        "executor_url": "http://dsl-executor.svc.cluster.local:8080/execute",
        "timeout_s": 20
      }
    }
  ]
}
```

---

## Minimal End-to-End Example

```python
# 1) Build executors from DSLItems (e.g., loaded from subject spec)
items = [
    {"dsl_type": "registry", "dsl_workflow_id": "add-workflow@1.0",
     "dsl_parameters": {"registry_url": "http://dsl-registry-service"}},
    {"dsl_type": "remote", "dsl_workflow_id": "transform.text.summarize",
     "dsl_parameters": {"executor_url": "http://dsl-exec:8080/execute"}}
]

manager = DSLWorkflowsManager("http://dsl-registry-service")
for it in items:
    exec_obj = build_executor_from_dsl_item(it)
    alias = it["dsl_workflow_id"]
    manager.register_new_dsl_workflow(alias, it["dsl_workflow_id"])
    # Optionally bind the resolved executor to alias if needed
    # manager.override_executor(alias, exec_obj)

# 2) Describe for LLM
planner = DSLPlanner(manager)
planner.prepare_dsl_descriptions()
planner.add_task_description("Add two numbers")
print(planner.get_full_description())

# 3) Execute
out = manager.execute("add-workflow@1.0", {"x": 5, "y": 7}, output_module="default_output")
print(out)
```

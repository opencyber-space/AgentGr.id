# Functions & Tools — Client Developer Documentation

## Introduction

The **Functions & Tools** subsystem provides a unified, LLM-friendly way to **register**, **discover**, and **execute** reusable capabilities in your agent stack.

It supports:

* **Spec-time registration** of items that your runtime can resolve later
* **Local** and **remote** execution backends
* **LLM discoverability** via a searchable registry
* **Custom tooling** with lifecycle hooks and admin commands

> Important: `FunctionItem`, `ToolItem`, and `BuiltinModules` are **spec-registration types only**. They declare *what exists* and *how to call it*. Your runtime resolves and executes them.

---

## Registration Types

### FunctionItem (spec registration)

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class FunctionItem:
    function_id: str
    function_custom_parameters: Dict[str, Any] = field(default_factory=dict)
    function_calling_config: Dict[str, Any] = field(default_factory=dict)
```

* **function\_id**: Unique logical name or URI (e.g., `"math.add"`, `"svc://billing.refund"`).
* **function\_custom\_parameters**: Deployment-agnostic extras (defaults, constraints, tags).
* **function\_calling\_config**: How to call it (protocol, endpoint, method, headers, timeout, auth refs).

---

### ToolItem (spec registration)

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Literal

@dataclass
class ToolItem:
    tool_id: str
    tool_description: str = ""
    tool_execution_mode: Literal["local", "remote"] = "local"
    tool_custom_config: Dict[str, Any] = field(default_factory=dict)
    tool_calling_config: Dict[str, Any] = field(default_factory=dict)
```

* **tool\_id**: Unique logical name/URI.
* **tool\_description**: Human/LLM-facing description.
* **tool\_execution\_mode**: `"local"` (Python executor) or `"remote"` (HTTP/gRPC/etc).
* **tool\_custom\_config**: Deployment-agnostic extras (schemas, defaults).
* **tool\_calling\_config**: Transport details for **remote** tools or constructor args for **local** tools.

---

### BuiltinModules (custom tool packs)

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class BuiltinModules:
    module_id: str = ""
    module_description: str = ""
    module_input_template: str = ""
    module_output_template: str = ""
    module_management_commands: List[ManagementCommandItem] = field(default_factory=list)
```

Use this to bundle **predefined local tools** with consistent I/O templates and admin commands.

---

## Runtime Architecture

| Component                     | Purpose                                                             |
| ----------------------------- | ------------------------------------------------------------------- |
| `ToolsFunctionsRegistry`      | In-memory registry + execution router for tools & functions.        |
| `ToolExecutor` (abstract)     | Base class for **local** tool logic with `validate/deploy/execute`. |
| `LocalCustomTool`             | Adapter binding a `ToolExecutor` to a `ToolItem`.                   |
| `PredefinedToolExecutor`      | Executes **remote** tools per `tool_calling_config`.                |
| `PredefinedFunctionExecutor`  | Executes **remote** functions per `function_calling_config`.        |
| `ToolsRegistrySDK` (optional) | REST client to CRUD/search tools in an external Tools service.      |

---

## Minimal Subject Spec Example

```json
{
  "subject_id": "agent-capabilities",
  "subject_type": "agent",
  "tools": [
    {
      "tool_id": "local.multiplier",
      "tool_description": "Multiply x by a factor",
      "tool_execution_mode": "local",
      "tool_custom_config": { "schema": { "input": {"x":"number","factor":"number"} } },
      "tool_calling_config": { "executor_class": "agents.tools.multiplier.MultiplierTool" }
    },
    {
      "tool_id": "remote.summarize",
      "tool_description": "Summarize text via HTTP service",
      "tool_execution_mode": "remote",
      "tool_calling_config": {
        "protocol": "http",
        "endpoint": "http://summary.svc.cluster.local:8080/summarize",
        "method": "POST",
        "headers": {"Authorization": "Bearer ${RUNTIME_TOKEN}"},
        "timeout_s": 20
      }
    }
  ],
  "functions": [
    {
      "function_id": "math.add",
      "function_custom_parameters": {"max_terms": 10},
      "function_calling_config": {
        "protocol": "grpc",
        "endpoint": "dns:///math.svc:9000",
        "method": "Add",
        "timeout_s": 10
      }
    }
  ]
}
```

---

## Local Tool Executors

### ToolExecutor interface

```python
class ToolExecutor:
    def deploy(self): ...
    def validate_inputs(self, input_data: dict) -> bool: ...
    def execute(self, input_data: dict) -> dict: ...
    def execute_command(self, command_name: str, data: dict) -> dict: ...
```

### Example: local multiplier tool

```python
# agents/tools/multiplier.py
from agent_sdk.tools import ToolExecutor

class MultiplierTool(ToolExecutor):
    def deploy(self):
        # preload assets if needed
        pass

    def validate_inputs(self, input_data):
        return isinstance(input_data.get("x"), (int, float)) and isinstance(input_data.get("factor"), (int, float))

    def execute(self, input_data):
        if not self.validate_inputs(input_data):
            raise ValueError("x and factor must be numbers")
        return {"result": input_data["x"] * input_data["factor"]}
```

---

## ToolsFunctionsRegistry — Core Usage

```python
from agent_sdk.tools.registry import ToolsFunctionsRegistry
from agent_sdk.tools.local import LocalCustomTool

registry = ToolsFunctionsRegistry()

# Register LOCAL tool
tool_item = {
  "tool_id": "local.multiplier",
  "tool_execution_mode": "local",
  "tool_calling_config": { "executor_class": "agents.tools.multiplier.MultiplierTool" }
}
registry.add_local_tool(LocalCustomTool, tool_item)

# Register REMOTE tool
remote_tool_item = {
  "tool_id": "remote.summarize",
  "tool_execution_mode": "remote",
  "tool_calling_config": {
    "protocol": "http",
    "endpoint": "http://summary.svc:8080/summarize",
    "method": "POST",
    "timeout_s": 20
  }
}
registry.add_tool(remote_tool_item)  # handled by PredefinedToolExecutor

# Register REMOTE function
fn_item = {
  "function_id": "math.add",
  "function_calling_config": {
    "protocol": "grpc",
    "endpoint": "dns:///math.svc:9000",
    "method": "Add",
    "timeout_s": 10
  }
}
registry.add_function(fn_item)       # handled by PredefinedFunctionExecutor

# Execute
out1 = registry.execute_tool("local.multiplier", {"x": 6, "factor": 7})
out2 = registry.execute_tool("remote.summarize", {"text": "Long text..."})
out3 = registry.execute_function("math.add", {"numbers": [1, 2, 3]})
```

**Routing rules**

* Tool with `tool_execution_mode="local"` → `LocalCustomTool` → your `ToolExecutor`.
* Tool with `tool_execution_mode="remote"` → `PredefinedToolExecutor` (HTTP/gRPC/etc).
* Functions always route through `PredefinedFunctionExecutor` unless you wrap them as tools.

---

## Calling Config Conventions

These are **guidelines** for `*_calling_config`. Your runtime may extend them.

**HTTP (remote tool/function)**

```json
{
  "protocol": "http",
  "endpoint": "http://host:port/path",
  "method": "POST",
  "headers": {"Authorization": "Bearer ${TOKEN}"},
  "timeout_s": 15,
  "retry": {"tries": 3, "backoff_s": 0.5},
  "input_mapping": {"text": "$.input"},
  "output_mapping": {"result": "$.data.summary"}
}
```

**gRPC (remote function)**

```json
{
  "protocol": "grpc",
  "endpoint": "dns:///service.svc:9000",
  "method": "Package.Service/Method"  // or "Method" if your client binds service
}
```

**Local (tool)**

```json
{
  "executor_class": "agents.tools.multiplier.MultiplierTool",
  "constructor_args": {"warmup": true}
}
```

---

## Searchable Representation (LLM Discovery)

```python
searchable = registry.get_searchable_representation()
```

Each entry typically includes:

| Field           | Description                                     |
| --------------- | ----------------------------------------------- |
| `id`            | Tool or function ID                             |
| `type`          | `"tool"` or `"function"`                        |
| `description`   | Human/LLM-readable description                  |
| `tags`          | Keywords for ranking and filtering              |
| `sub_type`      | Domain category (e.g., `nlp.summarize`, `math`) |
| `runtime_type`  | `local`, `http`, `grpc`, `cli`, etc.            |
| `protocol_type` | `http`, `grpc`, `python`, etc.                  |
| `schema`        | Input/output schema (OpenAPI/JSON Schema-like)  |
| `examples`      | Minimal call examples                           |

This is designed for **Planner** / **DSLPlanner** selection flows.

---

## Built-in Modules (Custom Tool Packs)

Use `BuiltinModules` to ship a curated set of tools with consistent I/O and admin controls.

```python
builtin = BuiltinModules(
  module_id="text.utils",
  module_description="Text utilities: normalize, extract, summarize",
  module_input_template='{"text": "string"}',
  module_output_template='{"result": "string"}',
  module_management_commands=[
    {"name": "warmup", "description": "Preload models"},
    {"name": "reindex", "description": "Rebuild local caches"}
  ]
)

registry.add_builtin_module(builtin)
registry.execute_tool("text.utils/summarize", {"text": "..."})
registry.execute_tool_command("text.utils/summarize", "warmup", {})
```

---

## Management & CRUD (optional external service)

If you use a Tools Service:

```python
from agent_sdk.tools.sdk import ToolsRegistrySDK

sdk = ToolsRegistrySDK(base_url="http://tools-service")

sdk.create_tool({...})
meta = sdk.get_tool_by_id("remote.summarize")
sdk.update_tool("remote.summarize", {"tags": ["nlp","summary"]})
sdk.delete_tool("legacy.tool")
hits = sdk.execute_query("summary AND remote")
```

---

## Validation & Health

* **Local tools** should implement `validate_inputs()` and optionally `deploy()` (warmup).
* **Remote calls** should support:

  * Timeouts & retries
  * Input/output mapping
  * Typed schema validation (pre/post)

Example health check:

```python
registry.check_tool("remote.summarize")      # ping HTTP endpoint /health
registry.check_function("math.add")          # gRPC reflection or custom "Ping"
```

---

## Best Practices

* **Spec vs runtime**: keep secrets out of spec; pass via env/secret refs at runtime.
* **Stable IDs**: choose deterministic `tool_id` / `function_id`.
* **Schemas**: define `schema.input` / `schema.output` for validation and LLM clarity.
* **Observability**: record latency, error rate, payload size, backend, and retries.
* **LLM surfacing**: keep `tool_description` concise, action-oriented, and tag-rich.
* **Idempotency**: design functions/tools to be safe for retry.

---

## End-to-End Quickstart

```python
# 1) Load spec (tools & functions array) and register
registry = ToolsFunctionsRegistry()

for t in spec["tools"]:
    if t.get("tool_execution_mode", "local") == "local":
        registry.add_local_tool(LocalCustomTool, t)
    else:
        registry.add_tool(t)

for f in spec["functions"]:
    registry.add_function(f)

# 2) Discover for LLM
for entry in registry.get_searchable_representation():
    print(entry["id"], entry.get("description"))

# 3) Execute
result_tool = registry.execute_tool("remote.summarize", {"text": "Hello world"})
result_fn   = registry.execute_function("math.add", {"numbers": [1, 2, 3]})
```

This gives you a clean separation between **spec-time registration** (`FunctionItem`, `ToolItem`, `BuiltinModules`) and **runtime execution** (registry routing, local executors, and remote invocations) with **LLM-ready discovery** built in.

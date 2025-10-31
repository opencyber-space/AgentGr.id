# Agent Execution

## Introduction

The `agents_sdk.executor` module provides the core **Stage 2 task execution system** for the agents-based multi-stage planner. It is responsible for executing a validated task graph (DAG or SubGraph), where each node may represent tool invocations, code generators, DSL workflows, LLMs, agent calls, or even recursive nested execution flows.

This module ensures that:

* Each task is executed only after all dependencies are met
* Task results are persisted into the subtask and task database
* Different execution types are routed to appropriate executor modules
* DAGs are validated for acyclicity and connectivity
* Optional dry-run (estimation) is supported before execution
* A custom multiprocessing pool manages parallelism

It is typically used after a Stage 1 planner has constructed a valid plan DAG (`PlannerTask` instances with metadata), and the system is ready to perform **actual execution**, with support for **subgraph-level dry runs**, **output aggregation**, and **recursive plans**.

---

## Importing Guide

To use the executor system in your application or agent runtime, you can import all primary classes and modules using:

```python
from agents_sdk.executor import *
```

This provides access to the following key components:

| Class/Module                | Purpose                                                               |
| --------------------------- | --------------------------------------------------------------------- |
| `DAGActionExecutor`         | Executes a full DAG of `PlannerTask` nodes end-to-end                 |
| `SubGraphExecutor`          | Executes a partial task graph (subgraph) within a larger plan         |
| `SubGraphEstimateRunner`    | Performs a dry-run estimation of a subgraph to validate executability |
| `DAGManager`                | Validates and manages task graph structure and readiness              |
| `NodeExecutorProcessPool`   | Handles task-level concurrency via multiprocessing                    |
| `ToolsExecutorModule`       | Executes registered tools using the `ToolExecutor` interface          |
| `CodeGeneratorExecutor`     | Executes and instantiates code snippets using `CodeGenerators`        |
| `P2PExecutorModule`         | Delegates execution to another agent using `P2PManager`               |
| `DSLWorkflowExecutorModule` | Runs named DSL workflows using `DSLWorkflowsManager`                  |
| `LLMModule`                 | Invokes LLM-based execution using the `KnownLLMs` registry            |
| `DynamicModuleLoader`       | Dynamically compiles and runs custom Python code at runtime           |

You must initialize these executors with the correct dependencies (e.g., tool manager, DSL manager, etc.) before using them in any `DAGActionExecutor` or `SubGraphExecutor`.

---

### ## Executor Modules

Executor modules are responsible for handling the actual execution logic for different `execution_type` values defined in each `PlannerTask` or subgraph task. Each module wraps a specific backend or interface and provides a standardized way to:

* **Validate task readiness** (`check_execute`)
* **Execute the task** (`execute_module`)

Each executor must be initialized with its respective manager or registry (e.g., `ToolExecutor`, `DSLWorkflowsManager`, `P2PManager`, etc.).

---

### 1. `ToolsExecutorModule`

Executes registered tools.

```python
class ToolsExecutorModule:
    def __init__(self, tool_executor: ToolExecutor)
```

| Method                                   | Description                                          |
| ---------------------------------------- | ---------------------------------------------------- |
| `check_execute(graph_node, input_data)`  | Verifies that the tool is available and ready to run |
| `execute_module(graph_node, input_data)` | Runs the tool with merged parameters and input       |

**Execution Type:** `"tool_call"`

---

### 2. `CodeGeneratorExecutor`

Handles task execution using dynamic code generators.

```python
class CodeGeneratorExecutor:
    def __init__(self, code_generators: CodeGenerators)
```

| Method                                   | Description                                             |
| ---------------------------------------- | ------------------------------------------------------- |
| `check_execute(graph_node, input_data)`  | Estimates whether the generator can fulfill the request |
| `execute_module(graph_node, input_data)` | Generates and executes a callable function with input   |

**Execution Type:** `"codegen_call"`

---

### 3.`P2PExecutorModule`

Delegates execution to another agent using peer-to-peer communication.

```python
class P2PExecutorModule:
    def __init__(self, p2p_manager: P2PManager)
```

| Method                                    | Description                                      |
| ----------------------------------------- | ------------------------------------------------ |
| `check_execute(graph_node, command_data)` | Estimates if the agent can fulfill the request   |
| `execute_module(graph_node, input_data)`  | Sends a request and waits for a response via P2P |

**Execution Type:** `"agent_call"`

---

### ### 4. `DSLWorkflowExecutorModule`

Executes pre-registered DSL workflows.

```python
class DSLWorkflowExecutorModule:
    def __init__(self, dsl_workflow_manager: DSLWorkflowsManager)
```

| Method                                                  | Description                                  |
| ------------------------------------------------------- | -------------------------------------------- |
| `check_execute(graph_node, input_data)`                 | Validates if the workflow exists and can run |
| `execute_module(graph_node, input_data, output_module)` | Executes the workflow using a DSL runtime    |

**Execution Type:** `"dsl_workflow"`

---

### 5. `LLMModule`

Executes tasks by invoking a known LLM.

```python
class LLMModule:
    def __init__(self, known_llms: KnownLLMs)
```

| Method                                   | Description                                               |
| ---------------------------------------- | --------------------------------------------------------- |
| `check_execute(graph_node, input_data)`  | Estimates LLM cost or feasibility                         |
| `execute_module(graph_node, input_data)` | Runs LLM inference with session and frame pointer context |

**Execution Type:** `"llm_call"`

---

### ### 6. `DynamicModuleLoader`

Dynamically loads and runs arbitrary Python modules (advanced use case).

```python
class DynamicModuleLoader:
    def __init__(self, module_name: str, code: str)
```

| Method                    | Description                                      |
| ------------------------- | ------------------------------------------------ |
| `load_module()`           | Compiles and loads the module from source code   |
| `get_function(func_name)` | Returns a function handle from the loaded module |

---

### 7. `VALID_EXECUTION_TYPES`

A predefined set of allowed execution types, validated during DAG validation:

```python
VALID_EXECUTION_TYPES = {
  "tool_call", "dsl_workflow", "agent_call",
  "llm_call", "codegen_call", "system_call", "l2_call"
}
```

---

Understood. Here's the corrected and complete section without emojis or informal tone.

---

## DAG Execution

### Overview

DAG Execution in `agents_sdk.executor` is responsible for interpreting and executing a dependency-resolved task graph (`PlannerTask` nodes) that was generated by the Stage 1 planner. Each node in the DAG represents a discrete unit of work and is executed based on its dependencies and designated `execution_type`.

Execution is orchestrated by the `DAGActionExecutor`, which performs validation, resolves dependencies, and coordinates the flow of execution using various executor modules and persistence layers.

---

### Graph Validation and Integrity Checks

Before executing any task, the DAG is validated by the `DAGManager` to ensure structural integrity and correctness.

#### 1. Cycle Detection

The DAG must be acyclic. The `is_acyclic()` method implements a form of topological sorting (using in-degrees) to ensure that no cycles exist in the task graph. A cycle indicates an invalid task plan and raises a `ValueError`.

#### 2. Connectivity Check

The `is_fully_connected()` method ensures that all tasks are part of a single connected component. Disconnected or unreachable tasks are considered an error and result in execution halting with a validation failure.

#### 3. Execution Type Validation

Each task's `execution_type` is checked against the allowed set:

```python
VALID_EXECUTION_TYPES = {
  "tool_call", "dsl_workflow", "agent_call",
  "llm_call", "codegen_call", "system_call", "l2_call"
}
```

If a task specifies an unrecognized execution type, the DAG is rejected.

---

### Task Execution Routing

During execution, each task is dispatched to the appropriate executor module based on its `execution_type`. The executor is responsible for validating the inputs and performing the actual computation or delegation.

| Execution Type | Executor Module                 | Responsibility                                                          |
| -------------- | ------------------------------- | ----------------------------------------------------------------------- |
| `tool_call`    | `ToolsExecutorModule`           | Executes a registered tool via `ToolExecutor`                           |
| `dsl_workflow` | `DSLWorkflowExecutorModule`     | Runs a predefined DSL workflow using `DSLWorkflowsManager`              |
| `agent_call`   | `P2PExecutorModule`             | Sends the task to a remote agent using `P2PManager`                     |
| `llm_call`     | `LLMModule`                     | Performs LLM inference using `KnownLLMs`                                |
| `codegen_call` | `CodeGeneratorExecutor`         | Dynamically generates and runs code using `CodeGenerators`              |
| `l2_call`      | `DAGActionExecutor` (recursive) | Invokes a nested DAG execution using a new `DAGActionExecutor` instance |
| `system_call`  | *(Reserved for future use)*     | System-specific logic, currently unimplemented                          |

---

### Persistence and State Updates

To ensure robustness, every change in task execution state is saved persistently using MongoDB-backed manager classes:

| Manager         | Class             | Responsibility                                                   |
| --------------- | ----------------- | ---------------------------------------------------------------- |
| Task Manager    | `TasksManager`    | Handles top-level task metadata, final outputs, and status       |
| Subtask Manager | `SubTasksManager` | Tracks individual DAG nodes, their execution status, and outputs |

#### Workflow:

1. **Initial Save**

   * On initialization, `DAGActionExecutor` saves the `TaskData` object to `TasksManager`.
   * Each `PlannerTask` node is individually stored via `SubTasksManager`.

2. **Execution Phase**

   * When a task is about to execute, its status is updated to `"in_progress"`.
   * If a dependency is missing or execution fails, the status is marked `"failed"` and an error message is recorded.
   * On successful execution, the task's output is saved and status is marked `"completed"`.

3. **Finalization**

   * Once all tasks complete, `TasksManager` is updated with the full output dictionary.
   * If any task fails fatally, the entire DAG is marked as `"failed"`.

---

## NodeExecutorProcessPool

### Overview

`NodeExecutorProcessPool` provides a **lightweight task execution pool using multiprocessing**. It allows DAG tasks to be executed concurrently in **separate processes**, with an upper bound on the number of concurrent workers.

This module is used by `DAGActionExecutor` and `SubGraphExecutor` to offload the actual task execution, enabling parallelism and process-level isolation.

It supports:

* **Bounded concurrency** (`max_processes`)
* **Task submission with prioritization**
* **Result propagation via queue**
* **Basic fault handling**

---

### Initialization

```python
pool = NodeExecutorProcessPool(max_processes: int)
```

| Parameter       | Type  | Description                                     |
| --------------- | ----- | ----------------------------------------------- |
| `max_processes` | `int` | Maximum number of concurrent processes to spawn |

---

### Methods

#### `submit_task(priority: int, task)`

Adds a new task to the priority queue. The task must implement an `execute_module(input_data)` method.

Internally, this method:

* Enqueues the task and its data
* Tries to spawn a new process if the number of active processes is below `max_processes`

> Note: In the current code, the interface expects both a task and input data but only unpacks `task` in `submit_task`. This should be carefully matched in usage or fixed.

#### `_try_execute_task()`

Checks if a new task can be launched. If yes:

* Dequeues the task from the queue
* Spawns a new process
* Executes the task in that process
* Waits for the process to join (blocking, sequential)

> Current implementation joins immediately, making it synchronous in effect. For true parallelism, `process.join()` should be decoupled from submission.

#### `_execute_task(task, input_data)`

Invoked inside the child process. It:

* Calls `task.execute_module(input_data)`
* Puts the result into the consumer queue
* Catches and logs any error, sending a failure response to the consumer queue

#### `get_result()`

Returns the next available result from the consumer queue. This is a **blocking call** and should be used by the orchestrator to collect results after tasks are dispatched.

---

### Usage Example

```python
pool = NodeExecutorProcessPool(max_processes=2)

# Define a mock task class with execute_module
class MyMockTask:
    def __init__(self, task_id):
        self.task_id = task_id

    def execute_module(self, input_data):
        return {"task_id": self.task_id, "result": input_data["value"] * 2}

task = MyMockTask("task_1")
pool.submit_task(priority=0, task=(task, {"value": 5}))

result = pool.get_result()
print("Result:", result)
```

---

## DAGManager Methods

The `DAGManager` encapsulates logic for loading, validating, and navigating the DAG of `PlannerTask` instances. It is the primary interface for checking graph structure and retrieving executable nodes.

### Initialization

```python
dag_manager = DAGManager(task_data: Dict)
```

Where `task_data` is a dictionary that conforms to the `TaskData` schema.

---

### Method Reference

| Method                 | Signature                  | Description                                                                                                                               |
| ---------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `validate_graph()`     | `-> None`                  | Validates the entire task graph. Checks for cycles, disconnected components, and invalid execution types. Raises `ValueError` on failure. |
| `is_acyclic()`         | `-> bool`                  | Checks whether the DAG is acyclic using in-degree tracking (topological sort). Returns `True` if valid.                                   |
| `is_fully_connected()` | `-> bool`                  | Ensures all tasks are reachable from the starting node. Returns `True` if all tasks form a connected component.                           |
| `next_task()`          | `-> Optional[PlannerTask]` | Returns the next task that is ready to execute (i.e., all its dependencies are completed). If none are ready, returns `None`.             |
| `task_data`            | `TaskData`                 | The parsed and structured representation of the full task plan.                                                                           |
| `task_graph`           | `Dict[str, PlannerTask]`   | Mapping of `task_id` to `PlannerTask` objects for easy access.                                                                            |
| `completed_tasks`      | `Set[str]`                 | Internal tracking of task IDs that are marked as completed.                                                                               |

---

### Execution Loop (Example)

```python
dag_manager.validate_graph()

while True:
    task = dag_manager.next_task()
    if not task:
        break

    # Resolve input data
    input_data = resolve_inputs(task)

    # Dispatch to appropriate executor
    result = dispatch(task.execution_type, input_data)

    # Update state
    dag_manager.completed_tasks.add(task.task_id)
    save_result(task.task_id, result)
```

This pattern is used internally by `DAGActionExecutor` and forms the backbone of dependency-respecting task execution.

---

## DAGActionExecutor

### Overview

`DAGActionExecutor` is the primary orchestrator class that **executes a full DAG of planned tasks** generated during Stage 1. It utilizes the `DAGManager` to traverse the DAG, validates dependencies, and dispatches each task to the appropriate executor module.

Each task is executed based on its `execution_type`, and its outputs are:

* Persisted via `SubTasksManager`
* Used as input for downstream tasks
* Aggregated into a final result for the full DAG, stored in `TasksManager`

This class ensures that:

* Tasks are only executed when all dependencies are satisfied
* Status and output of each task is persisted
* Failures are captured and stored, halting execution cleanly

---

### Initialization

```python
executor = DAGActionExecutor(
    task_id: str,
    task_plan: TaskData,
    tasks_manager: TasksManager,
    subtasks_manager: SubTasksManager,
    tool_executor: ToolsExecutorModule,
    dsl_executor: DSLWorkflowExecutorModule,
    agent_executor: P2PExecutorModule,
    llm_executor: LLMModule,
    codegen_executor: CodeGeneratorExecutor,
    l2_executor: DAGActionExecutor | None,
    pool: NodeExecutorProcessPool
)
```

| Parameter          | Description                                          |
| ------------------ | ---------------------------------------------------- |
| `task_id`          | The root task ID of the DAG                          |
| `task_plan`        | The `TaskData` object representing the full plan     |
| `tasks_manager`    | MongoDB-backed manager to persist the top-level task |
| `subtasks_manager` | Manager to persist and update subtasks               |
| `tool_executor`    | Handles tool-based tasks                             |
| `dsl_executor`     | Executes named DSL workflows                         |
| `agent_executor`   | Routes tasks to remote agents                        |
| `llm_executor`     | Interfaces with language models                      |
| `codegen_executor` | Dynamically generates and executes functions         |
| `l2_executor`      | Optional recursive executor for nested DAGs          |
| `pool`             | Multiprocessing pool to run tasks concurrently       |

---

### Methods

#### `initialize_tasks_in_db()`

* Saves the root task (if not already stored)
* Iterates over all subtasks and stores them if they don’t already exist
* Ensures the DAG state is persisted before any execution begins

#### `execute(input_data: Dict[str, Any])`

Executes the DAG from the root using the following logic:

1. Initializes task statuses to `"in_progress"`

2. Iterates over tasks in topological order

3. Waits for dependencies to be completed

4. Dispatches execution based on `execution_type`:

   * `"tool_call"` → `tool_executor.execute_module(...)`
   * `"dsl_workflow"` → `dsl_executor.execute_module(...)`
   * `"agent_call"` → `agent_executor.execute_module(...)`
   * `"llm_call"` → `llm_executor.execute_module(...)`
   * `"codegen_call"` → `codegen_executor.execute_module(...)`
   * `"l2_call"` → Uses `l2_executor` to recursively execute a sub-DAG

5. On success:

   * Updates task status to `"completed"`
   * Stores output in `SubTasksManager`
   * Aggregates it for use in dependent tasks

6. On failure:

   * Marks the task as `"failed"`
   * Stores the error in the subtask
   * Halts execution and marks DAG as `"failed"` in `TasksManager`

7. On successful completion:

   * Aggregates all task outputs
   * Stores the final output in `TasksManager` with `"completed"` status

---

### Execution Flow

```python
executor.initialize_tasks_in_db()
executor.execute({
    "user_query": "Summarize the news",
    "session_id": "session-123"
})
```

Internally:

* Inputs are merged with each task's parameters
* Each task's dependencies are checked
* Task is dispatched via the appropriate module
* Outputs are chained as inputs to downstream tasks

---

### Persistence Logic

| Task Level               | Manager           | Actions                                                                   |
| ------------------------ | ----------------- | ------------------------------------------------------------------------- |
| Root Task (`TaskData`)   | `TasksManager`    | Stored once at start; updated on completion                               |
| Subtasks (`PlannerTask`) | `SubTasksManager` | Each task is updated with status: `in_progress`, `completed`, or `failed` |

---

### Error Handling

* Any failure during execution halts the DAG
* The failed task is marked with an `error` field
* Final status is set to `"failed"` in the root task
* All changes are persisted to allow for monitoring or retries

---

### Example

```python
# Assuming new_workflow_executor returns DAGManager and DAGActionExecutor
dag_manager, executor = new_workflow_executor(task_data)

dag_manager.validate_graph()

executor.execute({
    "session_id": "abc-123",
    "query": "Extract keywords from paragraph"
})
```

---

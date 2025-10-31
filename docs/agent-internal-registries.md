# Agent internal registries

## DSL Manager

### Introduction

The **DSL Manager** provides a comprehensive system for managing and executing DSL-based workflows, enabling task execution, human interaction, and integration with LLM-based planners.

The key components include:

* `DSLWorkflowsManager`: A registry and executor of DSL workflows.
* `DSLPlanner`: A human-readable and LLM-understandable schema and task formatter.
* `Planner`: A high-level intelligent planner that interfaces with LLMs to choose the best DSL or agent/tool given a goal.
* `HumanInteractionClient` and `MessageResponseWaiter`: Tools for interacting with humans over NATS and collecting feedback.

---

### Usage

You can import the DSL manager utilities as:

```python
from agent_sdk.utils.dsl_manager import (
    DSLWorkflowsManager,
    DSLPlanner,
    HumanInteractionClient
)

from agent_sdk.utils.planner import Planner  # For LLM-based planning
```

---

### Functionalities

---

#### DSLWorkflowsManager

Provides registration, execution, and management for DSL workflows.

**Example**:

```python
manager = DSLWorkflowsManager("http://dsl-registry-service")

manager.register_new_dsl_workflow("add_workflow", "dsl_id_123", extras={"x": 10})

output = manager.execute("add_workflow", {"x": 5}, "output_module")

manager.unregister_dsl_workflow("add_workflow")
```

**Available Methods**:

| Method                                              | Description                    |
| --------------------------------------------------- | ------------------------------ |
| `register_new_dsl_workflow(name, workflow_id, ...)` | Register a DSL workflow        |
| `unregister_dsl_workflow(name)`                     | Remove a DSL workflow          |
| `execute(name, input_data, output_module)`          | Execute a registered DSL       |
| `deploy(name)`                                      | Load modules for a workflow    |
| `check_execute(name)`                               | Check if the DSL is executable |
| `execute_command(name, command_name, data)`         | Execute a named command        |
| `get_workflow(name)`                                | Get DSL executor object        |
| `list()`                                            | List all registered DSLs       |
| `get_searchable_representation()`                   | Get metadata used in planners  |

---

### DSL Planner

The `DSLPlanner` class is designed to convert DSL schemas and task definitions into **LLM-parsable and human-readable formats**, helping LLMs or users decide which DSL is most suitable for a task.

**Typical Usage**:

```python
planner = DSLPlanner(dsl_workflows_manager=manager)
planner.prepare_dsl_descriptions()
planner.add_task_description("Add two numbers.")
planner.add_input_conversion({"x": 5})
print(planner.get_full_description())
```

**Purpose**:

* Generates a complete description of available DSLs.
* Explains schema details.
* Helps LLMs select an appropriate DSL from a set of options based on the given task.

---

### Planner (LLM-integrated DSL Selector)

The `Planner` class integrates deeper into the system by **communicating with an LLM** via a behavior controller and combining DSL metadata, agent information, tools/functions, and user-defined descriptions to create actionable plans.

#### Core Responsibilities

| Functionality                     | Description                                             |
| --------------------------------- | ------------------------------------------------------- |
| `prepare_job_data()`              | Adds job goal, objectives, and steerability info        |
| `prepare_resources_description()` | Adds agent and tool descriptions                        |
| `add_task_description()`          | Adds plain task description                             |
| `generate_final_input()`          | Builds final prompt for LLM                             |
| `create_plan()`                   | Submits the full input to the behavior controller (LLM) |

#### Example Usage

```python
planner = Planner(behavior_controller_url, known_subjects, tools_functions_registry)

planner.set_custom_description("project_type", "This is an NLP project")

planner.generate_final_input(
    job_goal={"intent": "summarization"},
    job_objectives={"accuracy": "high"},
    job_steerability_data={"style": "concise"},
    task_description="Summarize customer reviews"
)

plan_response = planner.create_plan("Summarize customer reviews")
```

#### Key Features

* **LLM-Readable Prompt Construction**: Combines job metadata + DSLs + agents + tools + extras into a rich description.
* **LLM Execution**: Uses a `TaskProcessorClient` to invoke a model with the prompt and retrieve plan suggestions or DSL choices.
* **Custom Hooks**: Allows custom formatting or filtering via `set_custom_job_transformer`.

---

Certainly. Below is a **realistic example** added to the documentation that simulates how you would use the `DSLWorkflowsManager`, `DSLPlanner`, and `Planner` to choose the right DSL for an intelligent task such as *"Extract key insights from a customer review and summarize them."*

---

### Realistic Example: Intelligent Task Planning and DSL Selection

#### Job Description

**Goal**: Extract actionable insights and generate a human-readable summary from raw customer feedback.

#### 🛠 Available DSLs in the system:

| DSL ID                   | Name               | Description                                                                          |
| ------------------------ | ------------------ | ------------------------------------------------------------------------------------ |
| `dsl_sentiment_analysis` | Sentiment Analyzer | Identifies customer sentiment and classifies it into positive, negative, or neutral. |
| `dsl_keyword_extractor`  | Keyword Extractor  | Extracts key terms and themes from text.                                             |
| `dsl_summarizer`         | Text Summarizer    | Generates concise summaries of long passages of text.                                |

---

#### Step 1: Register DSLs

```python
manager = DSLWorkflowsManager(dsl_workflow_uri="http://dsl-registry-service")

manager.register_new_dsl_workflow("sentiment", "dsl_sentiment_analysis")
manager.register_new_dsl_workflow("keywords", "dsl_keyword_extractor")
manager.register_new_dsl_workflow("summarizer", "dsl_summarizer")
```

---

#### Step 2: Create the DSL Planner Prompt (LLM-understandable)

```python
dsl_planner = DSLPlanner(manager)
dsl_planner.prepare_dsl_descriptions()

# Add task description
dsl_planner.add_task_description("Extract insights and generate summary from customer feedback.")

# Add example input
dsl_planner.add_input_conversion({
    "review": "The phone's battery life is terrible, but the screen is excellent and the camera is sharp."
})

print(dsl_planner.get_full_description())
```

This description can now be sent to an LLM to help select the best DSLs. For instance:

* First run `dsl_sentiment_analysis`
* Then extract keywords using `dsl_keyword_extractor`
* Finally summarize using `dsl_summarizer`

---

#### Step 3: Use the LLM-integrated Planner to Automate DSL Selection and Planning

```python
planner = Planner(
    behavior_controller_url="http://behavior-controller",
    known_subjects=known_subjects,
    tools_functions_registry=tools_registry
)

planner.generate_final_input(
    job_goal={"objective": "insight summarization"},
    job_objectives={"clarity": "high", "actionability": "yes"},
    job_steerability_data={"tone": "professional", "length": "short"},
    task_description="Extract key insights and summarize from customer review."
)

# Send to LLM to get plan
plan = planner.create_plan("Extract key insights and summarize from customer review.")
```

#### Example `plan` Output from LLM

```json
{
  "selected_dsls": ["dsl_sentiment_analysis", "dsl_keyword_extractor", "dsl_summarizer"],
  "execution_order": ["sentiment", "keywords", "summarizer"],
  "flow": [
    {
      "dsl": "dsl_sentiment_analysis",
      "input": {"review": "<customer_feedback>"}
    },
    {
      "dsl": "dsl_keyword_extractor",
      "input": {"review": "<customer_feedback>"}
    },
    {
      "dsl": "dsl_summarizer",
      "input": {
        "insights": "<output_from_previous_steps>"
      }
    }
  ]
}
```

---

#### Step 4: Execute the Planned DSLs

You can now execute each DSL step-by-step using `DSLWorkflowsManager.execute()` or in a chained workflow.

```python
feedback = {
    "review": "The phone's battery life is terrible, but the screen is excellent and the camera is sharp."
}

sentiment = manager.execute("sentiment", feedback, "output")
keywords = manager.execute("keywords", feedback, "output")

summary_input = {
    "insights": {
        "sentiment": sentiment,
        "keywords": keywords
    }
}

summary = manager.execute("summarizer", summary_input, "output")
```
---

Absolutely! Below is the structured documentation for your **Functions and Tools** system:

---

## Functions and Tools

### Introduction

The **Functions and Tools** subsystem provides a unified framework for managing, executing, and discovering reusable components like tools and functions. These components may either be:

* **Remote tools/functions** — discovered and managed via API services.
* **Local tools/functions** — custom-defined and executed directly in the system.

This subsystem supports:

* Dynamic registration and execution of both local and remote assets.
* LLM-driven selection via searchable metadata (`get_searchable_representation()`).
* Flexible extension through custom tool executors using an abstract interface.

It is designed to be **LLM-compatible**, enabling autonomous agents or planners to search and select appropriate tools or functions based on natural language goals and task metadata.

---

### Tool Execution Architecture

| Component                    | Role                                                        |
| ---------------------------- | ----------------------------------------------------------- |
| `ToolExecutor`               | Abstract base class for implementing custom tool logic.     |
| `LocalCustomTool`            | Wrapper that invokes the associated `ToolExecutor`.         |
| `ToolsFunctionsRegistry`     | Registry and execution engine for both tools and functions. |
| `ToolsRegistrySDK`           | REST client for managing tools via external APIs.           |
| `FunctionsRegistryDB`        | Data access interface for function metadata.                |
| `PredefinedToolExecutor`     | Executes remote tools.                                      |
| `PredefinedFunctionExecutor` | Executes remote functions.                                  |

---

### ToolExecutor Interface

To define a custom tool, extend the abstract `ToolExecutor` class:

```python
class MyCustomTool(ToolExecutor):
    def execute(self, input_data: dict) -> dict:
        # Your tool logic here
        pass

    def validate_inputs(self, input_data: dict) -> bool:
        # Validation logic
        return True

    def check_execute(self):
        # Optional health check logic
        pass
```

Register it using:

```python
registry.add_local_tool(tool_object, MyCustomTool, tool_data)
```

---

### ToolsFunctionsRegistry

#### Initialization

```python
registry = ToolsFunctionsRegistry()
```

#### Add Remote Tool or Function

```python
registry.add_tool("tool_id")
registry.add_function("function_id")
```

#### Add Local Tool or Function

```python
registry.add_local_tool(tool_obj, MyToolExecutorClass, tool_data)
registry.add_local_function(function_obj)
```

#### Remove

```python
registry.remove_tool("tool_id")
registry.remove_function("function_id")
```

#### Execute Tool or Function

```python
result = registry.execute_tool("tool_id", input_data)
```

This automatically routes:

* Remote tool ➝ `PredefinedToolExecutor`
* Local tool ➝ `ToolExecutor` via `LocalCustomTool`
* Remote function ➝ `PredefinedFunctionExecutor`

---

### Searchable Representation (for LLM)

Use the following to extract metadata for LLM-based selection or semantic search:

```python
searchable = registry.get_searchable_representation()
```

Each entry includes:

| Field                            | Description                                  |
| -------------------------------- | -------------------------------------------- |
| `id`                             | Unique ID (tool or function)                 |
| `type`                           | `"tool"` or `"function"`                     |
| `tags`                           | Keyword tags for filtering                   |
| `description`                    | Textual description                          |
| `sub_type`                       | Subcategory of tool/function                 |
| `runtime_type` / `protocol_type` | Execution backend identifier                 |
| `schema`                         | Input/output API schema (OpenAPI-style JSON) |

This metadata enables systems like `Planner` or `DSLPlanner` to rank, filter, or auto-select appropriate tools.

---

### REST-backed Tool Management

You can manage remote tools using the `ToolsRegistrySDK`.

```python
sdk = ToolsRegistrySDK(base_url="http://tools-service")
```

| Method                          | Purpose                               |
| ------------------------------- | ------------------------------------- |
| `get_tool_by_id(tool_id)`       | Fetch a tool's metadata               |
| `create_tool(tool_data)`        | Register a new tool                   |
| `update_tool(tool_id, updates)` | Modify an existing tool               |
| `delete_tool(tool_id)`          | Remove a tool                         |
| `execute_query(query)`          | Search via freeform query             |
| `search_by_tags(tags)`          | Filter by tags                        |
| `search_advanced(...)`          | Advanced search using multiple fields |

---

### Example Usage

#### Register and Execute Local Tool

```python
class MyTool(ToolExecutor):
    def execute(self, input_data):
        return {"output": input_data["x"] * 2}

    def validate_inputs(self, input_data):
        return "x" in input_data

    def check_execute(self):
        pass

my_tool = Tool(tool_id="local_multiplier", ...)
registry.add_local_tool(my_tool, MyTool, {"version": "1.0"})

# Execute it
output = registry.execute_tool("local_multiplier", {"x": 10})
```

#### LLM Discoverability Example

```python
for entry in registry.get_searchable_representation():
    print(f"{entry['id']} - {entry['description']}")
```

Output:

```
local_multiplier - Multiplies input x by 2
```

This output can be fed into a planning LLM or used in semantic ranking to choose which tool to invoke.

---

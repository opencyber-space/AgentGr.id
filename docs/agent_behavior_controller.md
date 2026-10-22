# Behavior Controller

## Introduction

The **Behavior Controller** module is a two-phase behavior orchestration system designed to generate, process, and evaluate structured tasks using Large Language Models (LLMs). It serves as the intelligent backend for any application that requires:

* Automated planning of tasks (e.g., multi-step execution flows)
* Decision-making based on prior context and structured rules
* Integration of internal (AIOS) and external (OpenAI) inference systems
* History-aware behavior execution using FrameDB pointers or local context

The system supports **two distinct phases** in task reasoning:

1. **Phase 1: Behavior Planning**

   * Generates a structured plan containing multiple tasks.
   * Each task includes attributes like execution type, dependencies, and configuration.

2. **Phase 2: Behavior Execution**

   * From the Phase 1 plan, selects the most appropriate action to execute next.
   * Provides a `uid` referencing the chosen executable behavior.

### Key Features

| Feature                        | Description                                                            |
| ------------------------------ | ---------------------------------------------------------------------- |
| **LLM Agnostic**               | Supports both AIOS-based and OpenAI-based inference                    |
| **Structured Output**          | All outputs follow a strict JSON format based on provided templates    |
| **Historical Context Support** | Retrieves and reuses data from past executions                         |
| **Queue-Based Execution**      | Tasks are handled asynchronously using background workers              |
| **Full Lifecycle Management**  | Tracks task status, logs metadata, and stores results for traceability |

---

## Architecture

![Behavior-controller](./images/behavior-controller.png)


The **Behavior Controller** is structured as a modular, two-phase reasoning pipeline designed to generate and select behavior plans using LLMs, DSL logic, and contextual memory. Each component plays a distinct role in orchestrating, enriching, executing, and finalizing behavior tasks.

### Component Overview

| **Component**                  | **Description**                                                                                                                                                                                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Behavior Selection API**     | The external entry point for the controller. Accepts POST requests for Phase 1 and Phase 2 via `/process-phase-1-task` and `/process-phase-2-task`. It initiates the task lifecycle, prepares metadata, and dispatches the request to the internal controller.                        |
| **Previous Results Populator** | Before planning begins, this module performs similarity-based or goal-matching retrieval from historical results. It enriches the current input with prior knowledge (context JSON or FrameDB pointers), enabling memory-aware behavior planning.                                     |
| **Stage 1 Executor**           | Executes Phase 1 logic using the `Phase1Executor`. It applies a prompt template and invokes either the internal `AIOSLLM` (gRPC) or external `OpenAILLM` (HTTP) to generate a structured plan—a list of behavior candidates with metadata like `dsl`, `tool_id`, or `execution_type`. |
| **Stage 1 Results Collector**  | Receives the generated candidate plan from Stage 1 and stores it as a `PreviousResults` entry in the database. This makes the candidate pool available to Phase 2 and also reusable for future queries.                                                                               |
| **Stage 2 Executor**           | Runs Phase 2 logic using the `Phase2Executor`. Given a list of behavior candidates, it applies a second LLM prompt to select the most suitable `uid` representing the best next action.                                                                                               |
| **Stage 2 Results Collector**  | Captures and persists the selected behavior `uid` in the `PreviousResultsPhase2` table. This final result is returned to the client or passed downstream.                                                                                                                             |
| **Feedback Executor**          | Triggered if Stage 2 fails to select a valid action. It adapts or rewrites the input (e.g., modifying the LLM prompt or removing invalid candidates) and re-invokes Stage 1 to regenerate a new behavior plan.                                                                        |
| **Result Notifier**            | Responsible for delivering the final outcome to downstream consumers. This could involve sending it to another system, pushing a status update, or logging the behavior decision.                                                                                                     |
| **FrameDB Client**             | Resolves `framedb_ptr` references by fetching the actual context data from FrameDB (a distributed Redis-based store). Enables large historical context blocks to be dereferenced without storing them inline in the SQL database.                                                     |


---

## Task Lifecycle

### Key Architectural Components

1. **Flask API Layer**

   * Receives external task requests via HTTP POST endpoints.
   * Provides `/process-phase-1-task` and `/process-phase-2-task`.
   * Passes incoming data to the `BehaviorController` for handling.

2. **Behavior Controller**

   * Acts as the central orchestrator.
   * Validates and persists incoming tasks.
   * Submits tasks to the background processor.
   * Waits for result and updates task status.

3. **TaskProcessor**

   * Asynchronous background engine using `ThreadPoolExecutor`.
   * Continuously monitors a queue for incoming tasks.
   * Executes task logic (e.g., invoking LLM).
   * Pushes results to an output queue.

4. **Phase Executors**

   * `Phase1Executor`: Generates structured plans from inputs.
   * `Phase2Executor`: Selects the most appropriate action.
   * Both use configurable templates and can call either:

     * `AIOSLLM` (internal gRPC-based LLM)
     * `OpenAILLM` (OpenAI API)

5. **Database Layer**

   * SQLAlchemy models persist:

     * Task metadata (Phase1Data / Phase2Data)
     * Output results (PreviousResults / PreviousResultsPhase2)
   * CRUD interfaces support creation, updates, queries.

6. **Results Handler**

   * Maintains historical execution results.
   * Supports fetching latest results for reuse (e.g., context construction).
   * Integrates with FrameDB for dereferencing `framedb_ptr`.

7. **FrameDB Client**

   * Resolves and fetches contextual data from a distributed Redis setup.
   * Used when results store references to prior frame-based data.

---

## Task Lifecycle

### Phase 1 (Behavior Planning)

1. **Request Received**

   * User sends a POST request to `/process-phase-1-task` with `search_id` and `phase_1_data`.

2. **Task Initialized**

   * A `Phase1TaskData` object is created.
   * Stored in the database with status `pending`.

3. **Submitted to Processor**

   * Task is queued via `TaskProcessor.submit_task`.

4. **Execution**

   * A worker thread picks the task.
   * Prepares input using latest Phase 1 results (context-aware).
   * Calls `Phase1Executor.run_task(...)` using LLM backend.
   * Structured plan is returned.

5. **Result Stored**

   * Result is persisted.
   * Task status updated to `complete` or `failed`.

---

### Phase 2 (Behavior Selection)

1. **Request Received**

   * User sends a POST request to `/process-phase-2-task` with `search_id` and `phase_2_data`.

2. **Task Initialized**

   * A `Phase2TaskData` object is created and stored.

3. **Submitted to Processor**

   * Sent to the background queue.

4. **Execution**

   * Executor fetches task.
   * Calls `Phase2Executor.initialize_llm(...)` to select next action.

5. **Result Stored**

   * `uid` of selected action stored as `PreviousResultsPhase2`.
   * Status updated accordingly.

---

## Schema

This section explains the core SQLAlchemy models used in the Behavior Controller system. These models define how tasks and results are stored in a relational database.

We will cover the following models:

* `Phase1Data`
* `Phase2Data`
* `PreviousResults`

---

### `Phase1Data`

#### **Model Definition**

```python
class Phase1Data(Base):
    __tablename__ = "phase_1_data"

    search_id = Column(String, primary_key=True)
    phase_1_data = Column(JSON, nullable=True)
    entry_time = Column(Integer, default=int(time.now()))
    last_update_time = Column(Integer, default=int(time.now()), onupdate=int(time.now()))
    status = Column(String, nullable=True)
    log_runtime_trace = Column(JSON, nullable=True)
    n_repititions = Column(String, nullable=True)
```

#### **Field Descriptions**

| Field Name          | Type      | Description                                                           |
| ------------------- | --------- | --------------------------------------------------------------------- |
| `search_id`         | `String`  | Unique identifier for the task (primary key).                         |
| `phase_1_data`      | `JSON`    | Raw input data for the Phase 1 behavior planning task.                |
| `entry_time`        | `Integer` | Unix timestamp representing when the task was created.                |
| `last_update_time`  | `Integer` | Unix timestamp for last status update; auto-updated.                  |
| `status`            | `String`  | Current status of the task (`pending`, `complete`, or `failed`).      |
| `log_runtime_trace` | `JSON`    | Optional structured log or debug metadata from execution.             |
| `n_repititions`     | `String`  | Indicates how many repetitions of the plan are requested or executed. |

---

### `Phase2Data`

#### **Model Definition**

```python
class Phase2Data(Base):
    __tablename__ = "phase_2_data"

    search_id = Column(String, ForeignKey("phase_1_data.search_id"), primary_key=True)
    phase_2_data = Column(JSON, nullable=True)
    entry_time = Column(Integer, default=int(time.now()))
    last_update_time = Column(Integer, default=int(time.now()), onupdate=int(time.now()))
    status = Column(String, nullable=True)
    log_runtime_trace = Column(JSON, nullable=True)
```

#### **Field Descriptions**

| Field Name          | Type      | Description                                                       |
| ------------------- | --------- | ----------------------------------------------------------------- |
| `search_id`         | `String`  | Primary key and foreign key linking to `Phase1Data.search_id`.    |
| `phase_2_data`      | `JSON`    | Input data for Phase 2 decision-making based on the Phase 1 plan. |
| `entry_time`        | `Integer` | Task creation timestamp.                                          |
| `last_update_time`  | `Integer` | Timestamp of last update (e.g., completion or failure).           |
| `status`            | `String`  | Task execution status (`pending`, `complete`, or `failed`).       |
| `log_runtime_trace` | `JSON`    | Execution trace/logs for debugging Phase 2 decisions.             |

---

### `PreviousResults`

#### **Model Definition**

```python
class PreviousResults(Base):
    __tablename__ = "previous_results"

    result_id = Column(String, primary_key=True)
    context_json_or_context_framedb_ptr = Column(JSON, nullable=True)
    derived_search_tags = Column(Text, nullable=True)
    goal_data = Column(JSON, nullable=True)
    candidate_pool_behavior_dsls = Column(JSON, nullable=True)
    action_type = Column(String, nullable=True)
    action_sub_type = Column(String, nullable=True)
```

#### **Field Descriptions**

| Field Name                            | Type     | Description                                                                                        |
| ------------------------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| `result_id`                           | `String` | Unique identifier for the stored result.                                                           |
| `context_json_or_context_framedb_ptr` | `JSON`   | Stores either the actual context (as JSON) or a FrameDB pointer (with dereferencing instructions). |
| `derived_search_tags`                 | `Text`   | Tags derived from the search query or results, used for filtering/search.                          |
| `goal_data`                           | `JSON`   | Represents the original goal or objective metadata behind this task.                               |
| `candidate_pool_behavior_dsls`        | `JSON`   | A list or map of DSLs that were considered as possible behavior choices.                           |
| `action_type`                         | `String` | Broad category of action represented by this result (e.g., planning, routing).                     |
| `action_sub_type`                     | `String` | More specific type of action (e.g., "fetch-weather", "allocate-node").                             |

---


## Processing Lifecycle

The **Processing Lifecycle** section outlines the full path a task follows—from submission via the REST API, through background processing, LLM invocation, and result persistence. This lifecycle applies independently to both Phase 1 (behavior planning) and Phase 2 (behavior execution), although the underlying mechanisms are similar.

---

### Step 1: Task Submission via API

* A client sends a POST request to either:

  * `/process-phase-1-task` with `search_id` and `phase_1_data`
  * `/process-phase-2-task` with `search_id` and `phase_2_data`
* These requests are handled by Flask routes which extract the payload and call methods on `BehaviorController`.

---

### Step 2: Task Initialization

* The `BehaviorController` constructs an in-memory data object:

  * `Phase1TaskData` or `Phase2TaskData`, depending on the phase.
* This data is serialized using `.to_dict()` and stored in the corresponding SQLAlchemy model via the appropriate CRUD class (`Phase1DataCRUD`, `Phase2DataCRUD`).
* The task is inserted into the database with a default status of `"pending"`.

---

### Step 3: Task Submission to Processor

* The controller then submits the task to the background `TaskProcessor` using:

  ```python
  waiter = task_processor.submit_task(search_id, mode, task_data.to_dict())
  ```

* This internally creates a `Task` object containing:

  * `search_id`
  * `mode` (either `"phase1"` or `"phase2"`)
  * full input data dictionary

* The `Task` is placed into an input queue monitored by a thread.

---

### Step 4: Asynchronous Processing

* A worker thread inside the `TaskProcessor` picks up the task from the queue and executes it via:

  ```python
  result = task.execute()
  ```

* The `Task.execute()` function calls the appropriate LLM executor:

  * `Phase1Executor.run_task(...)`
  * `Phase2Executor.initialize_llm(...)`

* These executors use templates and configuration to invoke either:

  * `AIOSLLM` via gRPC
  * `OpenAILLM` via OpenAI's HTTP API

* The LLM returns a JSON-formatted result, which is parsed and returned.

---

### Step 5: Result Collection and Status Update

* The result is placed in the `output_queue`.
* The controller waits on the `TaskWaiter.get()` method to retrieve the result.
* Once the result is available:

  * It is stored if needed (e.g., via `create_phase_1_result` or `create_phase_2_result`).
  * The corresponding SQLAlchemy record is updated:

    * If successful → `status = "complete"`
    * If failed or timed out → `status = "failed"`

---

### Step 6: Historical Usage and FrameDB Support (Phase 1 only)

* During Phase 1 input preparation, the system may call:

  ```python
  get_latest_phase_1_results(history_value)
  ```

* This returns previously stored `PreviousResults`, which may contain either:

  * Raw context JSON, or
  * A `framedb_ptr` to fetch from FrameDB (via Redis).

* If a `framedb_ptr` is present:

  * `FrameDBFetchClient` resolves the pointer using routing logic.
  * Data is fetched securely from the appropriate Redis node.

* This context is embedded into the input data passed to the LLM executor, enabling memory-based reasoning.

---


## LLM Executor Interface

The Behavior Controller module uses a unified interface to interact with multiple LLM backends for executing structured behavior logic. This interface is abstracted via the `BehaviorAPI` protocol and implemented by two concrete classes:

* `AIOSLLM`: Internal inference system using gRPC (used with AIOS framework)
* `OpenAILLM`: External OpenAI models via REST API

These backends are invoked through the `Phase1Executor` and `Phase2Executor` depending on the phase of processing.

---

### BehaviorAPI Interface

Located in `generator.py`, the `BehaviorAPI` class defines the abstract behavior expected from any LLM integration.

```python
class BehaviorAPI(ABC):
    def search(self, task_description: str, descriptors: Dict[str, str]) -> str:
        pass
```

However, in practice, the interface is implemented through a more specific method called `generate(...)`, which both `AIOSLLM` and `OpenAILLM` expose directly.

---

### AIOSLLM (gRPC-based Internal Inference)

#### Purpose

Used when behavior planning or execution is routed through an internal AIOS inference block.

#### Key Characteristics

| Property       | Description                                               |
| -------------- | --------------------------------------------------------- |
| Transport      | gRPC                                                      |
| Message Format | Protobuf (`BlockInferencePacket`)                         |
| Channel        | `BlockInferenceServiceStub`                               |
| Input          | Pre-processed task description + serialized as JSON bytes |
| Output         | Inference result (string, usually JSON)                   |

#### Usage Flow

```python
llm_instance = AIOSLLM(...)
result = llm_instance.generate(task_description, descriptors)
```

The generator builds and sends a gRPC request with fields such as:

* `block_id`, `instance_id`, `session_id`, etc.
* Optional `frame_ptr` and `query_parameters`
* `data`: The actual task input in bytes

---

### OpenAILLM (OpenAI via REST)

#### Purpose

Connects to OpenAI’s public API (e.g., GPT-4, GPT-4o) for generating structured task responses.

#### Key Characteristics

| Property  | Description                                       |
| --------- | ------------------------------------------------- |
| Transport | HTTPS                                             |
| Library   | `openai` Python client                            |
| API       | `chat.completions.create`                         |
| Input     | Task description passed as a user message         |
| Output    | Extracted `message.content` from the first choice |

#### Usage Flow

```python
llm_instance = OpenAILLM(api_key="...", model="gpt-4o")
result = llm_instance.generate(task_description, descriptors)
```

The `generate` function builds a message list:

```json
[
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."}
]
```

And returns the final output string from the OpenAI response.

---

### Template Injection

Both `Phase1Executor` and `Phase2Executor` use fixed prompt templates for consistent structure. These templates are injected as part of the descriptors:

* **Phase 1** (planning template): Returns a structured JSON plan of tasks.
* **Phase 2** (decision template): Returns a single UID as the selected action.

These templates enforce consistency in outputs regardless of the backend used.

---

### Summary of Executor Responsibilities

| Executor         | Method                | Template Use  | Output Format           |
| ---------------- | --------------------- | ------------- | ----------------------- |
| `Phase1Executor` | `run_task(...)`       | Planning      | JSON with list of tasks |
| `Phase2Executor` | `initialize_llm(...)` | UID selection | JSON with `"uid"`       |

Each executor constructs the final prompt and calls `.generate(...)`, abstracting the LLM source behind a consistent interface.

---
## Result Management

The Behavior Controller maintains detailed records of task execution outputs using the `results_handler.py` module and the corresponding SQLAlchemy models. These records serve multiple purposes:

* Enable re-use of prior task context for new inferences (especially Phase 1).
* Allow traceability and auditing of task outcomes.
* Facilitate frame-based dereferencing of large context blobs using FrameDB pointers.

This section covers how results are stored, retrieved, and utilized during task execution.

---

### Phase 1 Results

Phase 1 results represent the output of behavior planning tasks. These are stored using the `PreviousResults` SQLAlchemy model and the `PreviousResultsData` dataclass.

#### Storage

```python
create_phase_1_result(result_data: PreviousResultsData)
```

* Converts the result data object to a dictionary.
* Persists it using `PreviousResultsCRUD.create(...)`.

#### Fields Stored

| Field                                 | Purpose                                  |
| ------------------------------------- | ---------------------------------------- |
| `result_id`                           | Unique identifier for the result         |
| `context_json_or_context_framedb_ptr` | Raw context or pointer to FrameDB        |
| `derived_search_tags`                 | Tags derived from task inputs or goals   |
| `goal_data`                           | Information about the intended objective |
| `candidate_pool_behavior_dsls`        | All DSLs considered for the plan         |
| `action_type` / `action_sub_type`     | Metadata to classify the behavior        |

---

### Phase 2 Results

Phase 2 results represent the selected behavior decision for a given planned task. They are stored using the `PreviousResultsPhase2` model and the `PreviousResultsPhase2Data` dataclass.

#### Storage

```python
create_phase_2_result(result_data: PreviousResultsPhase2Data)
```

* Stores the selected DSL ID (`uid`) linked to a prior result.

#### Fields Stored

| Field                      | Purpose                                        |
| -------------------------- | ---------------------------------------------- |
| `result_id`                | Links back to the corresponding Phase 1 result |
| `selected_behavior_dsl_id` | The chosen behavior/action UID for execution   |

---

### Retrieving Historical Results

Historical Phase 1 results are retrieved when preparing new task input data for LLMs. This enables context-aware processing by feeding the LLM with previous decisions or task states.

#### Retrieval

```python
get_latest_phase_1_results(limit: int)
```

* Fetches the most recent `PreviousResults` entries ordered by `result_id`.
* Returns them as `PreviousResultsData` instances.

This retrieval logic is embedded in:

```python
prepare_input_data_phase_1(task_data)
```

Which constructs an input context as:

```python
{
  "history": [context1, context2, ...],
  "task": task_data
}
```

---

### FrameDB Pointer Support

If a result contains a `framedb_ptr` (instead of raw JSON context), the system invokes:

```python
FrameDBFetchClient.fetch_data_from_framedb_ptr(framedb_ptr)
```

This allows large or remote context blocks to be efficiently referenced and resolved on demand, without storing them directly in the SQL database.

---

## REST API Documentation

The Behavior Controller exposes two REST API endpoints using Flask, designed to receive and process behavior tasks in two phases. Each endpoint accepts a structured JSON payload, triggers asynchronous processing, and returns the result.

### Base URL

```
http://<host>:8888/
```

---

### 1. **POST /process-phase-1-task**

#### **Description**

Submits a Phase 1 behavior planning task. The system processes the input, optionally augments it using prior context, invokes the LLM, and returns a structured task plan.

#### **Endpoint**

```
POST /process-phase-1-task
```

#### **Request Payload**

```json
{
  "search_id": "string",            // Unique ID for the task
  "phase_1_data": { ... }           // Task input as JSON
}
```

#### **Response Format**

```json
{
  "success": true,
  "data": {
    "status": "success",
    "processed_data": { ... }       // LLM-generated structured plan
  }
}
```

If processing fails:

```json
{
  "success": false,
  "message": "Error message"
}
```

#### **Example cURL**

```bash
curl -X POST http://localhost:8888/process-phase-1-task \
  -H "Content-Type: application/json" \
  -d '{
    "search_id": "task-123",
    "phase_1_data": {
      "input_description": "Plan a 3-step workflow to analyze traffic data."
    }
  }'
```

---

### 2. **POST /process-phase-2-task**

#### **Description**

Submits a Phase 2 behavior execution task. The system processes the plan, uses an LLM to select the best action, and returns a `uid` representing the chosen behavior.

#### **Endpoint**

```
POST /process-phase-2-task
```

#### **Request Payload**

```json
{
  "search_id": "string",            
  "phase_2_data": { ... }           
}
```

#### **Response Format**

```json
{
  "success": true,
  "data": {
    "status": "success",
    "processed_data": {
      "uid": "selected-action-id"
    }
  }
}
```

If processing fails:

```json
{
  "success": false,
  "message": "Error message"
}
```

#### **Example cURL**

```bash
curl -X POST http://localhost:8888/process-phase-2-task \
  -H "Content-Type: application/json" \
  -d '{
    "search_id": "task-123",
    "phase_2_data": {
      "planned_tasks": [
        {
          "task_id": "task_1",
          "description": "Analyze traffic by city",
          "execution_type": "tool_call",
          "tool_id": "traffic_analyzer",
          "parameters": { "city": "Mumbai" }
        }
      ]
    }
  }'
```

---

### Status Codes

| Code  | Description                                                   |
| ----- | ------------------------------------------------------------- |
| `200` | Task accepted and processed successfully                      |
| `400` | Missing required fields or invalid input                      |
| `500` | Internal server error (e.g., processing failure, LLM timeout) |

---

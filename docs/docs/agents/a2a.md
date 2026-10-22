# Agent to Agent message conversion system

## Introduction

The `MessageHandler` framework provides a robust, extensible system for validating, transforming, and managing structured communication between distributed AI subjects (e.g., agents, services, components). It enables seamless interoperability through:

* **Schema-driven input/output validation**
* **Template-aware DSL execution for data transformation**
* **Subject-aware caching and introspection**
* **Metadata-rich message type descriptions**

This system is designed to support dynamic, runtime-configurable messaging standards across diverse subjects in large-scale, modular AI systems. Each subject defines its communication patterns and supported message types using templates and DSL workflows, which are stored and accessed via a centralized subject registry.

### Core Capabilities

* **Validation**: Validates messages against subject-specific input/output templates, supporting nested schemas and field-level constraints.
* **Transformation**: Executes DSL workflows to transform messages between subjects using configurable field mappings and metadata.
* **Discovery**: Provides structured inspection of supported message types, associated metadata, and registered DSLs.
* **Caching**: Uses an in-memory cache to minimize registry queries and ensure fast local access.

Whether you are building an AI coordination network, a message routing system, or a multi-agent orchestration engine, this framework offers a unified interface to manage structured communication effectively.

---

## Schema Description

This section documents the structure and purpose of the key schemas used in the message validation and communication system.

---

### Communication Schema

The `SubjectCommunication` schema defines how a subject communicates, including the protocols it supports and the types of messages it can send or receive.

#### Data Class

```python
@dataclass
class SubjectCommunication:
    protocols: List[Dict[str, Any]]
    message_types: List[MessageType]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SubjectCommunication":
        return SubjectCommunication(
            protocols=data.get("protocols", []),
            message_types=[MessageType.from_dict(mt) for mt in data.get("message_types", [])]
        )
```

#### Field Descriptions

| Field           | Type                   | Description                                                                                                     |
| --------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------- |
| `protocols`     | `List[Dict[str, Any]]` | A list of supported communication protocols. Each dictionary may include keys like `type`, `port`, `path`, etc. |
| `message_types` | `List[MessageType]`    | A list of message types that the subject can handle, defined by the `MessageType` schema.                       |

---

### Message Type Schema

The `MessageType` schema describes a specific type of communication message, including templates for input and output validation, DSL transformation logic, and metadata.

#### Data Class

```python
@dataclass
class MessageType:
    type: str
    input_template: Dict[str, Any]
    output_template: Dict[str, Any]
    metadata: MessageTypeMetadata
    standard_fields_mapping_input: Dict[str, str]
    standard_fields_mapping_output: Dict[str, str]
    input_dsl_workflow_id: str
    output_dsl_workflow_id: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MessageType":
        return MessageType(
            type=data["type"],
            input_template=data.get("input_template", {}),
            output_template=data.get("output_template", {}),
            metadata=MessageTypeMetadata.from_dict(data.get("metadata", {})),
            standard_fields_mapping_input=data.get("standard_fields_mapping_input", {}),
            standard_fields_mapping_output=data.get("standard_fields_mapping_output", {}),
            input_dsl_workflow_id=data.get("input_dsl_workflow_id", ""),
            output_dsl_workflow_id=data.get("output_dsl_workflow_id", "")
        )
```

#### Field Descriptions

| Field                            | Type                  | Description                                                                  |
| -------------------------------- | --------------------- | ---------------------------------------------------------------------------- |
| `type`                           | `str`                 | Unique identifier for the message type.                                      |
| `input_template`                 | `Dict[str, Any]`      | A schema that defines the structure and constraints of incoming data.        |
| `output_template`                | `Dict[str, Any]`      | A schema that defines the structure and constraints of outgoing data.        |
| `metadata`                       | `MessageTypeMetadata` | Additional descriptive information such as description, usage docs, etc.     |
| `standard_fields_mapping_input`  | `Dict[str, str]`      | Mapping from standardized field names to keys in the input template.         |
| `standard_fields_mapping_output` | `Dict[str, str]`      | Mapping from standardized field names to keys in the output template.        |
| `input_dsl_workflow_id`          | `str`                 | DSL workflow ID for transforming input from external to internal structure.  |
| `output_dsl_workflow_id`         | `str`                 | DSL workflow ID for transforming output from internal to external structure. |

---

## Templates

Message templates define the expected structure and validation constraints for the input and output of a `MessageType`. These templates are used by the `MessageHandler` to verify correctness and by the DSL executor to assist in transformation.

Templates support field-level validation for types, patterns, enumerations, structure, and value constraints. The format is recursive and can express deeply nested schemas for objects and arrays.

---

### Writing a Template

Each template is a `Dict[str, Any]`, where each key represents a field name, and the corresponding value is a schema dictionary containing validation rules.

#### Supported Validation Fields

| Field         | Type      | Applicable To  | Description                                                         |
| ------------- | --------- | -------------- | ------------------------------------------------------------------- |
| `type`        | `string`  | All            | Data type: `string`, `number`, `boolean`, `array`, `object`, `any`. |
| `description` | `string`  | All            | Optional human-readable description of the field.                   |
| `pattern`     | `string`  | string         | Regular expression the string must match.                           |
| `length`      | `number`  | string         | Maximum allowed length of the string.                               |
| `choices`     | `array`   | string, number | Allowed set of values.                                              |
| `min`         | `number`  | number         | Minimum allowed numeric value.                                      |
| `max`         | `number`  | number         | Maximum allowed numeric value.                                      |
| `max_length`  | `number`  | array          | Maximum number of array elements.                                   |
| `items`       | `object`  | array          | Template for validating each item in an array.                      |
| `properties`  | `object`  | object         | Dictionary defining field schemas inside an object.                 |
| `optional`    | `boolean` | All            | Whether the field is optional (default is false).                   |

---

### Example: Agentic Template

This input template could be used by a messaging agent that receives a structured task request:

```python
input_template = {
    "task_id": {
        "type": "string",
        "description": "Unique identifier for the task",
        "pattern": "^[a-zA-Z0-9_-]{8,32}$"
    },
    "priority": {
        "type": "number",
        "description": "Priority level from 1 (low) to 10 (high)",
        "min": 1,
        "max": 10
    },
    "mode": {
        "type": "string",
        "description": "Execution mode",
        "choices": ["sync", "async", "stream"]
    },
    "parameters": {
        "type": "object",
        "description": "Parameter block for the task execution",
        "properties": {
            "temperature": {
                "type": "number",
                "min": 0.0,
                "max": 1.0
            },
            "max_tokens": {
                "type": "number",
                "max": 2048
            },
            "debug": {
                "type": "boolean"
            }
        }
    },
    "tags": {
        "type": "array",
        "description": "Optional search or routing tags",
        "items": {
            "type": "string"
        },
        "max_length": 10,
        "optional": True
    }
}
```

This template defines:

* Required scalar fields with pattern, numeric range, and enumeration
* A nested `parameters` object with its own validation rules
* An optional list of tags with a maximum length

---

## SubjectsLocalDB

`SubjectsLocalDB` provides an in-memory cache of all subject metadata and communication configurations retrieved from the subject registry. It reduces repetitive API calls by locally storing subject definitions and communication schemas.

### Class Initialization

```python
SubjectsLocalDB(db_client: SubjectDBAPIClient)
```

* `db_client`: an instance of `SubjectDBAPIClient` used to fetch subject definitions from the registry.

---

### Methods

#### `populate_cache()`

Fetches all runtime subjects from the registry and populates the internal cache.

```python
local_db.populate_cache()
```

#### `get_runtime_subject(subject_id: str) -> Optional[Subject]`

Retrieves a subject by ID from the local cache.

```python
subject = local_db.get_runtime_subject("agent-123")
```

#### `list_runtime_subjects() -> List[Subject]`

Returns a list of all cached subjects.

```python
subjects = local_db.list_runtime_subjects()
```

#### `query_runtime_subjects(query: Dict[str, Any]) -> List[Subject]`

Filters subjects based on top-level equality conditions. Supports list containment for array fields.

```python
agents = local_db.query_runtime_subjects({"subject_type": "agent"})
```

#### `get_communication_data(subject_id: str) -> Optional[SubjectCommunication]`

Parses and returns the `SubjectCommunication` object from the `subject_config["communication"]` field.

```python
comm = local_db.get_communication_data("agent-123")
```

#### `get_communications_searchable_fields(subject_id: str) -> List[Dict[str, Any]]`

Returns a list of message types and associated templates and metadata for indexing/search purposes.

```python
fields = local_db.get_communications_searchable_fields("agent-123")
```

#### `get_communications_searchable_representation(subject_id: str) -> Optional[str]`

Formats the communication metadata into a human-readable string (useful for LLMs or descriptions).

```python
summary = local_db.get_communications_searchable_representation("agent-123")
```

---

## MessageHandler

`MessageHandler` provides schema-aware validation, transformation, and DSL execution utilities for communication between subjects.

### Class Initialization

```python
MessageHandler(subject_cache: SubjectsLocalDB)
```

* `subject_cache`: an instance of `SubjectsLocalDB` with preloaded subject data.

---

### Validation Methods

#### `validate_input_source(message_type: str, data: Dict[str, Any])`

Validates `data` against the input template of the current subject (determined by `SUBJECT_ID`).

```python
handler.validate_input_source("chat", {"message": "Hello"})
```

#### `validate_output_source(message_type: str, data: Dict[str, Any])`

Validates `data` against the output template of the current subject.

```python
handler.validate_output_source("chat", {"response": "Hi"})
```

#### `validate_input_for_subject(subject_id: str, message_type: str, data: Dict[str, Any])`

Validates data as input for the given subject's message type.

```python
handler.validate_input_for_subject("agent-2", "chat", {"message": "Hello"})
```

#### `validate_output_for_subject(subject_id: str, message_type: str, data: Dict[str, Any])`

Validates data as output for the given subject's message type.

```python
handler.validate_output_for_subject("agent-2", "chat", {"response": "Hi"})
```

---

### Transformation Methods

Each conversion method uses the DSL executor with appropriate input/output templates and field mappings.

#### `convert_input_to_source(message_type: str, data: Dict[str, Any]) -> Dict`

Converts raw input into the current subject's expected input format.

```python
converted = handler.convert_input_to_source("chat", {"user_input": "Hello"})
```

#### `convert_output_to_source(message_type: str, data: Dict[str, Any]) -> Dict`

Converts output data into the current subject's expected output format.

```python
converted = handler.convert_output_to_source("chat", {"reply": "Hi"})
```

#### `convert_input_to_target_subject(subject_id: str, message_type: str, data: Dict[str, Any]) -> Dict`

Transforms input data from the current subject to the target subject’s expected format.

```python
converted = handler.convert_input_to_target_subject("agent-2", "chat", {"user_input": "Hi"})
```

#### `convert_output_to_target_subject(subject_id: str, message_type: str, data: Dict[str, Any]) -> Dict`

Transforms output data from the current subject to the target subject’s output format.

```python
converted = handler.convert_output_to_target_subject("agent-2", "chat", {"reply": "Hello"})
```

---

### Introspection Utilities

#### `is_valid_message_type(subject_id: str, message_type: str) -> bool`

Checks whether a message type is defined for a subject.

```python
handler.is_valid_message_type("agent-2", "chat")
```

#### `has_input_dsl(subject_id: str, message_type: str) -> bool`

Checks if input DSL is defined for the message type.

```python
handler.has_input_dsl("agent-2", "chat")
```

#### `has_output_dsl(subject_id: str, message_type: str) -> bool`

Checks if output DSL is defined for the message type.

```python
handler.has_output_dsl("agent-2", "chat")
```

#### `get_input_dsl(subject_id: str, message_type: str) -> Optional[str]`

Returns the input DSL workflow ID for a message type.

```python
dsl = handler.get_input_dsl("agent-2", "chat")
```

#### `get_output_dsl(subject_id: str, message_type: str) -> Optional[str]`

Returns the output DSL workflow ID for a message type.

```python
dsl = handler.get_output_dsl("agent-2", "chat")
```

#### `get_all_message_types(subject_id: str) -> List[str]`

Returns all supported message types for the subject.

```python
types = handler.get_all_message_types("agent-2")
```

#### `get_message_type_metadata(subject_id: str, message_type: str) -> Dict[str, Any]`

Returns metadata associated with the message type.

```python
meta = handler.get_message_type_metadata("agent-2", "chat")
```

---

## DSL Workflows for Message Translation

In a distributed system of AI agents or services, each subject may have its own data representation standards. To enable seamless communication, the `MessageHandler` supports **message translation via DSL workflows**.

DSL (Domain-Specific Language) workflows act as transformation bridges that convert input/output data structures between **source** and **target** subjects, while preserving semantics and respecting schema constraints.

---

### Why DSL Workflows?

Subjects may differ in how they:

* Name fields (`user_input` vs `message`)
* Structure objects (flat vs nested)
* Interpret values (enum strings vs numeric codes)

Rather than hard-coding these mappings, DSL workflows provide a **declarative, reusable mechanism** to encode transformation logic and apply it dynamically at runtime.

---

### DSL Workflow Types

Each message type may define two transformation workflows:

| Field                    | Purpose                                                                  |
| ------------------------ | ------------------------------------------------------------------------ |
| `input_dsl_workflow_id`  | Transforms **incoming messages** into the source subject's input format  |
| `output_dsl_workflow_id` | Transforms **outgoing messages** into the target subject's output format |

These are stored per `MessageType` and executed by the `MessageHandler` as needed.

---

### Workflow Execution Context

When a DSL is executed for message translation, the runtime is provided with structured context to support intelligent transformation:

| Field             | Description                                                                 |
| ----------------- | --------------------------------------------------------------------------- |
| `data`            | The input data to transform                                                 |
| `message_type`    | The type identifier of the message                                          |
| `communication`   | The full `SubjectCommunication` object of the current subject               |
| `field_mapping`   | Mapping from standardized fields to subject-specific fields                 |
| `source_template` | Schema for the source subject's input/output structure                      |
| `target_template` | Schema for the target subject's input/output structure                      |
| `metadata`        | Human-readable metadata describing the message (description, example, etc.) |

This context is injected as part of the `addons` argument when executing the workflow via:

```python
executor = new_dsl_workflow_executor(
    workflow_id=workflow_id,
    workflows_base_uri=WORKFLOWS_API_URL,
    is_remote=False,
    addons=context
)
result = executor.execute({"data": input_data})
```

---

### Example Use Case

Let’s say we have two agents:

* **Agent A** expects: `{ "user_input": "Hello" }`
* **Agent B** expects: `{ "message": "Hello" }`

The DSL workflow for translating A’s output to B’s input might contain rules like:

```json
{
  "workflow": {
    "steps": [
      {
        "transform": {
          "output.message": "input.user_input"
        }
      }
    ]
  }
}
```

When the `MessageHandler` calls `convert_input_to_target_subject(...)`, this DSL is executed to reshape the message appropriately.

---

### Design Principles

* DSL workflows should **not embed hardcoded assumptions** about external systems.
* They should rely on the provided `field_mapping`, `source_template`, and `target_template`.
* Workflows should be reusable across subjects with similar roles or message semantics.
* Errors in DSL execution should be caught and logged with fallback if needed.

---

Here is the documentation for the new section:

---

## Selecting Message Type

In systems with multiple message types per subject, it becomes essential to support **discovery**, **matching**, and **intelligent selection** of message types for a given communication goal. The `MessageHandler` and `SubjectsLocalDB` provide utilities for listing, inspecting, and rendering message types into a **searchable representation** that can be used by humans, scripts, or language models (LLMs).

---

### Purpose

* Identify the most appropriate `message_type` for a given subject
* Present the available types in a structured, searchable form
* Enable LLMs or rule engines to make automated decisions about message routing

---

### Methods for Message Type Discovery

#### `get_all_message_types(subject_id: str) -> List[str]`

Returns a flat list of all message types defined for a subject.

```python
types = handler.get_all_message_types("agent-123")
# Output: ['chat', 'search_query', 'summarization_request']
```

#### `get_message_type_metadata(subject_id: str, message_type: str) -> Dict[str, Any]`

Returns the metadata dictionary for a given message type.

```python
meta = handler.get_message_type_metadata("agent-123", "chat")
# Output: { "description": "Chat response agent", ... }
```

#### `get_communications_searchable_fields(subject_id: str) -> List[Dict[str, Any]]`

Returns a list of message types with input/output templates and metadata fields that can be indexed or used in selection logic.

```python
search_fields = local_db.get_communications_searchable_fields("agent-123")
# Output: list of dicts for each message_type
```

---

### Searchable Representation for LLM Selection

To support automated reasoning by LLMs or interactive UI selection, the framework provides a **formatted, structured textual representation** of the available message types.

#### Method: `get_communications_searchable_representation(subject_id: str) -> str`

Returns a multi-line string that includes:

* Message type identifier
* Input and output template summaries
* Metadata fields: description, usage docs, examples

##### Example Output

```
Type: chat
  Input Template: {'message': {'type': 'string'}}
  Output Template: {'response': {'type': 'string'}}
  Metadata:
    description: Handles conversational input and produces agent replies
    usage_doc_link: http://docs.aios/agent/chat
    example: {"message": "What's the weather like today?"}

Type: summarization_request
  Input Template: {'content': {'type': 'string'}}
  Output Template: {'summary': {'type': 'string'}}
  Metadata:
    description: Converts long text into short summaries
    usage_doc_link: http://docs.aios/agent/summarize
    example: {"content": "Article text here..."}
```

#### Example Usage

```python
representation = local_db.get_communications_searchable_representation("agent-123")
print(representation)
```

This output can be:

* Indexed for search
* Embedded into a chat prompt
* Displayed in a selection UI
* Fed into an LLM to ask:
  *“Which message type should I use to summarize a document?”*

---

### Use in Agentic Systems

* Use the searchable representation to dynamically select the best `message_type` based on user intent
* LLMs can be used to map user prompts to message types by inspecting their `description`, `input_template`, and `example`
* Rule engines can select types based on expected field structure and target format

---



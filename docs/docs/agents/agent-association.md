# Agents Association Registry

### Introduction

The **Agents Association Registry** is a dynamic agent registry that manages and tracks runtime subjects (agents, processors, components, etc.) in an intelligent system. Each subject is a versioned, semantically described runtime unit that can be discovered and invoked by the agent.

This registry supports:

* Fetching and maintaining runtime metadata from a centralized REST API
* Registering agents by name and subject ID
* Querying and listing all available runtime subjects
* Providing **LLM-compatible searchable representations** for intelligent planners

Each subject includes details like its version, tags, role, supported DSLs, and runtime traits, making it highly suitable for use in autonomous workflows and agent orchestration.

---

### Usage

#### Initialize the Registry

```python
from agent_sdk.known_subjects import KnownSubjects

known_subjects = KnownSubjects(base_url="http://runtime-db-service")
```

#### Add an Agent

```python
# subject_id = "block.image_processor:1.0-stable"
known_subjects.add_agent("image_agent", subject_id)
```

#### Remove an Agent

```python
known_subjects.remove_agent("image_agent")
```

#### List Registered Agents

```python
agents = known_subjects.list_agents()
for name, subject in agents.items():
    print(f"{name}: {subject.subject_description}")
```

#### Query All Runtime Subjects (from backend)

```python
all_subjects = known_subjects.list_runtime_subjects()
```

#### Run a Custom Query

```python
query = {"subject_type": "block", "subject_search_tags": ["text", "nlp"]}
results = known_subjects.query_runtime_subjects(query)
```

---

### Searchable Representation

The method `get_searchable_representation()` returns a list of structured records that describe each known agent. This is particularly useful for use in LLM-based planners and agent selectors.

```python
searchable = known_subjects.get_searchable_representation()
```

Each entry includes:

| Field         | Description                                                      |
| ------------- | ---------------------------------------------------------------- |
| `id`          | Unique subject identifier (`type.name:version-tag`)              |
| `name`        | Subject name                                                     |
| `type`        | Subject type (e.g., `block`, `processor`, etc.)                  |
| `description` | Human-readable description of what the subject does              |
| `tags`        | Semantic search tags                                             |
| `traits`      | Execution/environmental traits (e.g., `gpu`, `batching`)         |
| `role`        | Subject's system role (`generator`, `router`, `evaluator`, etc.) |
| `schema`      | DSL input schema (if defined)                                    |
| `agent_name`  | Name used in the registry (user-defined alias)                   |

This output can be directly used by an LLM planner to select appropriate agents for downstream tasks.

---

### Example

```python
# Initialize the registry
known_subjects = KnownSubjects("http://runtime-db-service")

# Register an agent by its unique subject_id
known_subjects.add_agent("text_summarizer", "block.summarizer:1.0-stable")

# View registered agents
print("Registered Agents:")
for name, agent in known_subjects.list_agents().items():
    print(f"{name} -> {agent.subject_description}")

# Get structured view for LLM integration
llm_input = known_subjects.get_searchable_representation()

for entry in llm_input:
    print(f"Agent {entry['agent_name']} - Role: {entry['role']} - Tags: {entry['tags']}")
```

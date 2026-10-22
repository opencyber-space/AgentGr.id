# Procedural Memory

**Procedural memory answers "how do I do this?"** A procedure is a named skill: an ordered list of steps (action, parameters, expected outcome), the situations that should trigger it, and a running record of how often it succeeds.

Use it to store playbooks the agent can look up by situation ("the user wants to send an email") and to prefer the procedures that work best.

---

## Models

### `ProceduralMemory`

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | `""` | Unique-ish procedure name (lookups use it) |
| `content` | `str` | `""` | Description (stored as `description`) |
| `trigger_conditions` | `list[str]` | `[]` | Situations in which to use it |
| `steps` | `list[ProcedureStep]` | `[]` | Ordered steps |
| `success_rate` | `float` | `0.0` | Running success rate (0 – 1) |
| `use_count` | `int` | `0` | Number of recorded executions |
| `updated_at` | `datetime \| None` | `created_at` on store | |

### `ProcedureStep`

| Field | Type | Default |
|---|---|---|
| `step_order` | `int` | `0` |
| `action` | `str` | `""` |
| `parameters` | `dict` | `{}` |
| `expected_outcome` | `str` | `""` |

**Storage:** PostgreSQL (`procedures` + `procedure_steps`, steps cascade-deleted with their procedure), Weaviate (`<prefix>Procedural`), ArangoDB (`procedural_nodes` with `step_count`, `success_rate`, `use_count`).

---

## Usage

### Learn a procedure

```python
with AgentMemory(config) as mem:
    proc = mem.learn_procedure(
        "deploy_service",
        description="Deploy a service to the staging cluster",
        trigger_conditions=["user asks to deploy", "new release tagged"],
        steps=[
            {"action": "run_tests", "parameters": {"suite": "unit"}, "expected_outcome": "tests pass"},
            {"action": "build_image", "parameters": {"tag": "latest"}, "expected_outcome": "image pushed"},
            {"action": "kubectl_apply", "parameters": {"env": "staging"}, "expected_outcome": "pods ready"},
        ],
    )
```

`learn_procedure` numbers the steps 0, 1, 2… in list order.

### Find a procedure

```python
mem.procedural.get_by_name("deploy_service")

for p in mem.procedural.search_by_trigger("ship the new version to staging"):
    print(p.score, p.name, [s.action for s in p.steps])

mem.procedural.get_top_procedures(limit=10)   # by success rate, then use count
```

`search_by_trigger` is a vector search over the procedure's name, description and step text. Trigger conditions themselves are not part of the embedded text.

### Track executions

```python
mem.procedural.record_execution(proc.id, success=True)
mem.procedural.record_execution(proc.id, success=False)

p = mem.procedural.retrieve(proc.id)
print(p.use_count, p.success_rate)   # 2 0.5
```

`record_execution` increments `use_count` and updates the running average:
`new_rate = (old_rate × old_count + (1 if success else 0)) / (old_count + 1)`.

### Update and delete

```python
from agentic_memory.models import ProcedureStep

p.steps.append(ProcedureStep(step_order=3, action="smoke_test", expected_outcome="200 OK"))
mem.procedural.update(p)   # replaces all steps, re-embeds

mem.procedural.delete(p.id)
```

---

## API Reference

| Method | Description |
|---|---|
| `store(memory) -> str` | Store a procedure and its steps |
| `retrieve(memory_id)` | Load a procedure with its steps |
| `search(query, top_k=5)` | Vector similarity search |
| `update(memory)` | Overwrite fields and replace all steps |
| `delete(memory_id)` | Remove the procedure (steps cascade) |
| `record_execution(memory_id, success)` | Update `use_count` and `success_rate` |
| `get_by_name(name)` | First procedure with this name, or `None` |
| `get_top_procedures(limit=10)` | Best procedures by success rate, then use count |
| `search_by_trigger(condition)` | Vector search for procedures that fit a situation |

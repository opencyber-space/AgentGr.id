# Reflective Memory

**Reflective memory answers "what did I learn?"** A reflection is an insight the agent draws from its own experience: a lesson, a suggested improvement, how confident it is, and which episode it came from.

Reflections let the agent improve between tasks. Before acting, it can search for relevant lessons, and it can count how often each lesson actually influenced a decision.

---

## Model: `ReflectiveMemory`

| Field | Type | Default | Description |
|---|---|---|---|
| `content` | `str` | `""` | The reflection itself |
| `lesson` | `str` | `""` | The lesson learned |
| `improvement_suggestion` | `str` | `""` | What to do differently |
| `source_episode_id` | `str \| None` | `None` | Episode that produced the insight |
| `confidence` | `float` | `1.0` | |
| `applied_count` | `int` | `0` | Times the reflection influenced a decision |

**Storage:** PostgreSQL (`reflective_memories`), Weaviate (`<prefix>Reflective`), ArangoDB (`reflective_nodes`). When `source_episode_id` is set, an `episode_reflection` edge is created from the episode node (provenance). The edge is skipped silently if the episode node doesn't exist.

---

## Usage

### Reflect on an episode

```python
from agentic_memory.models import Outcome

with AgentMemory(config) as mem:
    ep = mem.remember_episode("Gave weather for Paris, Texas instead of Paris, France",
                              session_id="s7", agent_id="weather-agent",
                              outcome=Outcome.FAILURE, importance=0.8)

    ref = mem.reflect(
        "I assumed the wrong Paris",
        lesson="Clarify ambiguous location references",
        improvement_suggestion="Ask which city is meant when a name is ambiguous",
        source_episode_id=ep.id,
        confidence=0.9,
    )
```

### Use reflections before acting

```python
for r in mem.reflective.search("user asks weather for a city name", top_k=3):
    print(f"{r.score:.3f}  {r.lesson}")
    mem.reflective.mark_applied(r.id)      # this lesson influenced the decision
```

### Query

```python
mem.reflective.get_from_episode(ep.id)              # records with source_episode_id == ep.id (PostgreSQL)
mem.reflective.get_reflections_for_episode(ep.id)   # nodes linked from the episode (ArangoDB)
mem.reflective.get_most_applied(limit=10)
mem.reflective.get_above_confidence(0.8)
```

### Update and delete

```python
ref.confidence = 0.95
ref.improvement_suggestion = "Ask for the country when the city name is ambiguous"
mem.reflective.update(ref)

mem.reflective.delete(ref.id)
```

---

## API Reference

| Method | Description |
|---|---|
| `store(memory) -> str` | Store a reflection (+ provenance edge when `source_episode_id` is set) |
| `retrieve(memory_id)` | Load by ID |
| `search(query, top_k=5)` | Vector similarity search |
| `update(memory)` | Re-embed and overwrite content, lesson, suggestion, confidence, applied count, metadata |
| `delete(memory_id)` | Remove from all backends |
| `mark_applied(memory_id)` | Increment `applied_count` |
| `get_from_episode(episode_id)` | Reflections whose `source_episode_id` matches |
| `get_most_applied(limit=10)` | Reflections ordered by `applied_count` |
| `get_above_confidence(threshold=0.8)` | Reflections with `confidence >= threshold` |
| `get_reflections_for_episode(episode_id)` | Reflection nodes linked from an episode in the graph |

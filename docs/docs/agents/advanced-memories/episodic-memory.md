# Episodic Memory

**Episodic memory answers "what happened?"** An episode is a specific event or experience, tied to a time, a session and an agent: what was asked, what the agent did, and how it turned out.

Use it for session logs, task histories, and any record you later want to search ("have I seen something like this before?"), filter ("what failed today?"), or learn from (reflections and lessons are mined from episodes).

---

## Model: `EpisodicMemory`

| Field | Type | Default | Description |
|---|---|---|---|
| `content` | `str` | `""` | What happened (embedded for search) |
| `session_id` | `str` | `""` | Session the episode belongs to |
| `agent_id` | `str` | `""` | Agent that experienced it |
| `context` | `dict` | `{}` | Who / when / where / why |
| `outcome` | `Outcome` | `UNKNOWN` | `SUCCESS`, `FAILURE`, `NEUTRAL` or `UNKNOWN` |
| `importance` | `float` | `0.5` | 0.0 – 1.0 |
| `id`, `metadata`, `created_at`, `score` | | | Common fields (see [Agentic Memory](agentic-memory.md#common-store-interface)) |

**Storage:** PostgreSQL (`episodic_memories`), Weaviate (`<prefix>Episodic`), ArangoDB (`episodic_nodes`, linked with `memory_relations`).

---

## Usage

### Store episodes

```python
from agentic_memory import AgentMemory
from agentic_memory.models import EpisodicMemory, Outcome

with AgentMemory(config) as mem:
    e1 = mem.remember_episode(
        "User asked about the weather forecast for Paris this weekend.",
        session_id="session-42", agent_id="weather-agent",
        context={"user": "alice", "channel": "chat"},
        outcome=Outcome.SUCCESS, importance=0.6,
    )

    # Or build the model yourself
    e2 = EpisodicMemory(content="Weather API timed out", session_id="session-42",
                        agent_id="weather-agent", outcome=Outcome.FAILURE, importance=0.9)
    mem.episodic.store(e2)
```

### Search and retrieve

```python
for ep in mem.episodic.search("weather questions about France", top_k=3):
    print(f"{ep.score:.3f}  {ep.outcome.value}  {ep.content}")

ep = mem.episodic.retrieve(e1.id)
```

### Filter

```python
mem.episodic.get_by_session("session-42")          # oldest first
mem.episodic.get_by_agent("weather-agent", limit=50)   # newest first
mem.episodic.get_by_outcome(Outcome.FAILURE)       # newest first
mem.episodic.get_high_importance(threshold=0.7)    # highest importance first
```

### Link episodes (graph)

```python
mem.episodic.link_episodes(e1.id, e2.id, relation="followed_by")
related = mem.episodic.get_related_episodes(e1.id)   # list of episode nodes (dicts)
```

Links are directed edges in `memory_relations`. `get_related_episodes` returns the nodes one hop away in the outbound direction.

Reflections that name an episode as `source_episode_id` are linked from it automatically; see [Reflective Memory](reflective-memory.md).

### Update and delete

```python
e1.importance = 0.9
e1.outcome = Outcome.SUCCESS
mem.episodic.update(e1)      # re-embeds content and updates all three backends

mem.episodic.delete(e2.id)
```

`update` writes `content`, `context`, `outcome`, `importance` and `metadata`. `session_id` and `agent_id` are not changed by `update`.

---

## API Reference

| Method | Description |
|---|---|
| `store(memory) -> str` | Store an episode |
| `retrieve(memory_id) -> EpisodicMemory \| None` | Load by ID |
| `search(query, top_k=5) -> list[EpisodicMemory]` | Vector similarity search |
| `update(memory)` | Re-embed and overwrite |
| `delete(memory_id)` | Remove from all backends |
| `get_by_session(session_id)` | Episodes in a session, ordered by `created_at` ascending |
| `get_by_agent(agent_id, limit=50)` | Latest episodes of an agent |
| `get_by_outcome(outcome)` | Episodes with an outcome, newest first |
| `get_high_importance(threshold=0.7)` | Episodes with `importance >= threshold` |
| `link_episodes(from_id, to_id, relation="related")` | Add a directed graph edge |
| `get_related_episodes(memory_id)` | Episodes linked from this one |

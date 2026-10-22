# Agentic Memory

`agentic_memory` is a Python library that gives an agent six kinds of memory behind one façade, `AgentMemory`:

| Store | Model | Backends |
|---|---|---|
| `mem.episodic` | `EpisodicMemory` | PostgreSQL + Weaviate + ArangoDB |
| `mem.semantic` | `SemanticMemory` | PostgreSQL + Weaviate + ArangoDB (knowledge graph) |
| `mem.procedural` | `ProceduralMemory` | PostgreSQL + Weaviate + ArangoDB |
| `mem.reflective` | `ReflectiveMemory` | PostgreSQL + Weaviate + ArangoDB |
| `mem.reward` | `RewardMemory` | PostgreSQL + Weaviate + ArangoDB |
| `mem.context_kv` | plain dicts | Redis |

---

## How Storage Works

Every write to one of the five long-term types goes to **three backends at once**:

```
store(memory)
     │
     ├──► PostgreSQL   structured fields, exact lookups, filters, aggregates
     ├──► Weaviate     embedding vector (cosine similarity search)
     └──► ArangoDB     graph node (+ edges for relationships)
```

Reads use the most suitable backend:

| Operation | Backend |
|---|---|
| `retrieve(id)`, filters, aggregates | PostgreSQL |
| `search(query)` | Weaviate finds the nearest IDs, then each record is loaded from PostgreSQL. `score` = 1 − cosine distance |
| Relationships (links, paths, neighbours, provenance) | ArangoDB traversal |

Context KV is different: it lives only in Redis (one hash per agent session).

> Writes are not transactional across backends. If one backend fails mid-write, the others may already hold the record.

---

## Installation

Requires Python ≥ 3.8 and the four databases (see [Deployment](deployment.md)).

```bash
cd agent-memories/agentic-memory
pip install -e ".[dev]"
```

Dependencies: `weaviate-client>=4.0`, `python-arango>=8.0`, `psycopg2>=2.9`, `openai>=1.0`, `redis>=5.0`.

---

## Configuration

```python
from agentic_memory import (
    AgentMemory, MemoryConfig, PostgresConfig, WeaviateConfig, ArangoConfig, RedisConfig,
)

config = MemoryConfig(
    postgres=PostgresConfig(host="db.example.org", port=30432, database="agent_memory",
                            username="postgres", password="..."),
    weaviate=WeaviateConfig(host="db.example.org", port=30880, grpc_port=30851,
                            collection_prefix="AgentMemory", embedding_dim=1536),
    arango=ArangoConfig(url="http://db.example.org:30529", username="root",
                        password="...", database="agent_memory"),
    redis=RedisConfig(host="db.example.org", port=30637, password="...", db=0),
    embedding_model="text-embedding-3-small",
    top_k=5,
)
mem = AgentMemory(config)
```

| Config | Field | Default |
|---|---|---|
| `PostgresConfig` | `host`, `port`, `database`, `username`, `password` | `localhost`, `5432`, `agent_memory`, `postgres`, `""` |
| `WeaviateConfig` | `host`, `port`, `grpc_port` | `localhost`, `8080`, `50051` |
| | `collection_prefix` | `AgentMemory` (collections `AgentMemoryEpisodic`, `AgentMemorySemantic`, …) |
| | `embedding_dim` | `1536` (passed to the embedding provider) |
| `ArangoConfig` | `url`, `username`, `password`, `database` | `http://localhost:8529`, `root`, `""`, `agent_memory` |
| `RedisConfig` | `host`, `port`, `password`, `db` | `localhost`, `6379`, `""`, `0` |
| `MemoryConfig` | `embedding_model` | `text-embedding-3-small` |
| | `top_k` | `5` (stored on the config; search methods take their own `top_k`) |

`AgentMemory()` with no arguments connects to all four databases on `localhost` with default ports.

On start-up the library creates what it needs:

* PostgreSQL tables and indexes (`CREATE TABLE IF NOT EXISTS`).
* One Weaviate collection per memory type (HNSW index, cosine distance, no vectorizer).
* The ArangoDB database plus its node and edge collections.

---

## Embeddings

Vectors come from an `EmbeddingProvider`. By default it calls the **OpenAI embeddings API** (`text-embedding-3-small`) and reads `OPENAI_API_KEY` from the environment.

```python
from agentic_memory.embeddings import EmbeddingProvider

# Default: OpenAI
mem = AgentMemory(config, openai_api_key="sk-...")       # or set OPENAI_API_KEY

# Explicit provider
embedder = EmbeddingProvider(model="text-embedding-3-large", dim=3072, api_key="sk-...")
mem = AgentMemory(config, embedder=embedder)

# Any embedding function
def my_embed(text: str) -> list[float]:
    ...
mem = AgentMemory(config, embedder=EmbeddingProvider(embed_fn=my_embed, dim=768))
```

`EmbeddingProvider` provides `embed(text)` and `embed_batch(texts)`. Use the same model (and dimension) for the lifetime of a Weaviate collection, because vectors from different models are not comparable.

What gets embedded for each type:

| Type | Embedded text |
|---|---|
| Episodic | `content` |
| Semantic | `"{subject} {predicate} {object} {content}"` |
| Procedural | `"{name} {description} {step.action step.expected_outcome …}"` |
| Reflective | `"{content} {lesson} {improvement_suggestion}"` |
| Reward | `"{state_description} {action} {outcome}"` |

---

## The `AgentMemory` Façade

### Write helpers

```python
from agentic_memory.models import Outcome

ep = mem.remember_episode(
    "User asked about the weather in Paris",
    session_id="sess-001", agent_id="weather-agent",
    context={"user": "alice", "channel": "chat"},
    outcome=Outcome.SUCCESS, importance=0.8, metadata={"lang": "en"},
)

fact = mem.know_fact("Paris", "is_capital_of", "France", confidence=1.0, source="wikipedia")

proc = mem.learn_procedure(
    "send_email",
    steps=[
        {"action": "compose", "parameters": {"to": "..."}, "expected_outcome": "draft ready"},
        {"action": "send", "parameters": {}, "expected_outcome": "email sent"},
    ],
    description="Send an email to a contact",
    trigger_conditions=["user wants to send an email"],
)

ref = mem.reflect(
    "I should confirm location before giving weather",
    lesson="Clarify ambiguous location references",
    improvement_suggestion="Ask 'Which Paris?' when unclear",
    source_episode_id=ep.id, confidence=0.9,
)

rw = mem.record_reward("low battery warning shown", "recharge_now", reward=1.0,
                       outcome="battery restored", policy="energy")
```

| Method | Returns | Notes |
|---|---|---|
| `remember_episode(content, *, session_id, agent_id, context, outcome, importance, metadata)` | `EpisodicMemory` | `outcome` defaults to `Outcome.UNKNOWN`, `importance` to `0.5` |
| `know_fact(subject, predicate, object_, *, content, confidence, source, metadata)` | `SemanticMemory` | `content` defaults to `"subject predicate object"` |
| `learn_procedure(name, steps, *, description, trigger_conditions, metadata)` | `ProceduralMemory` | `steps` are dicts with `action`, `parameters`, `expected_outcome`; `step_order` follows list order |
| `reflect(content, lesson, *, improvement_suggestion, source_episode_id, confidence, metadata)` | `ReflectiveMemory` | Linking to an episode creates a provenance edge |
| `record_reward(state_description, action, reward, *, outcome, policy, context, metadata)` | `RewardMemory` | `policy` defaults to `"default"` |

Each helper builds the model and calls the store's `store()`. You can also build models yourself and call `mem.<type>.store(memory)`.

### Searching everything: `recall`

```python
results = mem.recall("weather questions", top_k=5)
# {"episodic": [...], "semantic": [...], "procedural": [...], "reflective": [...], "reward": [...]}

results = mem.recall("step", top_k=5, agent_id="planner-agent", session_id="session-99")
# ... plus "context": [{"key": "...", "value": {...}}, ...]
```

`recall` runs a vector search on each of the five long-term types. When `agent_id` or `session_id` is given, it also adds a `"context"` list: the session's context entries whose key or value contains the query string (case-insensitive substring match, up to `top_k`).

### Context helpers

```python
mem.set_context("status", {"ready": True}, agent_id="planner", session_id="s1", ttl_seconds=600)
mem.get_context("status", agent_id="planner", session_id="s1")   # {"ready": True}
```

These are shorthands for `mem.context_kv.set(...)` / `.get(...)`. See [Context KV Memory](context-kv-memory.md).

### Lifecycle

```python
with AgentMemory(config) as mem:   # closes PostgreSQL, Weaviate and Redis on exit
    ...

mem = AgentMemory(config)
mem.close()
```

---

## Common Store Interface

Every long-term store (`episodic`, `semantic`, `procedural`, `reflective`, `reward`) implements:

| Method | Description |
|---|---|
| `store(memory) -> str` | Write to PostgreSQL, Weaviate and ArangoDB; returns the memory ID |
| `retrieve(memory_id)` | Load by ID from PostgreSQL (`None` if missing) |
| `search(query, top_k=5)` | Vector search; results carry `.score` (higher is more similar) |
| `update(memory)` | Re-embed and overwrite in all three backends |
| `delete(memory_id)` | Remove from all three backends (graph edges are not removed) |

All models share the `BaseMemory` fields:

| Field | Type | Default |
|---|---|---|
| `id` | `str` | random UUID |
| `content` | `str` | `""` |
| `metadata` | `dict` | `{}` |
| `embedding` | `list[float] \| None` | set on store/update |
| `created_at` | `datetime` | `datetime.utcnow()` |
| `score` | `float \| None` | set by `search` |

Enums: `MemoryType` (`episodic`, `semantic`, `procedural`, `reflective`, `reward`) and `Outcome` (`success`, `failure`, `neutral`, `unknown`).

---

## Storage Layout

### PostgreSQL tables

| Table | Holds | Indexed columns |
|---|---|---|
| `episodic_memories` | episodes | `session_id`, `agent_id`, `outcome` |
| `semantic_memories` | triples | `subject`, `predicate` |
| `procedures` | procedures | `name` |
| `procedure_steps` | steps (FK → `procedures`, cascade delete) | `procedure_id` |
| `reflective_memories` | reflections | `source_episode_id` |
| `reward_memories` | reward tuples | `action`, `policy` |

`context`, `metadata`, `trigger_conditions` and `parameters` are stored as `JSONB`.

### Weaviate collections

`<prefix>Episodic`, `<prefix>Semantic`, `<prefix>Procedural`, `<prefix>Reflective`, `<prefix>Reward`. Each object has the memory's ID as its UUID, a `memory_id` property and the embedding vector.

### ArangoDB collections

| Collection | Kind | Contents |
|---|---|---|
| `episodic_nodes`, `semantic_nodes`, `procedural_nodes`, `reflective_nodes`, `reward_nodes` | vertex | One node per memory (`_key` = memory ID) with its main fields |
| `entity_nodes` | vertex | Knowledge-graph entities (one per distinct subject/object) |
| `memory_relations` | edge | Episode ↔ episode links, reward state transitions |
| `entity_relations` | edge | Subject → object edges of semantic facts (`predicate`, `memory_id`, `confidence`) |
| `episode_reflection` | edge | Episode → reflection provenance |

### Redis

One hash per session: key `<agent_id>__<session_id>`, one field per context key, values stored as JSON.

---

## Testing

```bash
cd agent-memories/agentic-memory
pytest
```

The tests mock all four backends and do not need running databases. Runnable examples against real databases are in `agent-memories/examples/` (`example_episodic.py`, `example_semantic.py`, `example_procedural.py`, `example_reflective.py`, `example_reward.py`, `example_context_kv.py`, `example_openai_embeddings.py`). Connection settings come from environment variables read by `examples/db_config.py` (`POSTGRES_HOST`, `WEAVIATE_HOST`, `ARANGO_URL`, `REDIS_HOST`, …).

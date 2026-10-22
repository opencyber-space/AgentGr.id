# Context KV Memory

**Context KV memory answers "what is my current session state?"** It is a fast, schema-free key-value store for working state that belongs to one agent session: user preferences, task progress, scratch notes, tool-call counters.

It is backed by **Redis hashes**. Each `(agent_id, session_id)` pair is one hash, keyed `<agent_id>__<session_id>`, so:

* all keys of a session can be listed, exported or wiped together;
* a TTL applies to the whole session at once.

Values must be JSON-serializable. They are stored as JSON and returned as Python objects.

---

## Access

```python
from agentic_memory import AgentMemory

with AgentMemory(config) as mem:
    kv = mem.context_kv                     # ContextKVMemory bound to the configured Redis
```

Or standalone, without the other databases:

```python
from agentic_memory.backends.redis_client import RedisClient
from agentic_memory.config import RedisConfig
from agentic_memory.memory_types.context_kv import ContextKVMemory

redis = RedisClient(RedisConfig(host="localhost", port=6379, password=""))
kv = ContextKVMemory(
    redis,
    on_set=lambda agent, session, key, value: print("SET", agent, session, key),
    on_get=lambda agent, session, key, value: print("GET", agent, session, key),
)
```

`on_get` and `on_set` are optional observability hooks. `on_get` fires only for values that exist.

---

## Usage

```python
agent, session = "planner-agent", "session-99"

# set / get (a TTL applies to the whole session hash)
kv.set(agent, session, "user_prefs", {"language": "en", "theme": "dark"}, ttl_seconds=600)
kv.set(agent, session, "task_state", {"current_step": 2, "total_steps": 5})
kv.get(agent, session, "user_prefs")          # {"language": "en", "theme": "dark"}
kv.get(agent, session, "missing")             # None

# discoverability
kv.exists(agent, session, "task_state")       # True
kv.keys(agent, session)                       # ["user_prefs", "task_state"]

# bulk
kv.set_many(agent, session, {"scratch": {"notes": []}, "tool_calls": {"count": 0}})
kv.get_many(agent, session, ["user_prefs", "ghost"])   # {"user_prefs": {...}, "ghost": None}

# atomic initialise-once
state = kv.get_or_set(agent, session, "init_flag", lambda: {"initialized": True})

# snapshot / restore
snapshot = kv.dump(agent, session)            # {key: value, ...}
kv.clear(agent, session)                      # delete the whole session
kv.restore(agent, session, snapshot, ttl_seconds=300)

# delete one key
kv.delete(agent, session, "scratch")
```

### Through `AgentMemory`

```python
mem.set_context("status", {"ready": True}, agent_id=agent, session_id=session, ttl_seconds=600)
mem.get_context("status", agent_id=agent, session_id=session)

mem.recall("step", agent_id=agent, session_id=session)["context"]
# context entries whose key or value contains "step" (case-insensitive)
```

---

## Semantics

* **TTL** — `ttl_seconds` sets the expiry of the *whole session hash* (Redis `EXPIRE`). A later `set` without a TTL keeps the existing expiry.
* **`get_or_set`** — if the key exists, its value is returned. Otherwise the factory is called and the value is written with `HSETNX`. If another writer wins the race, their value is returned instead.
* **`restore`** — the same as `set_many`; it does not clear existing keys first.

---

## API Reference

| Method | Description |
|---|---|
| `get(agent_id, session_id, key)` | Value or `None` |
| `set(agent_id, session_id, key, data, *, ttl_seconds=None)` | Write a value |
| `delete(agent_id, session_id, key)` | Remove one key |
| `clear(agent_id, session_id)` | Delete the whole session hash |
| `exists(agent_id, session_id, key)` | `True` if present |
| `keys(agent_id, session_id)` | All keys in the session |
| `get_many(agent_id, session_id, keys)` | Dict of key → value (or `None`) in one round-trip |
| `set_many(agent_id, session_id, mapping, *, ttl_seconds=None)` | Write several keys in one call |
| `dump(agent_id, session_id)` | Export the session as a dict |
| `restore(agent_id, session_id, snapshot, *, ttl_seconds=None)` | Bulk-write a snapshot |
| `get_or_set(agent_id, session_id, key, default_factory, *, ttl_seconds=None)` | Atomic initialise-once |

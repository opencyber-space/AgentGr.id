# Agent Config Store

The **Agent Config Store** is a Redis-backed configuration manager for agent applications. It is provided by the `ConfigManager` class in the `agent_core_libs` package, and is built on the `CommonCache` Redis wrapper from the same package.

It is useful for agents that need runtime-tunable configuration — thresholds, operational modes, feature toggles — shared across processes and instances.

---

### Introduction

`ConfigManager` provides:

* **Layered reads**: environment variables → Redis → defaults → caller-supplied default.
* **Typed getters** for `str`, `int`, `float`, `bool` and JSON.
* **Optional TTLs** on values.
* **Bulk operations**, snapshots and snapshot loading.
* **Change notifications** over Redis Pub/Sub, and a `watch()` helper to react to them.
* **Validation hooks** that run before a value is written.
* **Namespacing**, so several modules can keep separate key spaces in one Redis.

---

### Installation

`ConfigManager` and `CommonCache` are part of `agent_core_libs` (`libs/core-libs`), which depends on `redis>=5.0.0`.

```bash
pip install ./libs/core-libs
```

### Importing

```python
from agent_core_libs.common_cache import CommonCache
from agent_core_libs.config import ConfigManager
```

---

### Creating a Config Manager

First create a `CommonCache` (a Redis connection with a key namespace), then wrap it in a `ConfigManager`:

```python
cache = CommonCache(default_url="redis://localhost:6379/0")

config = ConfigManager(
    cache,
    namespace="config",                 # key namespace for this manager
    env_prefix="AGENT_",                # optional: enable ENV overrides
    defaults={"threshold": 0.75, "mode": "auto"},
    validator=None,                     # optional: callable(key, value), raise to reject
    announce_changes=True,              # publish changes over Pub/Sub
)
```

**`CommonCache` arguments** (keyword-only):

| Argument | Default | Description |
|---|---|---|
| `default_url` | — (required) | Redis URL used when `url` is not given |
| `url` | `None` | Redis URL (overrides `default_url`) |
| `namespace` | `"common"` | Key prefix |
| `separator` | `":"` | Separator used between namespace parts |
| `decode_responses`, `socket_timeout`, `socket_connect_timeout`, `health_check_interval`, `max_connections` | `True`, `5.0`, `5.0`, `15`, `128` | Redis connection settings |
| `value_serializer` / `value_deserializer` | JSON for non-strings / JSON-or-string | How values are encoded |

`CommonCache` pings Redis on creation and raises if Redis is unreachable.

**`ConfigManager` arguments:**

| Argument | Default | Description |
|---|---|---|
| `cache` | — (required) | A `CommonCache` instance |
| `namespace` | `"config"` | Namespace appended to the cache's namespace (with the defaults above, keys are stored as `common:config:<key>`) |
| `env_prefix` | `None` | If set, `get(key)` first checks the environment variable `<env_prefix><KEY>` (upper-cased, `.` replaced by `_`) |
| `defaults` | `{}` | Fallback values when a key is not in Redis |
| `validator` | `None` | `validator(key, value)` is called before each write; raise to reject the value |
| `announce_changes` | `True` | Publish a message on `<namespace>::changes` for every set/delete |

---

### Reading and Writing Values

```python
config.set("threshold", 0.9)
config.set("session_token", "abc", ttl=3600)   # expires after 1 hour

config.get("threshold")            # 0.9
config.get("missing", "fallback")  # "fallback"
config.exists("threshold")         # True
config.delete("threshold")         # True if deleted
```

`get(key, default=None)` resolves values in this order:

1. Environment variable `<env_prefix><KEY>` (only when `env_prefix` is set). Values from the environment are always strings.
2. The value stored in Redis.
3. `defaults[key]`.
4. The `default` argument.

#### Typed getters

```python
config.get_str("mode")                 # "auto"
config.get_int("max_workers", 4)
config.get_float("threshold", 0.5)
config.get_bool("enabled", False)      # accepts true/false, 1/0, yes/no, y/n, on/off
config.get_json("routing_rules", {})   # parses JSON strings; returns dicts/lists as-is
```

`get_bool` raises `ValueError` for values it cannot interpret.

---

### Bulk Operations and Snapshots

```python
config.set_many({"mode": "manual", "threshold": 0.6})
config.set_many({"temp_flag": True}, ttl=60)        # TTL applied to every key

config.get_many(["mode", "threshold", "unknown"])   # Redis → ENV → defaults per key

config.set_defaults({"retries": 3})                 # add or override defaults

snapshot = config.snapshot()                        # dict of all keys/values in this namespace (Redis only)
config.load_snapshot(snapshot, clear_before=True)   # optionally wipe the namespace first

list(config)                                        # logical key names in the namespace
len(config)                                         # number of keys
config.keys("thr*")                                 # Redis key names matching a glob (including the namespace prefix)
```

---

### Namespaces

```python
llm_config = config.with_namespace("llm")
llm_config.set("temperature", 0.2)
```

`with_namespace(child)` returns a new `ConfigManager` with its own key space under the parent's namespace. It shares the Redis connection, validator and change-announcement setting, but starts with no defaults. If the parent has an `env_prefix`, the child's prefix is `<env_prefix><CHILD>_`.

---

### Watching for Changes

When `announce_changes=True`, every `set`, `set_many`, `delete` and `load_snapshot` publishes a JSON message on the Redis channel `<namespace>::changes`:

```json
{ "op": "set", "key": "threshold", "value": 0.9, "ttl": null, "ts": 1735689600 }
```

Subscribe with `watch()`:

```python
def on_change(event):
    print(f"{event['op']} {event['key']} -> {event['value']}")

config.watch(on_change)                 # runs a daemon thread; returns the Thread

for event in config.watch(None, run_in_thread=False):   # or iterate as a generator
    print(event)
```

Any instance of the agent that shares the Redis and namespace receives these events. You can use them to reload settings at runtime.

---

### Usage Example

```python
from agent_core_libs.common_cache import CommonCache
from agent_core_libs.config import ConfigManager


def validate(key, value):
    if key == "threshold" and not (0.0 <= float(value) <= 1.0):
        raise ValueError("threshold must be between 0 and 1")


cache = CommonCache(default_url="redis://localhost:6379/0", namespace="agent-123")
config = ConfigManager(
    cache,
    env_prefix="AGENT_",
    defaults={"threshold": 0.5, "enabled": True},
    validator=validate,
)


class ThresholdModule:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.threshold = config.get_float("threshold")
        config.watch(self._on_change)

    def _on_change(self, event):
        if event["key"] == "threshold":
            self.threshold = float(event["value"])


module = ThresholdModule(config)
config.set("threshold", 0.8)    # every watcher sees the change
```

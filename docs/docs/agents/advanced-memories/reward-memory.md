# Reward Memory

**Reward memory answers "what works best?"** Each memory is a **(state, action, reward)** tuple: in this situation the agent did this, and it earned this reward. Tuples are grouped by **policy**, so separate decision domains don't mix.

Because states are embedded, the agent can ask "in situations like this one, which action earned the most?" even when the new state is worded differently.

---

## Model: `RewardMemory`

| Field | Type | Default | Description |
|---|---|---|---|
| `state_description` | `str` | `""` | The situation (also stored as `content`) |
| `action` | `str` | `""` | Action taken |
| `reward` | `float` | `0.0` | Reward received (any sign or scale) |
| `outcome` | `str` | `""` | What happened |
| `policy` | `str` | `"default"` | Decision domain |
| `context` | `dict` | `{}` | Extra details |

**Storage:** PostgreSQL (`reward_memories`, indexed by `action` and `policy`), Weaviate (`<prefix>Reward`), ArangoDB (`reward_nodes`, with `memory_relations` edges for state transitions).

---

## Usage

### Record rewards

```python
with AgentMemory(config) as mem:
    ids = []
    for state, action, reward, outcome in [
        ("battery level is critically low", "recharge_now", 1.0, "battery restored"),
        ("battery level is critically low", "continue_task", -1.0, "device shutdown"),
        ("external API rate limit reached", "back_off_60s", 0.9, "requests resumed"),
        ("external API rate limit reached", "retry_immediately", -0.5, "429 error repeated"),
    ]:
        ids.append(mem.record_reward(state, action, reward, outcome=outcome, policy="default").id)
```

### Choose the best action

```python
best = mem.reward.get_best_action("device battery is almost empty", policy="default")
if best:
    action, avg_reward = best        # ("recharge_now", 1.0)
```

How `get_best_action(state_description, policy="default", top_k=20)` decides:

1. Vector-search the `top_k` most similar stored states.
2. Keep the ones with the given `policy`. If none match the policy, all candidates are used.
3. Average the reward per action, and return `(action, avg_reward)` for the highest average.

It returns `None` when nothing similar is stored.

### Statistics

```python
mem.reward.get_action_stats("default")
# {"recharge_now": {"count": 1, "avg_reward": 1.0, "max_reward": 1.0, "min_reward": 1.0}, ...}

mem.reward.get_policy_summary("default")
# {"total": 4, "avg_reward": 0.1, "max_reward": 1.0, "min_reward": -1.0, "unique_actions": 4}

mem.reward.get_top_rewards(limit=3, policy="default")
mem.reward.get_by_policy("default", limit=100)
```

### State transitions (graph)

```python
mem.reward.record_transition(ids[0], ids[1], action="recharge_now")
mem.reward.get_successor_states(ids[0])     # reward nodes reached from ids[0]
```

Transitions are `memory_relations` edges with `relation="state_transition"` and the `action`.

### Search, update and delete

```python
for rw in mem.reward.search("API throttled too many requests", top_k=3):
    print(rw.score, rw.action, rw.reward)

rw = mem.reward.retrieve(ids[0])
rw.reward = 0.8
mem.reward.update(rw)
mem.reward.delete(rw.id)
```

---

## API Reference

| Method | Description |
|---|---|
| `store(memory) -> str` | Store a tuple |
| `retrieve(memory_id)` | Load by ID |
| `search(query, top_k=5)` | Vector search over state/action/outcome |
| `update(memory)` | Re-embed and overwrite |
| `delete(memory_id)` | Remove from all backends |
| `get_best_action(state_description, policy="default", top_k=20)` | `(action, avg_reward)` for the best action in similar states, or `None` |
| `get_action_stats(policy="default")` | Per-action count / avg / max / min reward |
| `get_policy_summary(policy="default")` | Totals for a policy |
| `get_by_policy(policy, limit=100)` | Tuples of a policy, highest reward first |
| `get_top_rewards(limit=10, policy="default")` | Highest-reward tuples of a policy |
| `record_transition(from_id, to_id, action)` | Add a state-transition edge |
| `get_successor_states(memory_id)` | States reached from a state |

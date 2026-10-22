# Semantic Memory

**Semantic memory answers "what is true?"** Each memory is a fact stored as a **subject – predicate – object** triple, for example `("Paris", "is_capital_of", "France")`, with a confidence and a source.

Besides being searchable, facts build a **knowledge graph**. Every distinct subject and object becomes an entity node, and every fact becomes an edge between them. The agent can then ask "how is A related to B?" or "what do I know about A?".

---

## Model: `SemanticMemory`

| Field | Type | Default | Description |
|---|---|---|---|
| `subject` | `str` | `""` | Entity the fact is about |
| `predicate` | `str` | `""` | Relationship |
| `object` | `str` | `""` | Value or related entity |
| `confidence` | `float` | `1.0` | How sure the agent is |
| `source` | `str` | `""` | Where the fact came from |
| `content` | `str` | `""` | Free text (`know_fact` defaults it to `"subject predicate object"`) |
| `updated_at` | `datetime \| None` | `created_at` on store | Set to now on every `update` |

**Storage:** PostgreSQL (`semantic_memories`), Weaviate (`<prefix>Semantic`), ArangoDB (`semantic_nodes`, plus `entity_nodes` + `entity_relations` for the knowledge graph).

Entity node keys are the first 16 hex characters of the MD5 of the entity name, so the same name always maps to the same node.

---

## Usage

### Store facts

```python
with AgentMemory(config) as mem:
    mem.know_fact("Paris", "is_capital_of", "France", source="wikipedia")
    mem.know_fact("France", "is_member_of", "European Union")
    mem.know_fact("European Union", "uses_currency", "Euro", confidence=0.95)
    mem.know_fact("Python", "is_a", "programming language",
                  content="Python is a general-purpose programming language")
```

Each call stores the fact and also creates entity nodes for the subject and object (if new) and an `entity_relations` edge between them. The edge carries `predicate`, `memory_id` and `confidence`.

### Search

```python
for fact in mem.semantic.search("capital city of France", top_k=3):
    print(f"{fact.score:.3f}  {fact.subject} {fact.predicate} {fact.object}")
```

### Exact lookups

```python
mem.semantic.get_by_subject("Paris")                 # all facts about Paris, by confidence
mem.semantic.get_by_predicate("is_capital_of")       # all capital-of facts
mem.semantic.get_triple("Paris", "is_capital_of")    # best (highest-confidence) match or None
mem.semantic.get_above_confidence(0.9)
```

### Knowledge graph

```python
mem.semantic.get_neighbors("France")                         # entities France points to
mem.semantic.get_neighbors("France", direction="INBOUND")    # entities pointing to France
mem.semantic.get_neighbors("France", direction="ANY")

path = mem.semantic.find_path("Paris", "Euro")
# shortest outbound path: Paris -> France -> European Union -> Euro
```

`get_neighbors` returns entity node dicts (`{"_key": ..., "name": ...}`). `find_path` returns the vertices of the shortest outbound path over `entity_relations`.

### Update and delete

```python
fact = mem.semantic.get_triple("European Union", "uses_currency")
fact.confidence = 1.0
mem.semantic.update(fact)

mem.semantic.delete(fact.id)
```

`update` and `delete` change the fact record and its `semantic_nodes` node. Entity nodes and `entity_relations` edges created at store time are not updated or removed.

---

## API Reference

| Method | Description |
|---|---|
| `store(memory) -> str` | Store a fact, create entity nodes and a knowledge-graph edge |
| `retrieve(memory_id)` | Load by ID |
| `search(query, top_k=5)` | Vector similarity search |
| `update(memory)` | Re-embed and overwrite; sets `updated_at` |
| `delete(memory_id)` | Remove the fact record |
| `get_by_subject(subject)` | Facts with this subject, highest confidence first |
| `get_by_predicate(predicate)` | Facts with this predicate, highest confidence first |
| `get_triple(subject, predicate)` | Highest-confidence fact for the pair, or `None` |
| `get_above_confidence(threshold=0.8)` | Facts with `confidence >= threshold` |
| `get_neighbors(entity, direction="OUTBOUND")` | Entities directly connected (`OUTBOUND`, `INBOUND` or `ANY`) |
| `find_path(from_entity, to_entity)` | Shortest outbound path between two entities |

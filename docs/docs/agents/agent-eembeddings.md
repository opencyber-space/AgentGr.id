# Agent Embeddings — Client Developer Documentation

## Introduction

The **Agents Embeddings SDK** (`agents_embeddings`) provides one interface for generating embeddings from different backends, and a manager for registering several generators by name.

It provides:

* **Pluggable backends**:
    * **AIOS** — embedding models served as AIOS blocks, called over REST (`AIOSEmbeddingsAPI`).
    * **OpenAI** — the OpenAI Embeddings API (`OpenAIEmbeddingsGenerator`).
    * **Custom** — your own subclass of `BaseEmbeddingsGenerator`.
* **Single and batched** embedding of texts.
* **Object embedding**: embed any object exposing a text representation, keyed by its ID.
* **A registry** (`AgentEmbeddingsManager`) for addressing generators by name.

A typical workflow is:

1. **Declare a ModelItem** in the Subject Specification (optional) to record which embeddings model the agent uses.
2. **Create a generator** — AIOS-backed or OpenAI/custom.
3. **Register it** in `AgentEmbeddingsManager`.
4. **Generate embeddings** for texts or objects.

---

## Installation

The SDK lives in `libs/embeddings-sdk` and depends on `openai` and `requests`.

```bash
pip install ./libs/embeddings-sdk
```

---

## Registering Embeddings in Subject Specification

Embedding models can be recorded in the subject's `integrations.models` list using a `ModelItem`.

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ModelItem:
    llm_type: str
    llm_block_id: str
    llm_selection_query: Dict[str, Any] = field(default_factory=dict)
    llm_parameters: Dict[str, Any] = field(default_factory=dict)
```

### Example Configuration

```json
{
  "llm_type": "embeddings",
  "llm_block_id": "bge-large-embeddings-block",
  "llm_selection_query": {},
  "llm_parameters": {
    "inference_server_id": "inference-server-1",
    "batch_size": 64
  }
}
```

### Field Descriptions

| Field                     | Type   | Description                                                                 |
| ------------------------- | ------ | --------------------------------------------------------------------------- |
| **llm\_type**             | `str`  | Model kind, e.g. `"embeddings"`.                                            |
| **llm\_block\_id**        | `str`  | ID of the AIOS block (or provider model name) to use.                       |
| **llm\_selection\_query** | `dict` | Optional selector for picking a deployment.                                 |
| **llm\_parameters**       | `dict` | Backend settings, e.g. `inference_server_id`, `batch_size`.                 |

> The agents SDK does not build generators from `ModelItem` entries automatically. Read the entry from `self.subject.integrations.models` and pass its values to `register_new_generator` (see below).

---

## Import and Setup

```python
from agents_embeddings.embeddings import AgentEmbeddingsManager
from agents_embeddings.aios import AIOSEmbeddingsAPI
from agents_embeddings.custom import BaseEmbeddingsGenerator, OpenAIEmbeddingsGenerator
```

---

## AgentEmbeddingsManager

`AgentEmbeddingsManager` is a registry of named embeddings generators.

```python
mgr = AgentEmbeddingsManager()
```

### Register an AIOS-backed generator

```python
mgr.register_new_generator(
    name="bge",
    model="bge-large-embeddings-block",         # block ID of the embedding model
    inference_server_id="inference-server-1",   # or a direct URL: "http://10.0.0.5:8000"
    aios_url_map={
        "inference_server_url": "http://<inference-server-registry>",
        "blocks_db_url": "http://<blocks-db>",
    },
    default_mode="embedding",
)
```

| Argument              | Default       | Description                                                                 |
| --------------------- | ------------- | --------------------------------------------------------------------------- |
| `name`                | — (required)  | Registry name of the generator                                              |
| `model`               | — (required)  | Block ID of the embedding model                                             |
| `inference_server_id` | — (required)  | Inference server ID, looked up in the registry; or an `http(s)://` URL used directly |
| `aios_url_map`        | — (required)  | `inference_server_url` (inference server registry) and, optionally, `blocks_db_url` (blocks DB, used to verify the model exists) |
| `session_id`          | auto          | Session ID sent with each request (`embed-<uuid>`)                          |
| `overwrite`           | `False`       | Replace an existing generator with the same name (otherwise `ValueError`)   |
| `default_mode`        | `"embedding"` | `mode` value sent to the inference server                                   |

Each request is sent to `POST <inference-server>/v1/infer`:

```json
{
  "model": "bge-large-embeddings-block",
  "session_id": "embed-...",
  "seq_no": 1735689600123,
  "data": { "mode": "embedding", "gen_params": {}, "texts": ["text one", "text two"] },
  "graph": {},
  "selection_query": {}
}
```

A single text is sent as `"message"` instead of `"texts"`. The response may carry the vectors in any of `data.embeddings`, `data.embedding` (single input), `data.data[].embedding` or `data.reply.embeddings`.

### Register a custom (e.g. OpenAI) generator

```python
from openai import OpenAI

openai_gen = OpenAIEmbeddingsGenerator(
    model="text-embedding-3-small",   # default: "text-embedding-3-large"
    client=OpenAI(),                  # optional; created from OPENAI_API_KEY if omitted
)
mgr.register_custom_generator(name="openai", generator=openai_gen, overwrite=True)
```

`register_custom_generator` only accepts instances of `BaseEmbeddingsGenerator`.

### Manage generators

```python
mgr.list_generators()          # ['bge', 'openai']
mgr.has_generator("bge")       # True
gen = mgr.get_generator("bge") # KeyError if missing
mgr.unregister_generator("bge")
mgr.clear_generators()
```

---

## Generating Embeddings

### Texts

```python
vectors = mgr.embed_texts(
    name="openai",
    texts=["AI is transforming industries.", "Vector databases store embeddings."],
    batch_size=0,     # 0 = one request; > 0 = split into requests of this size
)
# -> List[List[float]], in input order
```

For AIOS generators you can also pass `seq_no`, `extra_headers`, `mode` and any extra keyword arguments. Extra arguments are sent as `gen_params`.

### Objects

Any object with an ID attribute and a method returning its text can be embedded:

```python
class Doc:
    def __init__(self, doc_id, title, body):
        self.id, self.title, self.body = doc_id, title, body

    def get_searchable_representation(self) -> str:
        return f"{self.title}\n{self.body}"

doc_vectors = mgr.embed_objects(
    name="openai",
    objects=[Doc("d1", "Intro LLMs", "Basics of LLMs."), Doc("d2", "Advanced RAG", "Retrieval.")],
    id_attr="id",
    rep_method="get_searchable_representation",
)
# -> {"d1": [...], "d2": [...]}
```

Generators can also be used directly: `gen.embed_texts([...])` and `gen.embed_objects([...])`.

Errors (failed requests, unexpected response shapes, count mismatches) raise `EmbeddingsError`.

---

## Writing a Custom Generator

Subclass `BaseEmbeddingsGenerator` and implement `embed_texts`. `embed_objects` is inherited.

```python
from typing import Any, List, Sequence
from agents_embeddings.custom import BaseEmbeddingsGenerator


class HashEmbeddings(BaseEmbeddingsGenerator):
    def __init__(self, dims: int = 8, **kwargs: Any):
        super().__init__(model="hash", **kwargs)
        self.dims = dims

    def embed_texts(self, texts: Sequence[str], *, batch_size: int = 0, **kwargs: Any) -> List[List[float]]:
        return [[float((hash(t) >> i) & 1) for i in range(self.dims)] for t in texts]


mgr.register_custom_generator(name="hash", generator=HashEmbeddings(dims=16))
```

`BaseEmbeddingsGenerator.__init__` takes keyword-only `model`, `session_id` and `logger`.

---

## Using Embeddings with a Vector Database

Generators plug directly into the vector database add-on (`agent_addons.embeddings_store.EmbeddingsSDK`) as the `embedder`:

```python
from agent_addons.embeddings_store import EmbeddingsSDK

vdb = EmbeddingsSDK(provider="weaviate", weaviate_url="http://localhost:8080")
vdb.insert_texts("KnowledgeBase", ["hello world"], embedder=mgr.get_generator("openai"))
```

See [Accessing Vector Databases](agent-vector-storage.md).

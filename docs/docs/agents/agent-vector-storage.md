# Vector Database Integration — Client Developer Documentation

## Introduction

The **Vector Database** add-on gives agents one interface for storing and searching embeddings (semantic search, recommendation, retrieval-augmented generation). It is provided by the `EmbeddingsSDK` class in the `agent_addons` package.

Supported providers:

* **Weaviate** (via the `weaviate-client` v3 `weaviate.Client` API)
* **Pinecone** (serverless indexes)

`EmbeddingsSDK` provides:

* Collection (Weaviate class / Pinecone index) management.
* Vector CRUD and similarity search with metadata filters.
* **Text-based** helpers that embed text with an embeddings generator before inserting or searching.
* Ingestion of pre-computed vectors from local JSON/JSONL files or S3.

The same package includes `AgentRAG`, a small retrieval-augmented generation helper built on `EmbeddingsSDK`.

Typical workflow:

1. **Declare an `AddonItem`** in the Subject Specification to record the vector DB (optional).
2. **Create an `EmbeddingsSDK` client** for Weaviate or Pinecone.
3. **Create a collection**, then **insert vectors** (or texts) with optional metadata.
4. **Search** by vector or by text, with optional filters.
5. **Retrieve, update, or delete** vectors as needed.

---

## Installation

`EmbeddingsSDK` is part of `agent_addons` (`libs/agents-addons`), which installs `weaviate-client`, `pinecone-client` and `boto3`.

```bash
pip install ./libs/agents-addons
```

---

## Registering Vector DB in Subject Specification

Vector databases can be recorded in the subject's `integrations.addons` list using `AddonItem`.

### Data Class Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class AddonItem:
    addon_id: str
    addon_type: str
    addon_config: Dict[str, Any] = field(default_factory=dict)
```

### Example Configuration

```json
{
  "addon_id": "vector-primary",
  "addon_type": "vector_db",
  "addon_config": {
    "provider": "weaviate",
    "weaviate_url": "http://weaviate.default.svc.cluster.local:8080",
    "metric": "cosine"
  }
}
```

### Field Descriptions

| Field             | Type             | Description                                                              |
| ----------------- | ---------------- | ------------------------------------------------------------------------ |
| **addon\_id**     | `str`            | Unique identifier for this add-on.                                       |
| **addon\_type**   | `str`            | Add-on kind, e.g. `"vector_db"`.                                         |
| **addon\_config** | `Dict[str, Any]` | Client settings. Use the `EmbeddingsSDK` constructor arguments as keys (see below). |

> The agents SDK does not create clients from add-on entries automatically. Read the entry from `self.subject.integrations.addons` in your agent and build the client yourself, e.g. `EmbeddingsSDK(**addon.addon_config)`.

---

## Import and Setup

```python
from agent_addons.embeddings_store import EmbeddingsSDK
```

### Weaviate

```python
vdb = EmbeddingsSDK(
    provider="weaviate",
    weaviate_url="http://localhost:8080",
    weaviate_api_key=None,      # optional
    metric="cosine",
)
```

### Pinecone

```python
vdb = EmbeddingsSDK(
    provider="pinecone",
    pinecone_api_key="pc-...",
    dimension=1536,             # required to create indexes
    metric="cosine",
    pinecone_cloud="aws",
    pinecone_region="us-east-1",
)
```

| Argument              | Default       | Description                                                        |
| --------------------- | ------------- | ------------------------------------------------------------------ |
| `provider`            | — (required)  | `"weaviate"` or `"pinecone"` (anything else raises `ValueError`)   |
| `dimension`           | `None`        | Vector dimension (used when creating Pinecone indexes)             |
| `metric`              | `"cosine"`    | Distance metric (Weaviate class distance / Pinecone index metric)  |
| `weaviate_url`        | `None`        | Required for Weaviate                                              |
| `weaviate_api_key`    | `None`        | Optional Weaviate API key                                          |
| `pinecone_api_key`    | `None`        | Required for Pinecone                                              |
| `pinecone_index_name` | `None`        | Stored on the client for reference                                 |
| `pinecone_cloud`      | `"aws"`       | Serverless cloud for new indexes                                   |
| `pinecone_region`     | `"us-east-1"` | Serverless region for new indexes                                  |

---

## Usage Guide

### A. Collections

A *collection* is a Weaviate class or a Pinecone index.

```python
vdb.create_collection("KnowledgeBase")
vdb.list_collections()            # ['KnowledgeBase', ...]
vdb.delete_collection("KnowledgeBase")
```

* **Weaviate:** creates a class with `vectorizer: "none"` (you bring your own embeddings), an HNSW index and the configured distance.
* **Pinecone:** creates a serverless index with `dimension` and `metric`.

### B. Insert vectors

```python
vdb.insert_vectors("KnowledgeBase", [
    {"id": "4b7c1c1e-6a8e-4b6c-9a0e-2f1a3b4c5d6e", "values": [0.12, 0.98, ...], "metadata": {"text": "Doc A", "source": "wiki"}},
    {"id": "9f0e2d3c-1b2a-4c5d-8e7f-6a5b4c3d2e1f", "values": [0.33, 0.71, ...]},
])
```

* **Weaviate:** objects are batch-added with the given `id` as UUID (Weaviate requires UUIDs), `values` as the vector and `metadata` as properties.
* **Pinecone:** the list is upserted as-is into the index.

### C. Get, update and delete

```python
vdb.get_vector("KnowledgeBase", vid)                    # Weaviate object / Pinecone fetch result (dict)
vdb.update_vector("KnowledgeBase", vid, new_values, metadata={"source": "updated"})
vdb.delete_vector("KnowledgeBase", vid)
```

### D. Similarity search

```python
results = vdb.search("KnowledgeBase", query_vector, top_k=5, filters=None)
```

`filters` is passed to the provider unchanged:

* **Weaviate:** a `where` filter, e.g. `{"path": ["source"], "operator": "Equal", "valueText": "wiki"}`. The result is the raw GraphQL response (`{"data": {"Get": {"KnowledgeBase": [...]}}}`).
* **Pinecone:** a metadata filter, e.g. `{"source": {"$eq": "wiki"}}`. The result is the raw query response (`matches` with `id`, `score`, `metadata`).

---

### E. Text-based helpers

These helpers take an `embedder`: any object with `embed_texts(texts, batch_size=...) -> List[List[float]]`, such as the generators from the [Embeddings SDK](agent-eembeddings.md).

```python
from agents_embeddings.custom import OpenAIEmbeddingsGenerator

embedder = OpenAIEmbeddingsGenerator(model="text-embedding-3-small")   # uses OPENAI_API_KEY

# Items can be strings or dicts with "text" (+ optional "id", "metadata")
vdb.insert_texts("KnowledgeBase", [
    "AI is transforming industries.",
    {"id": "4b7c1c1e-...", "text": "Vector DBs store embeddings.", "metadata": {"source": "notes"}},
], embedder=embedder, batch_size=128)

vdb.update_texts("KnowledgeBase", [{"id": "4b7c1c1e-...", "text": "Updated text"}], embedder=embedder)

hits = vdb.search_text("KnowledgeBase", "What stores embeddings?", embedder=embedder, top_k=3)

many = vdb.bulk_search_texts("KnowledgeBase", ["query one", "query two"], embedder=embedder, top_k=3)
```

* Items without an `id` get a random hex ID (`uuid4().hex`).
* `insert_texts` stores only the item's `metadata`, not the text itself. Include the text in `metadata` if you need it back from search results.
* Use `id_key`, `text_key` and `metadata_key` to map other field names, and `preprocess` to transform text before embedding.

---

### F. Ingest pre-computed vectors

The file or S3 object must be a JSON array or JSONL of `{"id", "values", "metadata"}` records (or anything `transform` turns into that).

```python
vdb.ingest_from_file("KnowledgeBase", "/data/vectors.jsonl", batch_size=100)

vdb.ingest_from_s3("KnowledgeBase", bucket="my-bucket", key="vectors/part-0001.jsonl",
                   region="us-east-1", transform=lambda r: {"id": r["uuid"], "values": r["emb"], "metadata": r["meta"]})
```

S3 ingestion uses the default `boto3` credential chain; the region defaults to `AWS_REGION`.

---

## Retrieval-Augmented Generation (`AgentRAG`)

`AgentRAG` combines an `EmbeddingsSDK`, an embedder and an LLM to answer questions from stored documents.

```python
from agent_addons.rag import AgentRAG
from agents_llm_lite.custom import OpenAIInference

llm = OpenAIInference(model="gpt-4o-mini")

rag = AgentRAG(
    collection="KnowledgeBase",
    embeddings_sdk=vdb,
    embedder=embedder,
    llm=llm,                     # an agents_llm_lite provider, e.g. OpenAIInference(model="gpt-4o-mini")
    text_field="text",           # metadata field holding the chunk text
    default_top_k=5,
    max_context_chars=12_000,
    chunk_size=1200,
    chunk_overlap=200,
)

rag.add_texts(["Acme was founded in 1999.", {"text": "RetailCo is based in Delaware."}])
rag.add_documents_chunked([{"id": "contract-1", "text": long_contract_text, "metadata": {"type": "contract"}}])

chunks = rag.retrieve("Where is RetailCo based?", top_k=3)   # List[RetrievedChunk(id, score, metadata, text)]

result = rag.ask("Where is RetailCo based?")
print(result["answer"])
print(result["sources"])      # chunks that fit in the context budget
```

* `add_texts` and `add_documents_chunked` store the text in `metadata[text_field]`, so it is available at retrieval time. Chunk IDs are `<doc id>__0000`, `<doc id>__0001`, …, and each chunk's metadata includes `chunk_index` and `parent_id`.
* `retrieve` normalizes Weaviate and Pinecone results into `RetrievedChunk` objects, sorted by score (higher is better). Weaviate distances are converted to `1 / (1 + distance)`.
* `ask` packs retrieved chunks into the prompt up to `max_context_chars`, asks the LLM to cite them as `[1]`, `[2]`, … (`cite_inline=True`), and returns `{"answer", "sources", "retrieved"}`. Pass `prompt_template` (with `{context}` and `{question}`) to customize the prompt, and `callback` to extract the answer text from your LLM's response (default: OpenAI `choices[0].message.content`).

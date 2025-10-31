# Agent generator

## Agents Embedding generator
 
### Introduction

The **Agents Embedding** module provides a unified interface to generate embeddings from different backends, such as OpenAI, Hugging Face, and remote AIOS blocks via gRPC. This abstraction allows you to:

* Easily switch between multiple embedding providers.
* Register and configure custom embedding generators.
* Generate embeddings for single or batched text inputs.
* Use a consistent API for local or remote model inference.

The design is based on the `AbstractEmbeddingGenerator` base class and is extended by implementations such as:

| Generator Class                 | Backend            | Notes                                                                |
| ------------------------------- | ------------------ | -------------------------------------------------------------------- |
| `OpenAIEmbeddingGenerator`      | OpenAI API         | Uses OpenAI’s hosted embedding models like `text-embedding-ada-002`  |
| `HuggingFaceEmbeddingGenerator` | Hugging Face       | Uses local transformer models, conditional on `PYTORCH_TRANSFORMERS` |
| `AIOSEmbeddings`                | Remote AIOS Blocks | Uses gRPC to communicate with AIOS-managed embedding services        |

A central `EmbeddingGeneratorManager` class enables registration and invocation of these generators by name, allowing for seamless orchestration in applications where multiple embedding strategies may coexist.

---

### Importing

To use the embedding generators and the manager, import them as follows:

```python
from agent_sdk.embeddings.generator import *
```

This will give you access to:

* `AbstractEmbeddingGenerator` – the base class interface.
* `OpenAIEmbeddingGenerator` – implementation using OpenAI APIs.
* `HuggingFaceEmbeddingGenerator` – implementation using local Hugging Face models.
* `AIOSEmbeddings` – implementation using AIOS block over gRPC.
* `EmbeddingGeneratorManager` – manager to register and orchestrate multiple generators.

---

### `EmbeddingGeneratorManager`

The `EmbeddingGeneratorManager` class acts as a central controller to manage multiple embedding generators. Each generator is registered with a unique name and must implement the `AbstractEmbeddingGenerator` interface.

#### Class Definition

```python
class EmbeddingGeneratorManager:
    def __init__(self):
        self.generators = {}

    def register_generator(self, name: str, generator: AbstractEmbeddingGenerator)
    def generate(self, name: str, text: str)
    def generate_batch(self, name: str, texts: list)
    def set_parameter(self, name: str, key: str, value)
    def get_parameter(self, name: str, key: str)
```

#### Methods

| Method                                | Description                                                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `register_generator(name, generator)` | Registers a generator instance under a unique name. The generator must inherit from `AbstractEmbeddingGenerator`. |
| `generate(name, text)`                | Generates an embedding for the given `text` using the specified generator.                                        |
| `generate_batch(name, texts)`         | Generates embeddings for a list of `texts` using the specified generator.                                         |
| `set_parameter(name, key, value)`     | Sets a custom parameter for a registered generator.                                                               |
| `get_parameter(name, key)`            | Retrieves a parameter value for a registered generator.                                                           |

#### Example Usage

```python
manager = EmbeddingGeneratorManager()

# Register an OpenAI generator
openai_gen = OpenAIEmbeddingGenerator(api_key="your-api-key")
manager.register_generator("openai", openai_gen)

# Generate a single embedding
embedding = manager.generate("openai", "What is AI?")

# Generate embeddings for a batch of texts
batch_embeddings = manager.generate_batch("openai", ["Hello", "World"])
```
---

### Writing Custom Embeddings Generator

To create your own embedding generator, you must implement the `AbstractEmbeddingGenerator` interface. This ensures compatibility with the `EmbeddingGeneratorManager` and consistent behavior across all generators.

#### Base Interface

```python
from abc import ABC, abstractmethod

class AbstractEmbeddingGenerator(ABC):
    def __init__(self):
        self.parameters = {}

    @abstractmethod
    def generate(self, text: str):
        pass

    @abstractmethod
    def generate_batch(self, texts: list):
        pass

    def set_parameter(self, key: str, value):
        self.parameters[key] = value

    def get_parameter(self, key: str):
        return self.parameters.get(key, None)
```

Your custom generator must implement:

| Method                  | Description                                               |
| ----------------------- | --------------------------------------------------------- |
| `generate(text)`        | Returns an embedding for a single input string.           |
| `generate_batch(texts)` | Returns a list of embeddings for a list of input strings. |

You can optionally use `set_parameter` and `get_parameter` to support configurable behavior.

---

#### Example: Dummy Generator

```python
from agent_sdk.embeddings.generator import AbstractEmbeddingGenerator

class DummyEmbeddingGenerator(AbstractEmbeddingGenerator):
    def generate(self, text: str):
        return [len(text)]  # Example: embedding is just the length

    def generate_batch(self, texts: list):
        return [[len(t)] for t in texts]
```

#### Registering Your Custom Generator

```python
manager = EmbeddingGeneratorManager()
dummy = DummyEmbeddingGenerator()
manager.register_generator("dummy", dummy)

result = manager.generate("dummy", "Hello AI")
print(result)  # Output: [8]
```

This makes it easy to integrate custom logic, local models, or remote services without changing the interface or manager logic.

---


Here’s the complete documentation for your vector database module:

---

## Vector Databases

### Overview

The vector database module provides a pluggable interface to multiple backends for storing and querying high-dimensional vectors (embeddings). Each backend implements a consistent interface built on top of `BaseVectorDB`, enabling:

* Insertion of vectors with metadata
* Filtered similarity search
* Retrieval and deletion
* Count and reset operations

---

### Available Vector Databases

| Database     | Class Name         | Type         | Storage Location | Filtering Support | Notes                                             |
| ------------ | ------------------ | ------------ | ---------------- | ----------------- | ------------------------------------------------- |
| **FAISS**    | `FaissEmbeddings`  | In-memory    | Local            | No              | Lightweight, fast for prototyping, no persistence |
| **Milvus**   | `MilvusEmbeddings` | Distributed  | Remote Cluster   | Yes             | Powerful, scalable, production-grade              |
| **Weaviate** | `WeaviateDB`       | Hosted/Local | Local/Remote     | Yes (GraphQL)   | GraphQL filtering, rich schema support            |
| **LanceDB**  | `LanceDB`          | Local        | Filesystem       | Yes             | Optimized for local storage, columnar format      |
| **Qdrant**   | `QdrantDB`         | Hosted/Local | Local/Remote     | Yes             | Efficient, scalable, production-ready             |

---

### FAISS

#### Description

FAISS is an in-memory, non-persistent vector search library developed by Facebook. It supports multiple indexing strategies but does not support metadata or deletion.

#### Import

```python
from agent_sdk.embeddings.db import FaissEmbeddings
```

#### Usage

```python
db = FaissEmbeddings(dimension=128)
db.add_embeddings([[0.1]*128, [0.2]*128], ids=[1, 2])
results = db.search([0.1]*128, top_k=2)
```

#### Limitations

* In-memory only (no disk storage)
* No support for deleting entries
* No metadata or filtering support

---

### Milvus

#### Description

Milvus is a distributed, production-ready vector database optimized for performance and scalability. It supports filtering and persistent storage.

#### Import

```python
from agent_sdk.embeddings.db import MilvusEmbeddings
```

#### Usage

```python
db = MilvusEmbeddings(host="localhost", port="19530", collection_name="my_collection")
db.create_index(dimension=128)
db.add_embeddings([[0.1]*128], ids=[101])
results = db.search([0.1]*128, top_k=2)
embedding = db.get_embedding(101)
db.delete_embeddings([101])
```

#### Features

* Persistent storage
* Advanced filtering
* Scalable and highly performant

---

### Weaviate

#### Description

Weaviate is a vector-native database that uses a GraphQL interface and supports both local and cloud deployment. Supports metadata filtering and linking.

#### Import

```python
from agent_sdk.embeddings.db import WeaviateDB
```

#### Usage

```python
db = WeaviateDB(config=config)
db.set_embedder(my_embedder)
db._initialize()
db.add(documents, metadatas, ids)
results = db.query(input_query="example", n_results=3, where={"doc_id": "123"}, citations=True)
```

#### Features

* GraphQL filtering
* Linkable metadata schemas
* Extensible and schema-aware

---

### LanceDB

#### Description

LanceDB is a local vector database using Apache Arrow for columnar storage. It is ideal for local use cases and supports metadata-based filtering.

#### Import

```python
from agent_sdk.embeddings.db import LanceDB
```

#### Usage

```python
db = LanceDB(config=config)
db.set_embedder(my_embedder)
db._initialize()
db.add(documents, metadatas, ids)
results = db.query("semantic search", n_results=3, citations=True)
```

#### Features

* Local file storage
* Simple SQL-like filtering
* Lightweight and easy to use

---

### Qdrant

#### Description

Qdrant is a high-performance, vector-native database with support for metadata filtering, efficient similarity search, and production-readiness.

#### Import

```python
from agent_sdk.embeddings.db import QdrantDB
```

#### Usage

```python
db = QdrantDB(config=config)
db.set_embedder(my_embedder)
db._initialize()
db.add(documents, metadatas, ids)
results = db.query("query text", n_results=3, where={"topic": "ai"}, citations=True)
```

#### Features

* Disk-backed or in-memory storage
* Fast filtering and indexing
* Fully supports batch ingestion and updates

---

## End-to-End Example: Embedding + Vector Search Pipeline

### Goal

We want to:

1. Initialize an embedding generator (e.g., OpenAI)
2. Register it in an `EmbeddingGeneratorManager`
3. Use it to generate embeddings for documents
4. Store those embeddings in a vector database (e.g., QdrantDB)
5. Perform similarity search on the stored data
6. Retrieve results with metadata

---

### Assumptions

* OpenAI API key is available in your environment (`OPENAI_API_KEY`)
* Qdrant server is running and accessible (`QDRANT_URL`)
* You have installed necessary dependencies:

```bash
pip install openai qdrant-client tqdm
```

---

### Code Example

```python
from agent_sdk.embeddings.generator import OpenAIEmbeddingGenerator, EmbeddingGeneratorManager
from agent_sdk.embeddings.db import QdrantDB
from embedchain.config.vector_db.qdrant import QdrantDBConfig

# 1. Create and register embedding generator
openai_gen = OpenAIEmbeddingGenerator(api_key=os.getenv("OPENAI_API_KEY"))
manager = EmbeddingGeneratorManager()
manager.register_generator("openai", openai_gen)

# 2. Generate embeddings for sample documents
documents = [
    "What is artificial intelligence?",
    "The capital of France is Paris.",
    "Machine learning is a subset of AI."
]
metadatas = [
    {"category": "ai"}, {"category": "geography"}, {"category": "ai"}
]
ids = ["doc1", "doc2", "doc3"]

# Generate embeddings via manager
embeddings = manager.generate_batch("openai", documents)

# 3. Initialize vector DB
qdrant_config = QdrantDBConfig(collection_name="knowledge_base")
vectordb = QdrantDB(config=qdrant_config)
vectordb.set_embedder(openai_gen)  # embedder is needed
vectordb._initialize()

# 4. Add data to the vector DB
vectordb.add(documents=documents, metadatas=metadatas, ids=ids)

# 5. Run a similarity query
query = "Tell me about AI"
results = vectordb.query(
    input_query=query,
    n_results=2,
    where={"category": "ai"},
    citations=True
)

# 6. Display results
for context, metadata in results:
    print(f"Matched: {context}")
    print(f"Metadata: {metadata}")
```

---

### Output (Example)

```
Matched: What is artificial intelligence?
Metadata: {'category': 'ai', 'score': 0.87}

Matched: Machine learning is a subset of AI.
Metadata: {'category': 'ai', 'score': 0.81}
```

---
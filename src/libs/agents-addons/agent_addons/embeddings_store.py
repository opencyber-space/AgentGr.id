# embeddings_sdk.py
import os
import json
import logging
from typing import Dict, Any, List, Optional, Union, Iterable, Callable, Sequence

import weaviate
from pinecone import Pinecone, ServerlessSpec
import uuid

import requests

try:
    import boto3  # optional, for ingest_from_s3
except Exception:
    boto3 = None

logger = logging.getLogger("EmbeddingsSDK")
logging.basicConfig(level=logging.INFO)


class EmbeddingsSDK:
    

    def __init__(
        self,
        provider: str,
        # Common
        dimension: Optional[int] = None,
        metric: str = "cosine",
        # --- Weaviate ---
        weaviate_url: Optional[str] = None,
        weaviate_api_key: Optional[str] = None,
        # --- Pinecone ---
        pinecone_api_key: Optional[str] = None,
        pinecone_index_name: Optional[str] = None,
        pinecone_cloud: str = "aws",
        pinecone_region: str = "us-east-1",
    ):
        self.provider = provider.lower()
        if self.provider not in ("weaviate", "pinecone"):
            raise ValueError("provider must be 'weaviate' or 'pinecone'")

        self.dimension = dimension
        self.metric = metric

        if self.provider == "weaviate":
            if not weaviate_url:
                raise ValueError("weaviate_url is required")
            auth = None
            if weaviate_api_key:
                auth = weaviate.AuthApiKey(api_key=weaviate_api_key)
            self.client = weaviate.Client(weaviate_url, auth_client_secret=auth)
        else:
            if not pinecone_api_key:
                raise ValueError("pinecone_api_key is required")
            self.pinecone = Pinecone(api_key=pinecone_api_key)
            self.index_name = pinecone_index_name
            self.cloud = pinecone_cloud
            self.region = pinecone_region

    # ---------- Collection / Index management ----------

    def create_collection(self, name: str):
        if self.provider == "weaviate":
            schema = {
                "class": name,
                "vectorizer": "none",  # assume you bring your own embeddings
                "vectorIndexType": "hnsw",
                "vectorIndexConfig": {"distance": self.metric},
            }
            self.client.schema.create_class(schema)
            logger.info(f"Weaviate class '{name}' created.")
        else:
            spec = ServerlessSpec(cloud=self.cloud, region=self.region)
            self.pinecone.create_index(name, dimension=self.dimension, metric=self.metric, spec=spec)
            logger.info(f"Pinecone index '{name}' created.")

    def delete_collection(self, name: str):
        if self.provider == "weaviate":
            self.client.schema.delete_class(name)
            logger.info(f"Weaviate class '{name}' deleted.")
        else:
            self.pinecone.delete_index(name)
            logger.info(f"Pinecone index '{name}' deleted.")

    def list_collections(self) -> List[str]:
        if self.provider == "weaviate":
            return [c["class"] for c in self.client.schema.get()["classes"]]
        else:
            return [i["name"] for i in self.pinecone.list_indexes()]

    # ---------- CRUD ----------

    def insert_vectors(self, collection: str, vectors: List[Dict[str, Any]]):
        """
        vectors format:
        [
            {"id": "v1", "values": [..], "metadata": {...}},
            {"id": "v2", "values": [..]}
        ]
        """
        if self.provider == "weaviate":
            with self.client.batch as batch:
                for v in vectors:
                    batch.add_data_object(
                        v.get("metadata", {}),
                        class_name=collection,
                        uuid=v["id"],
                        vector=v["values"],
                    )
        else:
            index = self.pinecone.Index(collection)
            index.upsert(vectors)

    def get_vector(self, collection: str, vid: str) -> Optional[Dict[str, Any]]:
        if self.provider == "weaviate":
            return self.client.data_object.get(vid, class_name=collection)
        else:
            index = self.pinecone.Index(collection)
            return index.fetch([vid]).to_dict()

    def delete_vector(self, collection: str, vid: str):
        if self.provider == "weaviate":
            self.client.data_object.delete(vid, class_name=collection)
        else:
            index = self.pinecone.Index(collection)
            index.delete(ids=[vid])

    def update_vector(self, collection: str, vid: str, values: List[float], metadata: Optional[Dict[str, Any]] = None):
        if self.provider == "weaviate":
            self.client.data_object.update(
                uuid=vid,
                class_name=collection,
                vector=values,
                properties=metadata or {},
            )
        else:
            index = self.pinecone.Index(collection)
            index.upsert([{"id": vid, "values": values, "metadata": metadata or {}}])

    # ---------- Search ----------

    def search(self, collection: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None):
        if self.provider == "weaviate":
            res = self.client.query.get(collection, ["*"]).with_near_vector({"vector": query_vector}).with_limit(top_k)
            if filters:
                res = res.with_where(filters)
            return res.do()
        else:
            index = self.pinecone.Index(collection)
            return index.query(vector=query_vector, top_k=top_k, filter=filters or {})

    
    def _normalize_items_to_records(
        self,
        items: Sequence[Union[str, Dict[str, Any]]],
        *,
        id_key: str = "id",
        text_key: str = "text",
        metadata_key: str = "metadata",
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
      
        out: List[Dict[str, Any]] = []
        for it in items:
            if isinstance(it, str):
                txt = preprocess(it) if preprocess else it
                out.append({"id": uuid.uuid4().hex, "text": txt, "metadata": {}})
            elif isinstance(it, dict):
                if text_key not in it or not isinstance(it[text_key], str):
                    raise ValueError(f"Each dict item must contain a string '{text_key}' field.")
                txt = preprocess(it[text_key]) if preprocess else it[text_key]
                _id = str(it.get(id_key) or uuid.uuid4().hex)
                md = it.get(metadata_key) or {}
                if not isinstance(md, dict):
                    raise ValueError(f"'{metadata_key}' must be a dict when provided.")
                out.append({"id": _id, "text": txt, "metadata": md})
            else:
                raise ValueError("Each item must be either a string or a dict with 'text'.")
        return out

    def _batch_iter(self, seq: Sequence[Any], batch_size: int) -> Iterable[Sequence[Any]]:
        if batch_size and batch_size > 0:
            for i in range(0, len(seq), batch_size):
                yield seq[i : i + batch_size]
        else:
            yield seq

    # ---------- Ingest (text-based) ----------

    def insert_texts(
        self,
        collection: str,
        items: Sequence[Union[str, Dict[str, Any]]],
        *,
        embedder: Any,  # e.g., OpenAIEmbeddingsGenerator with embed_texts()
        id_key: str = "id",
        text_key: str = "text",
        metadata_key: str = "metadata",
        batch_size: int = 128,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> None:
        
        records = self._normalize_items_to_records(
            items,
            id_key=id_key,
            text_key=text_key,
            metadata_key=metadata_key,
            preprocess=preprocess,
        )

        # Embed in batches to control API/latency and memory
        for batch in self._batch_iter(records, batch_size):
            texts = [r["text"] for r in batch]
            vectors = embedder.embed_texts(texts, batch_size=batch_size)

            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"Embedder returned {len(vectors)} vectors for {len(batch)} texts."
                )

            payload = [
                {"id": r["id"], "values": vec, "metadata": r["metadata"]}
                for r, vec in zip(batch, vectors)
            ]
            self.insert_vectors(collection, payload)

    def update_texts(
        self,
        collection: str,
        items: Sequence[Union[str, Dict[str, Any]]],
        *,
        embedder: Any,
        id_key: str = "id",
        text_key: str = "text",
        metadata_key: str = "metadata",
        batch_size: int = 128,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> None:
        """
        Same as insert_texts but uses the SDK's update mechanism per id.
        (Pinecone: upsert again. Weaviate: data_object.update.)
        """
        records = self._normalize_items_to_records(
            items,
            id_key=id_key,
            text_key=text_key,
            metadata_key=metadata_key,
            preprocess=preprocess,
        )
        for batch in self._batch_iter(records, batch_size):
            texts = [r["text"] for r in batch]
            vectors = embedder.embed_texts(texts, batch_size=batch_size)
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"Embedder returned {len(vectors)} vectors for {len(batch)} texts."
                )
            for r, vec in zip(batch, vectors):
                self.update_vector(collection, r["id"], vec, r["metadata"])

    # ---------- Search (text-based) ----------

    def search_text(
        self,
        collection: str,
        query_text: str,
        *,
        embedder: Any,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        preprocess: Optional[Callable[[str], str]] = None,
    ):
        """
        Embed a single query string via `embedder` and run vector search.
        """
        q = preprocess(query_text) if preprocess else query_text
        vecs = embedder.embed_texts([q], batch_size=0)
        if not vecs or not isinstance(vecs[0], list):
            raise RuntimeError("Embedder returned no vectors for the query.")
        return self.search(collection, vecs[0], top_k=top_k, filters=filters)

    def bulk_search_texts(
        self,
        collection: str,
        query_texts: Sequence[str],
        *,
        embedder: Any,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        batch_size: int = 64,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> List[Any]:
       
        if not query_texts:
            return []
        prepped = [preprocess(t) if preprocess else t for t in query_texts]
        out: List[Any] = []
        for batch in self._batch_iter(prepped, batch_size):
            vecs = embedder.embed_texts(list(batch), batch_size=batch_size)
            if len(vecs) != len(batch):
                raise RuntimeError(
                    f"Embedder returned {len(vecs)} vectors for {len(batch)} queries."
                )
            for v in vecs:
                out.append(self.search(collection, v, top_k=top_k, filters=filters))
        return out

    # ---------- Ingestion from JSON & S3 ----------

    @staticmethod
    def _iter_json(path: str) -> Iterable[Dict[str, Any]]:
        with open(path, "r") as f:
            first_char = f.read(1)
            f.seek(0)
            if first_char == "[":
                for obj in json.load(f):
                    yield obj
            else:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    def ingest_from_file(self, collection: str, path: str, transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None, batch_size: int = 100):
        buf: List[Dict[str, Any]] = []
        for obj in self._iter_json(path):
            if transform:
                obj = transform(obj)
            buf.append(obj)
            if len(buf) >= batch_size:
                self.insert_vectors(collection, buf)
                buf = []
        if buf:
            self.insert_vectors(collection, buf)

    def ingest_from_s3(self, collection: str, bucket: str, key: str, region: Optional[str] = None, transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None, batch_size: int = 100):
        if boto3 is None:
            raise RuntimeError("boto3 not installed")

        session = boto3.session.Session(region_name=region or os.getenv("AWS_REGION"))
        s3 = session.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read().decode("utf-8")

        def gen():
            body_stripped = body.lstrip()
            if body_stripped.startswith("["):
                for x in json.loads(body):
                    yield transform(x) if transform else x
            else:
                for line in body.splitlines():
                    if not line.strip():
                        continue
                    x = json.loads(line)
                    yield transform(x) if transform else x

        buf: List[Dict[str, Any]] = []
        for obj in gen():
            buf.append(obj)
            if len(buf) >= batch_size:
                self.insert_vectors(collection, buf)
                buf = []
        if buf:
            self.insert_vectors(collection, buf)

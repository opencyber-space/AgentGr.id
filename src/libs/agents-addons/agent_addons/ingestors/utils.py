import io
import os
import re
import math
import json
import time
import zlib
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Protocol, Callable

logger = logging.getLogger("IngestionCore")
logging.basicConfig(level=logging.INFO)

# ----------------------
# Shared utilities
# ----------------------

def stable_id(*parts: str) -> str:
    """Deterministic ID from parts (bucket/key/offset/etc)."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h

def l2_normalize_inplace(vectors: List[List[float]]) -> None:
    for v in vectors:
        s = math.sqrt(sum(x * x for x in v)) or 1.0
        for i in range(len(v)):
            v[i] = v[i] / s

@dataclass
class VectorRow:
    id: str
    values: List[float]
    metadata: Dict[str, Any]

class EmbeddingsSink(Protocol):
    """Minimal sink interface shared by Weaviate and Pinecone adapters."""
    def insert_vectors(self, collection: str, payload: List[Dict[str, Any]]) -> None: ...

# ----------------------
# Chunking
# ----------------------

class Chunker:
    """
    Simple length-based chunker with overlap.
    Works well as a default; swap for token-aware if needed.
    """
    def __init__(self, *, max_chars: int = 1200, overlap: int = 150):
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> List[Tuple[int, str]]:
        text = text or ""
        if not text:
            return []
        chunks: List[Tuple[int, str]] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(n, start + self.max_chars)
            chunk = text[start:end]
            chunks.append((start, chunk))
            if end == n:
                break
            start = end - self.overlap
            if start < 0:
                start = 0
        return chunks


class ContentParser:
   
    def __init__(self):
        pass

    def parse(self, *, data: bytes, key: str, content_type: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        ext = (os.path.splitext(key)[1] or "").lower()

        if content_type:
            ct = content_type.lower()
        else:
            # naive content-type inference by extension
            if ext in [".pdf"]:
                ct = "application/pdf"
            elif ext in [".docx"]:
                ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif ext in [".txt", ".md", ".log"]:
                ct = "text/plain"
            elif ext in [".json"]:
                ct = "application/json"
            else:
                ct = "application/octet-stream"

        if ct == "application/pdf":
            return self._parse_pdf(data), {"source_ext": "pdf", "source_key": key}
        if ct.endswith("wordprocessingml.document") or ext == ".docx":
            return self._parse_docx(data), {"source_ext": "docx", "source_key": key}
        if ct.startswith("text/") or ext in (".txt", ".md", ".log"):
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = data.decode("latin-1", errors="replace")
            return text, {"source_ext": "txt", "source_key": key}
        if ct == "application/json" or ext == ".json":
            try:
                obj = json.loads(data.decode("utf-8", errors="replace"))
            except Exception:
                obj = {}
            return self._flatten_json(obj), {"source_ext": "json", "source_key": key}
        # default: try text
        try:
            t = data.decode("utf-8", errors="replace")
            return t, {"source_ext": ext.lstrip("."), "source_key": key}
        except Exception:
            return "", {"source_ext": ext.lstrip("."), "source_key": key}

    def _parse_pdf(self, data: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            parts: List[str] = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            return "\n".join(parts).strip()
        except Exception as e:
            logger.exception(f"PDF parse failed: {e}")
            return ""

    def _parse_docx(self, data: bytes) -> str:
        try:
            from docx import Document
            bio = io.BytesIO(data)
            doc = Document(bio)
            return "\n".join(p.text for p in doc.paragraphs if p.text).strip()
        except Exception as e:
            logger.exception(f"DOCX parse failed: {e}")
            return ""

    def _flatten_json(self, obj: Any, *, sep: str = " ") -> str:
        # simple textualization of JSON
        try:
            if isinstance(obj, dict):
                parts = []
                for k, v in obj.items():
                    parts.append(f"{k}: {self._flatten_json(v, sep=sep)}")
                return sep.join(parts)
            if isinstance(obj, list):
                return sep.join(self._flatten_json(x, sep=sep) for x in obj)
            if obj is None:
                return ""
            return str(obj)
        except Exception:
            return ""

# ----------------------
# Ingestion base
# ----------------------

class BaseIngestor:
    """
    Base class shared by S3 and Redis ingestors.
    """
    def __init__(
        self,
        *,
        sink: EmbeddingsSink,
        model,  # your EmbeddingModel
        collection: str,
        chunker: Optional[Chunker] = None,
        parser: Optional[ContentParser] = None,
        normalize: bool = False,
        batch_size: int = 128,
        metadata_builder: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        retry_times: int = 3,
        retry_backoff: float = 1.5,
    ):
        self.sink = sink
        self.model = model
        self.collection = collection
        self.chunker = chunker or Chunker()
        self.parser = parser or ContentParser()
        self.normalize = normalize
        self.batch_size = max(1, batch_size)
        self.metadata_builder = metadata_builder or (lambda m: m)
        self.retry_times = retry_times
        self.retry_backoff = retry_backoff

    def _embed_and_upsert(self, rows: List[VectorRow]) -> None:
        # batching for model + sink
        idx = 0
        while idx < len(rows):
            batch = rows[idx: idx + self.batch_size]
            texts = [r.metadata.get("__text__", "") for r in batch]  # store transiently for embedding
            # embed
            vectors = self.model.embed_texts(texts)
            if self.normalize:
                l2_normalize_inplace(vectors)
            # payload
            payload = []
            for r, vec in zip(batch, vectors):
                meta = dict(r.metadata)
                meta.pop("__text__", None) 
                payload.append({"id": r.id, "values": vec, "metadata": meta})

            attempt = 0
            while True:
                try:
                    self.sink.insert_vectors(self.collection, payload)
                    break
                except Exception as e:
                    attempt += 1
                    if attempt > self.retry_times:
                        logger.exception(f"Sink upsert failed after retries: {e}")
                        raise
                    sleep_s = (self.retry_backoff ** (attempt - 1))
                    logger.warning(f"Upsert failed (attempt {attempt}), retrying in {sleep_s:.2f}s: {e}")
                    time.sleep(sleep_s)
            idx += self.batch_size

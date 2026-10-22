from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI


class EmbeddingsError(RuntimeError):
    pass


# =========================
# Base + OpenAI Embeddings
# =========================

class BaseEmbeddingsGenerator(ABC):
    """
    Abstract base for embeddings generation.
    """

    def __init__(
        self,
        *,
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.model = model
        self.session_id = session_id or f"embed-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 0,
        **kwargs: Any,
    ) -> List[List[float]]:
        """
        Returns an embedding vector for each text (order preserved).
        """
        raise NotImplementedError

    def embed_objects(
        self,
        objects: Sequence[Any],
        *,
        id_attr: str = "id",
        rep_method: str = "get_searchable_representation",
        batch_size: int = 0,
        **kwargs: Any,
    ) -> Dict[str, List[float]]:
        """
        Convert objects (with .get_searchable_representation()) into embeddings.
        Returns { "<id>": [vector], ... }.
        """
        if not objects:
            return {}

        ids: List[str] = []
        texts: List[str] = []

        for i, obj in enumerate(objects):
            if not hasattr(obj, id_attr):
                raise EmbeddingsError(f"Object at index {i} missing '{id_attr}' attribute")
            if not hasattr(obj, rep_method):
                raise EmbeddingsError(f"Object at index {i} missing '{rep_method}()' method")

            _id = str(getattr(obj, id_attr))
            _txt = getattr(obj, rep_method)()
            if not isinstance(_txt, str):
                raise EmbeddingsError(f"{rep_method}() must return a string (obj index {i})")

            ids.append(_id)
            texts.append(_txt)

        vectors = self.embed_texts(texts, batch_size=batch_size, **kwargs)
        if len(vectors) != len(ids):
            raise EmbeddingsError("Embedding count mismatch")

        return {ids[i]: vectors[i] for i in range(len(ids))}


class OpenAIEmbeddingsGenerator(BaseEmbeddingsGenerator):
    """
    Concrete embeddings generator using OpenAI Embeddings API.
    """

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-large",
        client: Optional[OpenAI] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self.client = client or OpenAI()

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 0,
        **_: Any,
    ) -> List[List[float]]:
        if not texts:
            return []
        if not all(isinstance(t, str) for t in texts):
            raise EmbeddingsError("'texts' must be a sequence of strings")

        # If batch_size <= 0, send in one go
        if batch_size and batch_size > 0:
            out: List[List[float]] = []
            for i in range(0, len(texts), batch_size):
                out.extend(self._embed_batch(texts[i : i + batch_size]))
            return out
        return self._embed_batch(texts)

    # ---------- internals ----------

    def _embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        try:
            resp = self.client.embeddings.create(model=self.model, input=list(texts))
        except Exception as e:
            self.logger.exception("OpenAI embeddings request failed")
            raise EmbeddingsError(str(e)) from e

        # resp.data is a list of objects with `.embedding`
        try:
            vectors = [list(map(float, d.embedding)) for d in resp.data]
        except Exception:
            self.logger.error("Unexpected embeddings response shape: %r", resp)
            raise EmbeddingsError("Unexpected embeddings response shape")

        if len(vectors) != len(texts):
            raise EmbeddingsError(f"Expected {len(texts)} embeddings, got {len(vectors)}")

        return vectors

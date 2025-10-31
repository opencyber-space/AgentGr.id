from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Mapping, Tuple, Iterable, Union

from .block.rest import RESTBlockInference
from .block.block_client import BlocksClient
from .block.inference_server import InferenceServerRegistryClient
from .custom import BaseEmbeddingsGenerator


class EmbeddingsError(RuntimeError):
    pass


class EmbeddingsGenerator:
    

    def __init__(
        self,
        *,
        client: "RESTBlockInference",
        model: str,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_mode: str = "embedding",  # change if your backend expects a different mode string
    ) -> None:
        self.client = client
        self.model = model
        self.session_id = session_id or f"embed-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_mode = default_mode

    # ----------------- Public API -----------------

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 0,  # 0/1 => send all at once if backend supports it
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        mode: Optional[str] = None,
        # passthrough for provider-specific params:
        **gen_params: Any,
    ) -> List[List[float]]:
        """
        Return an embedding vector for each input text, preserving order.
        """
        if not texts:
            return []

        if not all(isinstance(t, str) for t in texts):
            raise EmbeddingsError("All items in 'texts' must be strings")

        if batch_size and batch_size > 0:
            out: List[List[float]] = []
            for i in range(0, len(texts), batch_size):
                chunk = texts[i : i + batch_size]
                out.extend(self._embed_batch(chunk, seq_no=seq_no, extra_headers=extra_headers, mode=mode, **gen_params))
            return out

        # single shot
        return self._embed_batch(texts, seq_no=seq_no, extra_headers=extra_headers, mode=mode, **gen_params)

    def embed_objects(
        self,
        objects: Sequence[Any],
        *,
        id_attr: str = "id",
        rep_method: str = "get_searchable_representation",
        batch_size: int = 0,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        mode: Optional[str] = None,
        **gen_params: Any,
    ) -> Dict[str, List[float]]:
        """
        Convert objects (with .get_searchable_representation()) into embeddings.
        Returns dict: { "<id>": [vector], ... }
        """
        texts: List[str] = []
        ids: List[str] = []

        for i, obj in enumerate(objects):
            if not hasattr(obj, id_attr):
                raise EmbeddingsError(f"Object at index {i} missing '{id_attr}' attribute")
            if not hasattr(obj, rep_method):
                raise EmbeddingsError(f"Object at index {i} missing '{rep_method}()' method")
            _id = str(getattr(obj, id_attr))
            _txt = getattr(obj, rep_method)()
            if not isinstance(_txt, str):
                raise EmbeddingsError(f"Object at index {i} returned non-string from {rep_method}()")
            ids.append(_id)
            texts.append(_txt)

        vectors = self.embed_texts(
            texts,
            batch_size=batch_size,
            seq_no=seq_no,
            extra_headers=extra_headers,
            mode=mode,
            **gen_params,
        )

        if len(vectors) != len(ids):
            raise EmbeddingsError("Embedding count mismatch with input objects")

        return {ids[i]: vectors[i] for i in range(len(ids))}

    # ----------------- Internals -----------------

    def _embed_batch(
        self,
        texts: Sequence[str],
        *,
        seq_no: Optional[int],
        extra_headers: Optional[Dict[str, str]],
        mode: Optional[str],
        **gen_params: Any,
    ) -> List[List[float]]:
        # Try a generic payload contract; your backend can read either "texts" or "message"
        # Prefer "texts" for batch; fall back to single "message" if len==1.
        data: Dict[str, Any] = {
            "mode": mode or self.default_mode,
            "gen_params": gen_params or {},  # keep parity with your /infer pattern
        }

        if len(texts) == 1:
            data["message"] = texts[0]
        else:
            data["texts"] = list(texts)

        try:
            raw = self.client.infer(
                model=self.model,
                session_id=self.session_id,
                seq_no=seq_no if seq_no is not None else self._now_ms(),
                data=data,
                graph={},               # your pattern uses empty graph/selection_query
                selection_query={},
                extra_headers=extra_headers,
            )
        except Exception as e:
            self.logger.exception("Embeddings request failed")
            raise EmbeddingsError(str(e)) from e

        vectors = self._parse_embeddings_response(raw, expected=len(texts))
        return vectors

    @staticmethod
    def _now_ms() -> int:
        import time as _t
        return int(_t.time() * 1000)

    # ------- Response parsing (robust to variants) -------

    def _parse_embeddings_response(self, raw: Dict[str, Any], *, expected: int) -> List[List[float]]:
        """
        Tries multiple common shapes. Raises if shape is invalid or lengths mismatch.
        """
        data = raw.get("data") if isinstance(raw, dict) else None

        # 1) data.embeddings -> list[list[float]]
        if isinstance(data, dict) and isinstance(data.get("embeddings"), list):
            vecs = data["embeddings"]
            return self._validate_vectors(vecs, expected)

        # 2) data.embedding -> list[float] (single)
        if isinstance(data, dict) and isinstance(data.get("embedding"), list):
            vec = data["embedding"]
            return self._validate_vectors([vec], expected)

        # 3) data.data -> list[{"embedding": list[float]}]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            try:
                vecs = [item["embedding"] for item in data["data"]]
                return self._validate_vectors(vecs, expected)
            except Exception:
                pass

        # 4) data.reply.embeddings
        if isinstance(data, dict) and isinstance(data.get("reply"), dict):
            reply = data["reply"]
            if isinstance(reply.get("embeddings"), list):
                vecs = reply["embeddings"]
                return self._validate_vectors(vecs, expected)

        self.logger.error("Unrecognized embeddings response format: %r", raw)
        raise EmbeddingsError("Unrecognized embeddings response format.")

    def _validate_vectors(self, vecs: Any, expected: int) -> List[List[float]]:
        if not isinstance(vecs, list):
            raise EmbeddingsError("Embeddings payload must be a list")
        # Allow single vector return for single input
        if expected == 1 and vecs and isinstance(vecs[0], (int, float)):
            vecs = [vecs]

        if len(vecs) != expected:
            raise EmbeddingsError(f"Expected {expected} embeddings, got {len(vecs)}")

        out: List[List[float]] = []
        for i, v in enumerate(vecs):
            if not isinstance(v, (list, tuple)) or not all(isinstance(x, (int, float)) for x in v):
                raise EmbeddingsError(f"Embedding at index {i} is not a list of numbers")
            out.append(list(map(float, v)))
        return out


# ---------- AIOS wrapper (mirrors your AIOSSearchSelectorAPI pattern) ----------
class AIOSEmbeddingsAPI:
    """
    High-level embeddings client using AIOS discovery + RESTBlockInference.
    """

    def __init__(
        self,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str] = {},
        *,
        session_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        default_mode: str = "embedding",
    ) -> None:
        self.model = model
        self.session_id = session_id or f"embed-{uuid.uuid4()}"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_mode = default_mode

        self.inference_server_id: str = inference_server_id
        self.inference_server_registry_url = aios_url_map.get("inference_server_url")
        self.blocks_db_url = aios_url_map.get("blocks_db_url")

        # Load metadata/URLs
        self.block_data = self._load_block_data()
        self.inference_server_url = self._load_inference_server_data()

        # REST client to the target server
        self.block_inference = RESTBlockInference(self.inference_server_url)

        # Compose generator
        self._gen = EmbeddingsGenerator(
            client=self.block_inference,
            model=self.model,
            session_id=self.session_id,
            logger=self.logger,
            default_mode=self.default_mode,
        )

    # ----------------- Discovery helpers (same pattern) -----------------

    def _load_inference_server_data(self) -> str:
        if self.inference_server_id.startswith(("http://", "https://")):
            return self.inference_server_id

        if not self.inference_server_registry_url:
            raise EmbeddingsError("Missing inference_server_url in aios_url_map")

        registry_client = InferenceServerRegistryClient(self.inference_server_registry_url)
        inference_server_data = registry_client.get_inference_server(self.inference_server_id)
        if not inference_server_data:
            raise EmbeddingsError(f"Inference server not found: {self.inference_server_id}")

        urls = inference_server_data.get("inference_server_urls") or {}
        url = urls.get("rest") or urls.get("http") or urls.get("https")
        if not url:
            raise EmbeddingsError(f"No REST/HTTP URL found for inference server: {self.inference_server_id}")
        return url

    def _load_block_data(self) -> Dict[str, Any]:
        if not self.blocks_db_url:
            return {}
        block_client = BlocksClient(self.blocks_db_url)
        block_data = block_client.get_block_by_id(self.model)
        if not block_data:
            raise EmbeddingsError(f"failed to query blocks data for model '{self.model}': {block_data}")
        return block_data

    # ----------------- Public API -----------------

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 0,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        mode: Optional[str] = None,
        **gen_params: Any,
    ) -> List[List[float]]:
        return self._gen.embed_texts(
            texts,
            batch_size=batch_size,
            seq_no=seq_no,
            extra_headers=extra_headers,
            mode=mode or self.default_mode,
            **gen_params,
        )

    def embed_objects(
        self,
        objects: Sequence[Any],
        *,
        id_attr: str = "id",
        rep_method: str = "get_searchable_representation",
        batch_size: int = 0,
        seq_no: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        mode: Optional[str] = None,
        **gen_params: Any,
    ) -> Dict[str, List[float]]:
        return self._gen.embed_objects(
            objects,
            id_attr=id_attr,
            rep_method=rep_method,
            batch_size=batch_size,
            seq_no=seq_no,
            extra_headers=extra_headers,
            mode=mode or self.default_mode,
            **gen_params,
        )

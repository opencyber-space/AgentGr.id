from __future__ import annotations

import logging
import math
import textwrap
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# Assumes these are available from your codebase
# from your_module import EmbeddingsSDK
# from your_module import OpenAIEmbeddingsGenerator, BaseEmbeddingsGenerator
# from your_module import BaseInference

log = logging.getLogger("AgentRAG")


@dataclass
class RetrievedChunk:
    id: str
    score: float
    metadata: Dict[str, Any]
    text: str  # pulled from metadata[text_field]


class AgentRAG:
   

    def __init__(
        self,
        *,
        collection: str,
        embeddings_sdk,
        embedder: Any,  # e.g., OpenAIEmbeddingsGenerator
        llm,
        text_field: str = "text",
        default_top_k: int = 5,
        max_context_chars: int = 12_000,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        system_preamble: Optional[str] = None,
        answer_in_markdown: bool = True,
    ) -> None:
        self.collection = collection
        self.db = embeddings_sdk
        self.embedder = embedder
        self.llm = llm

        self.text_field = text_field
        self.default_top_k = max(1, int(default_top_k))
        self.max_context_chars = max_context_chars
        self.chunk_size = max(1, int(chunk_size))
        self.chunk_overlap = max(0, int(chunk_overlap))
        self.answer_in_markdown = answer_in_markdown
        self.system_preamble = system_preamble or (
            "You are a careful assistant. Use the provided context to answer succinctly. "
            "If the answer is not in the context, say you don't know."
        )

    # ──────────────────────────────── Ingestion ────────────────────────────────

    def add_texts(
        self,
        items: Sequence[Union[str, Dict[str, Any]]],
        *,
        batch_size: int = 128,
        store_text_in_metadata: bool = True,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> None:
       
        prepared: List[Dict[str, Any]] = []
        for it in items:
            if isinstance(it, str):
                txt = preprocess(it) if preprocess else it
                prepared.append({"id": uuid.uuid4().hex, "text": txt, "metadata": {self.text_field: txt}})
            elif isinstance(it, dict):
                _id = str(it.get("id") or uuid.uuid4().hex)
                txt = it.get("text")
                md = dict(it.get("metadata") or {})
                if not isinstance(txt, str):
                    raise ValueError("Each dict item must include a string 'text' field.")
                if store_text_in_metadata and self.text_field not in md:
                    md[self.text_field] = txt
                if preprocess:
                    txt = preprocess(txt)
                    # also keep preprocessed text in metadata to remain consistent
                    if store_text_in_metadata:
                        md[self.text_field] = txt
                prepared.append({"id": _id, "text": txt, "metadata": md})
            else:
                raise ValueError("Items must be strings or dicts containing 'text'.")

        # delegate to EmbeddingsSDK's text-ingest (does batching + embed)
        self.db.insert_texts(self.collection, prepared, embedder=self.embedder, batch_size=batch_size)

    def add_documents_chunked(
        self,
        docs: Sequence[Dict[str, Any]],
        *,
        id_key: str = "id",
        text_key: str = "text",
        meta_key: str = "metadata",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        batch_size: int = 128,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> None:
        
        csize = chunk_size or self.chunk_size
        cover = chunk_overlap or self.chunk_overlap

        to_ingest: List[Dict[str, Any]] = []
        for d in docs:
            base_id = str(d.get(id_key) or uuid.uuid4().hex)
            full_text = d.get(text_key)
            meta = dict(d.get(meta_key) or {})
            if not isinstance(full_text, str):
                raise ValueError("Each document must include a string 'text'.")

            for idx, chunk in enumerate(self._chunk(full_text, csize, cover)):
                cid = f"{base_id}__{idx:04d}"
                txt = preprocess(chunk) if preprocess else chunk
                md = dict(meta)
                md[self.text_field] = txt  # ensure retrievable text
                md["chunk_index"] = idx
                md["parent_id"] = base_id
                to_ingest.append({"id": cid, "text": txt, "metadata": md})

        self.db.insert_texts(self.collection, to_ingest, embedder=self.embedder, batch_size=batch_size)

    # ─────────────────────────────── Retrieval ─────────────────────────────────

    def retrieve(
        self,
        query_text: str,
        *,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        preprocess: Optional[Callable[[str], str]] = None,
    ) -> List[RetrievedChunk]:
        """
        Vector similarity retrieval; normalizes results across Weaviate/Pinecone.
        `filters` is passed through to EmbeddingsSDK.search (Weaviate `where`, Pinecone `filter`).
        """
        q = preprocess(query_text) if preprocess else query_text
        raw = self.db.search_text(self.collection, q, embedder=self.embedder, top_k=top_k or self.default_top_k, filters=filters)
        return self._normalize_results(self.collection, raw)

    # ─────────────────────────────── Answering ─────────────────────────────────

    def ask(
        self,
        question: str,
        *,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        max_context_chars: Optional[int] = None,
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 1024,
        prompt_template: Optional[str] = None,
        cite_inline: bool = True,
        callback: Optional[Callable[[Any], str]] = None,  # for custom LLM adapter extraction
    ) -> Dict[str, Any]:
        """
        End-to-end RAG:
          1) retrieve top_k passages
          2) construct context-limited prompt
          3) call LLM and return {answer, sources, retrieved}

        Returns:
          {
            "answer": str,
            "sources": [{"id": ..., "score": ..., "metadata": {...}, "text": ...}, ...],
            "retrieved": [...raw normalized...],
          }
        """
        retrieved = self.retrieve(question, top_k=top_k, filters=filters)
        ctx, used = self._assemble_context(retrieved, max_chars=max_context_chars or self.max_context_chars)

        tmpl = prompt_template or self._default_prompt(cite_inline=cite_inline)
        prompt = tmpl.format(question=question.strip(), context=ctx)

        # Default extractor for OpenAI chat.completions
        def _default_extract(resp: Any) -> str:
            try:
                return resp.choices[0].message.content or ""
            except Exception:
                return ""

        extractor = callback or _default_extract

        answer = self.llm.infer(
            prompt=prompt,
            callback=extractor,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message or self.system_preamble,
        )

        return {
            "answer": answer,
            "sources": [self._to_dict(r) for r in used],
            "retrieved": [self._to_dict(r) for r in retrieved],
        }

    # ─────────────────────────────── Utilities ─────────────────────────────────

    def _chunk(self, text: str, size: int, overlap: int) -> Iterable[str]:
        if len(text) <= size:
            yield text
            return
        step = max(1, size - overlap)
        i = 0
        while i < len(text):
            yield text[i : i + size]
            i += step

    def _assemble_context(
        self,
        retrieved: List[RetrievedChunk],
        *,
        max_chars: int,
    ) -> Tuple[str, List[RetrievedChunk]]:
        # Pack in order until char budget is hit.
        buf: List[str] = []
        used: List[RetrievedChunk] = []
        total = 0
        for i, r in enumerate(retrieved, start=1):
            piece = f"[{i}] {r.text}"
            if total + len(piece) > max_chars and used:
                break
            buf.append(piece)
            used.append(r)
            total += len(piece)
        return "\n\n".join(buf), used

    def _default_prompt(self, *, cite_inline: bool = True) -> str:
        cite_hint = (
            "Cite evidence with bracketed numbers like [1], [2] that refer to the given context chunks."
            if cite_inline else "Do not include inline citations."
        )
        return textwrap.dedent(
            f"""
            Use the context to answer the QUESTION.
            If the answer is not contained in the context, say you don't know.

            {cite_hint}

            CONTEXT:
            {{context}}

            QUESTION:
            {{question}}

            Answer:
            """.strip()
        )

    def _to_dict(self, r: RetrievedChunk) -> Dict[str, Any]:
        return {"id": r.id, "score": r.score, "metadata": r.metadata, "text": r.text}

    # Normalize search output across Weaviate and Pinecone shapes.
    def _normalize_results(self, collection: str, raw: Any) -> List[RetrievedChunk]:
        """
        Expected raw shapes (based on your EmbeddingsSDK):
        - Weaviate .search(): client.query.get(...).with_near_vector(...).do()
          -> {"data": {"Get": {<collection>: [ {<props...>, "_additional": {"id", "distance" | "certainty"}} ]}}}
        - Pinecone .search(): index.query(...):
          -> {"matches": [ {"id": "...", "score": float, "metadata": {...}}, ... ]}
        """
        out: List[RetrievedChunk] = []

        # Pinecone
        if isinstance(raw, dict) and "matches" in raw:
            for m in raw.get("matches") or []:
                _id = str(m.get("id") or "")
                score = float(m.get("score") or 0.0)
                md = dict(m.get("metadata") or {})
                txt = str(md.get(self.text_field, ""))  # we stored text here
                out.append(RetrievedChunk(id=_id, score=score, metadata=md, text=txt))
            # sort desc by score (Pinecone: higher is better)
            out.sort(key=lambda r: r.score, reverse=True)
            return out

        # Weaviate
        try:
            nodes = (((raw or {}).get("data") or {}).get("Get") or {}).get(collection) or []
            for n in nodes:
                add = n.get("_additional") or {}
                _id = str(add.get("id") or "")
                # We might have 'distance' (smaller is better) or 'certainty' (higher is better)
                if "certainty" in add:
                    score = float(add["certainty"])
                else:
                    # Convert distance (0 best) into a descending score; a simple transform:
                    dist = float(add.get("distance", 0.0))
                    score = 1.0 / (1.0 + dist)
                # Everything else on n are user properties = metadata
                md = {k: v for k, v in n.items() if k != "_additional"}
                txt = str(md.get(self.text_field, ""))
                out.append(RetrievedChunk(id=_id, score=score, metadata=md, text=txt))
            # sort desc by score
            out.sort(key=lambda r: r.score, reverse=True)
            return out
        except Exception:
            # Fallback: return empty normalized list
            log.exception("Failed to normalize retrieval results")
            return out

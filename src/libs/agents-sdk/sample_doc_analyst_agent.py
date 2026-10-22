"""
Document Analyst Agent — demonstrates:

  1. Versioned File System  — uses agent_fs.AgentFS (git-backed) to checkpoint
                              every processing stage as an immutable commit.
                              Any past version of any document is recoverable
                              via its commit hash.

  2. Episodic memory        — each processing run is logged as a timestamped
                              episode with outcome and importance score.

  3. Semantic memory        — subject–predicate–object triples extracted from
                              the document are stored in the knowledge graph.

All database / filesystem connection config is read from
  subject.persona.config["parameters"]
No environment variables are used for credentials.

Expected job_data:
    {
        "text": "<raw document text>",
        "document_id": "<optional stable id, defaults to task_id>"
    }

Output:
    {
        "document_id": str,
        "versions": [{"stage": str, "commit": str}],
        "fs_log":   [{"hash": str, "short_hash": str, "message": str, "date": str}],
        "facts":    [{"subject": str, "predicate": str, "object": str}],
        "related_episodes": [str],
        "related_facts":    [str]
    }
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agents_sdk.core.agent_executor import AgentResult, AgentTask, Context
from agents_sdk.core.main import main

from agent_fs import AgentFS

from agentic_memory import AgentMemory
from agentic_memory.config import ArangoConfig, MemoryConfig, PostgresConfig, WeaviateConfig
from agentic_memory.models import Outcome

log = logging.getLogger(__name__)


class DocumentAnalystAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context

        # ── Pull all config from spec; no env-var reads ────────────────
        params: Dict[str, Any] = {}
        if hasattr(subject, "persona") and hasattr(subject.persona, "config"):
            params = subject.persona.config.get("parameters", {})

        mem_cfg_raw: Dict[str, Any] = params.get("MEMORY_CONFIG", {})
        fs_cfg: Dict[str, Any] = params.get("FS_CONFIG", {})
        openai_cfg: Dict[str, Any] = params.get("OPENAI_CONFIG", {})

        self._agent_id: str = getattr(
            getattr(subject, "identity", None), "subject_id", "unknown"
        )

        # ── AgentFS: git-backed versioned workspace ────────────────────
        # Each agent gets its own repo at  <fs_path>/<agent_id>/
        self.fs = AgentFS(
            path=fs_cfg.get("path", "/tmp/agent_workspaces"),
            subject_id=self._agent_id,
            author_name=fs_cfg.get("author_name", "DocumentAnalystAgent"),
            author_email=fs_cfg.get("author_email", "doc-analyst@agents.local"),
        )

        # ── Memory (episodic + semantic) ───────────────────────────────
        mem_config = MemoryConfig(
            weaviate=WeaviateConfig(**mem_cfg_raw.get("weaviate", {})),
            arango=ArangoConfig(**mem_cfg_raw.get("arango", {})),
            postgres=PostgresConfig(**mem_cfg_raw.get("postgres", {})),
            embedding_model=mem_cfg_raw.get(
                "embedding_model",
                openai_cfg.get("embedding_model", "text-embedding-3-small"),
            ),
            top_k=int(mem_cfg_raw.get("top_k", 5)),
        )

        self.memory = AgentMemory(
            config=mem_config,
            openai_api_key=openai_cfg.get("api_key"),
        )

        log.info("[DocumentAnalystAgent] initialized  agent_id=%s  fs_root=%s",
                 self._agent_id, self.fs.root)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def get_muxer(self):
        return None

    def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]:
        if not task.job_data.get("text"):
            log.warning("Task %s missing 'text' field — skipping.", task.task_id)
            return None
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        try:
            text: str = task.job_data["text"]
            doc_id: str = task.job_data.get("document_id") or task.task_id

            version_log: List[Dict[str, Any]] = []

            # ── Stage 1: commit the raw document ──────────────────────
            raw_path = f"docs/{doc_id}/raw.txt"
            h1 = self.fs.write(
                raw_path,
                text,
                message=f"stage(raw): {doc_id}",
            )
            version_log.append({"stage": "raw", "commit": h1, "path": raw_path})
            log.info("doc=%s  raw → %s  commit=%s", doc_id, raw_path, h1[:8])

            # ── Stage 2: commit sentence-level chunks ─────────────────
            sentences = _split_sentences(text)
            chunks_path = f"docs/{doc_id}/chunks.json"
            h2 = self.fs.write(
                chunks_path,
                json.dumps(sentences, indent=2),
                message=f"stage(chunked): {doc_id}  sentences={len(sentences)}",
            )
            version_log.append({"stage": "chunked", "commit": h2, "path": chunks_path})
            log.info("doc=%s  chunked → %s  commit=%s", doc_id, chunks_path, h2[:8])

            # ── Stage 3: extract facts, commit annotated output ────────
            facts = _extract_facts(sentences)
            analyzed_path = f"docs/{doc_id}/analyzed.json"
            h3 = self.fs.write(
                analyzed_path,
                json.dumps({"sentences": sentences, "facts": facts}, indent=2),
                message=f"stage(analyzed): {doc_id}  facts={len(facts)}",
            )
            version_log.append({"stage": "analyzed", "commit": h3, "path": analyzed_path})
            log.info("doc=%s  analyzed → %s  commit=%s", doc_id, analyzed_path, h3[:8])

            # fs.log() gives the full immutable audit trail for this file
            fs_history = [
                {"hash": c.hash, "short_hash": c.short_hash, "message": c.message, "date": c.date}
                for c in self.fs.log(file_path=analyzed_path)
            ]

            # ── Episodic memory: record this processing event ─────────
            importance = min(0.4 + 0.05 * len(facts), 1.0)
            ep = self.memory.remember_episode(
                f"Processed document '{doc_id}': {len(sentences)} sentences, "
                f"{len(facts)} facts extracted. FS commit={h3[:8]}",
                session_id=task.task_id,
                agent_id=self._agent_id,
                context={"doc_id": doc_id, "fs_commit": h3},
                outcome=Outcome.SUCCESS,
                importance=importance,
            )
            log.info("Episodic memory stored  id=%s  importance=%.2f", ep.id, importance)

            # ── Semantic memory: persist extracted SPO triples ─────────
            for fact in facts:
                self.memory.know_fact(
                    subject=fact["subject"],
                    predicate=fact["predicate"],
                    object_=fact["object"],
                    content=fact.get("raw_sentence", ""),
                    source=doc_id,
                )

            # ── Recall: surface related past knowledge ─────────────────
            query_snippet = text[:256]
            past_episodes = self.memory.episodic.search(query_snippet, top_k=3)
            related_facts = self.memory.semantic.search(query_snippet, top_k=3)

            return AgentResult(
                task_id=task.task_id,
                job_output={
                    "document_id": doc_id,
                    "versions": version_log,
                    "fs_log": fs_history,
                    "facts": facts,
                    "related_episodes": [e.content for e in past_episodes],
                    "related_facts": [
                        f"{f.subject} {f.predicate} {f.object}"
                        for f in related_facts
                    ],
                },
                job_output_metadata={
                    "sentence_count": len(sentences),
                    "fact_count": len(facts),
                    "fs_latest_commit": h3,
                    "episodic_memory_id": ep.id,
                },
                is_error=False,
            )

        except Exception as exc:
            log.exception("Task %s — error in on_data: %s", task.task_id, exc)
            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "on_data", "message": str(exc)},
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


_SPO_PATTERNS: List[tuple] = [
    (r"^(.+?)\s+is\s+(.+)$", "is"),
    (r"^(.+?)\s+are\s+(.+)$", "are"),
    (r"^(.+?)\s+has\s+(.+)$", "has"),
    (r"^(.+?)\s+was\s+(.+)$", "was"),
    (r"^(.+?)\s+were\s+(.+)$", "were"),
    (r"^(.+?)\s+can\s+(.+)$", "can"),
    (r"^(.+?)\s+contains\s+(.+)$", "contains"),
]


def _extract_facts(sentences: List[str]) -> List[Dict[str, Any]]:
    """Heuristic SPO extractor. Replace with an LLM call for production use."""
    facts = []
    for sentence in sentences:
        s = sentence.rstrip(".!?")
        for pattern, predicate in _SPO_PATTERNS:
            m = re.match(pattern, s, re.IGNORECASE)
            if m:
                facts.append({
                    "subject": m.group(1).strip(),
                    "predicate": predicate,
                    "object": m.group(2).strip(),
                    "raw_sentence": sentence,
                })
                break
    return facts


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main(DocumentAnalystAgent)

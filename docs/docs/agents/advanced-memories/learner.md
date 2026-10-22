# Learner

The **Learner** (`memorygrid_learner`, MemoryGrid "Process 2") turns experience into **lessons** that agents can trust. A lesson reaches agents in one of three ways:

* it is **mined**, on a schedule or on demand, from episodic logs, task outcomes and other memory sources;
* it is **injected** by a human or by another agent;
* it is **requested** from a peer agent's Skills store or Knowledge Base (cross-agent sharing, read-only).

Mined and agent-injected lessons are **enriched** (why the lesson matters, evidence, priority, a suggested bin) and go to **human review**. Approved lessons are **promoted** to one of two bins:

| Bin | `BinType` | Holds |
|---|---|---|
| **Skills** | `skills_base` | Procedural knowledge, how-to patterns |
| **Knowledge Base** | `knowledge_base` | Semantic facts, domain knowledge |

Every lesson is stored as a Markdown file, a database record and a vector embedding, and every change is a git commit.

![Learner process](../../images/advanced-memories/learner-process.png)

[Download Image](../../images/advanced-memories/learner-process.png)

---

## Lesson Lifecycle

```
            mined (pipeline)                    injected (ai_agent)              injected (human)
                  │                                    │                              │
                  ▼                                    ▼                              │
               DRAFT ──► watcher ──► enrichment ──► PENDING_REVIEW                    │
                                                       │                              │
                              human decision ◄─────────┘                              │
                     ┌───────────────┼────────────────────┐                           │
                  approve     edit_then_approve         reject                        │
                     │               │                     │                          │
                  APPROVED     EDITED_APPROVED          REJECTED ─► archive/          │
                     └───────┬───────┘                                                │
                             ▼                                                        ▼
                         PROMOTED  ◄──────────────────────────────── (skips review) APPROVED
                   skills/ or kb/  + DB + vector + git commit
```

| Status | Meaning |
|---|---|
| `draft` | Created by the pipeline (or just persisted), not yet enriched |
| `pending_enrichment` | Reserved for enrichment in progress |
| `pending_review` | Enriched and waiting for a human decision |
| `approved` / `edited_approved` | Human approved (with or without edits) |
| `rejected` | Rejected; file moved to `archive/` and the reason logged |
| `promoted` | Written to the Skills store or Knowledge Base and committed |

Every transition is appended to the lesson's `audit_trail`.

---

## Running the Service

Requires Python ≥ 3.10.

```bash
cd agent-memories/Learner
uv venv --python 3.11 .venv && source .venv/bin/activate     # or any Python 3.10+ venv
pip install -r requirements.txt
uvicorn memorygrid_learner.main:app --port 8000
```

By default it runs with no external services:

* **SQLite** stands in for TiDB.
* An **in-memory** vector index stands in for pgvector or Milvus.
* A local **git repo** in `./data/lessons_repo` holds the lesson files.
* An offline **`FakeLLMClient`** stands in for the LLM when `ANTHROPIC_API_KEY` is unset.

On start-up the service:

* starts the **filesystem watcher** on `lessons/` and the **database poller**;
* schedules mining runs **daily at 02:00**, **weekly on Sunday at 03:00** and **monthly on day 1 at 04:00**.

### Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `MG_TIDB_DSN` | `sqlite+aiosqlite:///./memorygrid_frame.db` | Lessons/Skills/KB object store. For TiDB use `mysql+aiomysql://user:pass@host:4000/framedb` |
| `MG_VECTOR_BACKEND` | `memory` | `memory`, `pgvector` or `milvus` |
| `MG_VECTOR_DSN` | `""` | pgvector DSN or Milvus URI |
| `MG_VECTOR_DIM` | `128` | Embedding dimension |
| `MG_LESSONS_ROOT` | `./data/lessons_repo` | Lesson files + git repository |
| `MG_WORKFLOW_STRATEGY` | `statistical` | Pattern-mining strategy: `statistical`, `llm_only`, `clustering_llm`, `custom_dsl` |
| `MG_DEFAULT_TIME_WINDOW` | `daily` | Default mining window |
| `ANTHROPIC_API_KEY` | unset | Enables real LLM calls (otherwise `FakeLLMClient`) |
| `MG_LLM_MODEL` | `claude-sonnet-5` | Model name for LLM calls. Set it to a model ID your account can use (e.g. `claude-sonnet-5-5`) |
| `MG_DSL_CONFIG_DIR` | `./config/dsl` | Per-tenant lesson DSL schemas |
| `MG_TENANT_ID` | unset | Tenant whose DSL schema to load |
| `MG_DB_POLL_INTERVAL_SEC` | `30` | Database poll interval for new drafts |

Optional vector backends need extra packages: `psycopg[binary]` + `pgvector` (and `CREATE EXTENSION vector`) for pgvector, `pymilvus` for Milvus.

> The default vector embedding is a deterministic hashed bag-of-words, not a semantic model. Vector search therefore matches on shared words. Pass your own `embedding_fn` to `VectorStoreClient` for semantic search (see [Programmatic Use](#programmatic-use)).

---

## REST API

### Inject a lesson — `POST /lessons/inject/`

```bash
curl -X POST http://localhost:8000/lessons/inject/ -H "Content-Type: application/json" -d '{
  "title": "Retry flaky uploads",
  "body_md": "Retry uploads up to 3 times with exponential backoff when the storage API returns 503.",
  "injector_type": "human",
  "injected_by": "alice@example.com",
  "dsl_payload": {"action": "retry_with_backoff", "instruction_template": "Retry {operation} with backoff"},
  "metadata": {"priority": "high", "criticality": 0.8, "suggested_bin": "skills_base", "tags": ["storage"]}
}'
```

| Field | Required | Description |
|---|---|---|
| `title`, `body_md` | Yes | Lesson title and Markdown body |
| `injector_type` | Yes | `human` or `ai_agent` |
| `injected_by` | Yes | Human or agent ID |
| `dsl_payload` | No | Structured payload. An `action` (and optional `instruction_template`) here lets the [Incorporator](incorporator.md) apply the lesson deterministically |
| `metadata` | No | `priority` (`low`/`medium`/`high`/`critical`), `criticality` (0–1), `suggested_bin` (`skills_base`/`knowledge_base`), `tags`, `source_pattern_ids`. Default: medium priority, 0.5, `knowledge_base` |

Routing:

* **`human`** — trusted. The lesson skips review and is **promoted immediately** to the bin in `metadata.suggested_bin`. Response status: `promoted`.
* **`ai_agent`** — persisted as a draft, enriched, and queued for human review. Response status: `pending_review`, with `enrichment` filled in.

`POST /lessons/` does the same as `POST /lessons/inject/`.

### Human review

```bash
curl http://localhost:8000/lessons/review/queue           # lessons with status pending_review

curl -X POST http://localhost:8000/lessons/review/<lesson_id>/decide \
  -H "Content-Type: application/json" -d '{"decision": "approve"}'

curl -X POST http://localhost:8000/lessons/review/<lesson_id>/decide \
  -H "Content-Type: application/json" -d '{
    "decision": "edit_then_approve",
    "edits": {"title": "Retry uploads with backoff",
              "metadata": {"suggested_bin": "skills_base", "priority": "high"},
              "notes": "Verified against last week'\''s incidents"}
  }'

curl -X POST http://localhost:8000/lessons/review/<lesson_id>/decide \
  -H "Content-Type: application/json" -d '{"decision": "reject", "reject_reason": "too specific"}'
```

| Decision | Effect |
|---|---|
| `approve` | Promote to the bin in `metadata.suggested_bin` |
| `edit_then_approve` | Apply `edits` (`title`, `body_md`, `metadata.*`, `notes` → `dsl_payload.human_notes`), then promote |
| `reject` | Set `rejected` and `reject_reason`, move the file to `archive/`. The record is kept, not deleted |

Returns the updated lesson (404 if unknown).

### Lessons CRUD and search

| Method & Path | Description |
|---|---|
| `GET /lessons/{lesson_id}` | Get a lesson |
| `GET /lessons/?q=<text>&status=<status>&top_k=10` | List lessons (optionally by status). With `q`, lessons are filtered by text match on title/body, and `bin_matches` adds the best Skills/KB hits (text + vector) |
| `PUT /lessons/{lesson_id}` | Update `title`, `body_md`, `metadata` (merged); re-writes the file and commits |
| `DELETE /lessons/{lesson_id}` | Delete the lesson record, its vector entry and its Skills/KB entries |

### Cross-agent lesson request — `POST /lessons/cross-agent/request`

Read-only. A peer agent asks for relevant promoted lessons:

```bash
curl -X POST http://localhost:8000/lessons/cross-agent/request -H "Content-Type: application/json" \
  -d '{"agent_id": "peer-agent-7", "query": "upload retries", "top_k": 5, "bin": "skills_base"}'
```

The response is `{"requested_by": "peer-agent-7", "lessons": [{"lesson_id", "title", "body_md", "score", "match_type": "text" | "vector"}, ...]}`. Omit `bin` to search both bins. Text matches score `1.0`.

### Mining on demand — `POST /learner/trigger?time_window=daily`

Runs the mining pipeline once and returns the new draft lesson. `time_window` is `daily`, `weekly` or `monthly`.

### Metrics

| Method & Path | Returns |
|---|---|
| `GET /lessons/metrics/throughput?granularity=day` | Lessons created per `day`, `week` (ISO) or `month` |
| `GET /lessons/metrics/outcomes` | `total`, `promoted`, `rejected`, `pending`, `graduation_ratio`, `rejection_ratio` |
| `GET /health` | `{"status": "ok"}` |

---

## The Mining Pipeline

`run_learner_pipeline(time_window)`:

1. **Data collection** — `DataCollector` gathers episodes, task outcomes and auxiliary records (working memory, reflections) for the window.
2. **Pattern extraction** — the configured **workflow strategy** returns `ExtractedPattern`s. Each has a `pattern_type` (`recurring_behaviour`, `failure_mode`, `successful_strategy` or `new_correlation`), a `description`, `supporting_evidence`, a `confidence` and a `time_window`. Patterns are saved as `extracted_pattern` objects.
3. **Lesson creation** — `LessonDocumentCreator` renders a lesson (Markdown + `dsl_payload` + metadata).
4. **Persist** — the lesson file is written to `lessons/`, its record to the database, and both are committed to git.
5. The **watcher** detects the new draft, runs **enrichment**, and submits it to the **review queue**.

### Workflow strategies

| Strategy | Needs LLM | How it finds patterns |
|---|---|---|
| `statistical` (default) | No | Counts failure `error_code`s among task outcomes with `status == "failure"`, and successful `action`s among episodes with `outcome == "success"`. Anything seen at least `min_occurrences` (2) times becomes a `failure_mode` or `successful_strategy` pattern. Confidence = count / total |
| `llm_only` | Yes | Sends episodes and outcomes (in chunks of 50) to the LLM and parses a JSON list of patterns |
| `clustering_llm` | Yes | Embeds all records, clusters them with KMeans (default 3 clusters), and asks the LLM to summarise each cluster |
| `custom_dsl` | No | Runs your own Python `extract(dataset) -> list[dict]` in a restricted namespace (safe built-ins only; not a hard sandbox) |

Records the `statistical` strategy understands:

```python
episode     = {"action": "retry_with_backoff", "outcome": "success"}
task_result = {"status": "failure", "error_code": "RATE_LIMIT"}
```

A custom strategy:

```python
from memorygrid_learner.learner import workflows  # registers the built-in strategies
from memorygrid_learner.learner.workflow_runner import WorkflowRunner

script = '''
def extract(dataset):
    slow = [e for e in dataset["episodes"] if e.get("latency_ms", 0) > 2000]
    if len(slow) < 3:
        return []
    return [{"pattern_type": "new_correlation",
             "description": f"{len(slow)} slow episodes this window",
             "confidence": 0.7, "supporting_evidence": slow[:5]}]
'''
runner = WorkflowRunner("custom_dsl", script_source=script)
```

You can register your own strategy class with `WorkflowRunner.register("name", MyStrategy)`. The class must subclass `WorkflowStrategy` and implement `async run(dataset) -> list[ExtractedPattern]`.

### Lesson creation

The service uses **script mode**, a deterministic renderer:

* **Title** — the highest-confidence pattern.
* **Body** — a summary, steps or facts, and evidence sections.
* **Priority** — `high` if the average confidence is ≥ 0.75, `medium` if ≥ 0.4, else `low`.
* **Criticality** — the average confidence.
* **Suggested bin** — `skills_base` for `successful_strategy`/`failure_mode`, otherwise `knowledge_base`.

`LessonDocumentCreator(mode="llm", llm_client=...)` renders lessons with an LLM instead.

### Enrichment and the lesson DSL schema

Enrichment asks the LLM for `why_important`, `reasons_and_evidence`, `priority_classification`, `criticality_classification` and `bin_suggestion`, and stores them in `lesson.enrichment`. Enrichment and lesson creation are driven by a **lesson DSL schema** (required fields and sections), loaded per tenant:

1. `<MG_DSL_CONFIG_DIR>/<MG_TENANT_ID>.json`, else
2. `<MG_DSL_CONFIG_DIR>/default.json`, else
3. the built-in default (`title`, `summary`, `priority`, `suggested_bin`, optional `tags`; sections `summary`, `steps_or_facts`, `evidence`).

```json
{
  "version": "2.0",
  "fields": [
    {"name": "title", "type": "string"},
    {"name": "priority", "type": "enum", "enum_values": ["low", "medium", "high", "critical"]},
    {"name": "owner_team", "type": "string", "required": false}
  ],
  "required_sections": ["summary", "steps_or_facts", "evidence", "rollback"]
}
```

`LessonDSLSchema.validate_payload(payload)` returns a list of validation errors (empty if valid).

---

## Storage

| Store | Contents |
|---|---|
| **Object store** (`TiDBFrameDBClient`, table `framedb_objects`) | JSON objects keyed by `(obj_type, obj_id)`: `lesson`, `skill`, `knowledge_base_entry`, `extracted_pattern` |
| **Vector store** (`VectorStoreClient`) | Embeddings of promoted lessons, with metadata `bin` and `title` |
| **Filesystem** (`MG_LESSONS_ROOT`) | `lessons/` (drafts, pending review), `skills/`, `kb/`, `archive/`; each lesson is `<id>.md` with JSON front-matter (id, title, status, metadata, enrichment) and the Markdown body |
| **Git** (`GitVersioning`, same folder) | A commit for every draft, update, promotion and archive. `history(path)` lists a file's commits; `rollback(sha)` reverts a commit non-destructively |

Promotion (`SkillsStore.promote` / `KnowledgeBaseStore.promote`):

1. Moves the file from `lessons/` to `skills/` or `kb/`.
2. Writes the `skill` or `knowledge_base_entry` object.
3. Upserts the embedding.
4. Commits to git.

---

## Feeding Experience into the Learner

The data collector's sources (`EpisodicMemoryClient`, `TaskLogClient`, `MemoryDBClient`) are **in-process, append-only stores**. They are not connected to [Agentic Memory](agentic-memory.md), and they return all records regardless of the time window. Feed them yourself, or replace them with clients that read your real stores. A replacement only needs an `async fetch(time_window) -> list[dict]` method.

```python
from memorygrid_learner.api.deps import build_dependencies
from memorygrid_learner.learner.pipeline import run_learner_pipeline

deps = build_dependencies()

# Push experience (e.g. from Agentic Memory episodes)
for ep in mem.episodic.get_by_agent("uploader", limit=200):
    deps.data_collector.episodic_db.add({"action": ep.metadata.get("action"),
                                         "outcome": ep.outcome.value})
deps.data_collector.task_log_db.add({"status": "failure", "error_code": "RATE_LIMIT"})

lesson = await run_learner_pipeline("daily", deps.learner_deps)
```

A custom source:

```python
from datetime import datetime, timedelta, timezone

class AgenticMemoryEpisodes:
    def __init__(self, mem, agent_id):
        self.mem, self.agent_id = mem, agent_id

    async def fetch(self, time_window: str) -> list[dict]:
        days = {"daily": 1, "weekly": 7, "monthly": 30}[time_window]
        since = datetime.utcnow() - timedelta(days=days)
        return [{"action": e.metadata.get("action"), "outcome": e.outcome.value, "content": e.content}
                for e in self.mem.episodic.get_by_agent(self.agent_id, limit=1000)
                if e.created_at >= since]

deps.data_collector.episodic_db = AgenticMemoryEpisodes(mem, "uploader")
```

---

## Programmatic Use

All components can be used without the HTTP layer:

```python
from memorygrid_learner.api.deps import build_dependencies
from memorygrid_learner.config import Settings
from memorygrid_learner.hil.review_service import ReviewDecision
from memorygrid_learner.learner.pipeline import run_learner_pipeline

deps = build_dependencies(Settings(lessons_root="/tmp/lessons", workflow_strategy="statistical"))

draft = await run_learner_pipeline("daily", deps.learner_deps)
enriched = await deps.enrichment_workflow.enrich(draft)
enriched = await deps.lessons_store.update_lesson(enriched, stage="draft")

promoted = await deps.review_service.decide(str(enriched.id), ReviewDecision.APPROVE)
hits = await deps.skills_store.search("rate limit", top_k=3)
```

To plug in a real embedding model, rebuild the vector client with your own `embedding_fn` before building the stores, or construct the stores directly:

```python
from memorygrid_learner.storage.vector_client import VectorStoreClient

vector = VectorStoreClient(backend="pgvector", dsn_or_uri="postgresql://...", dim=1536,
                           embedding_fn=my_embed)
```

---

## Notes and Limitations

* **Review queue.** The queue is in-process. The source of truth for pending reviews is the lesson `status` (`GET /lessons/review/queue`), so restarting the service doesn't lose them.
* **Duplicate processing.** An `ai_agent`-injected lesson is briefly stored as a `draft` before it is enriched. If the database poller runs in that window, the lesson can be enriched and queued twice.
* **Data sources.** The time window is not applied by the built-in in-memory data sources.

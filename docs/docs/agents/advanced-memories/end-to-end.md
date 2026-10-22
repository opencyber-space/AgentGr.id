# End-to-End Example

This walkthrough connects every part of Advanced Agent Memories into one loop, using an agent that uploads files to a flaky storage API:

1. The agent **remembers** what happens (Agentic Memory).
2. The Learner **mines** a lesson from that experience; a human **approves** it.
3. At the next task, the Incorporator **applies** the lesson.
4. Outcomes are **reported**; a lesson that keeps failing is **escalated**.

It assumes the databases are deployed ([Deployment](deployment.md)) and both services run on one machine with shared storage:

* Learner on `http://localhost:8000`
* Incorporator on `http://localhost:8001`

---

## 1. Record experience

```python
from agentic_memory import AgentMemory
from agentic_memory.models import Outcome

mem = AgentMemory(config)

for attempt in range(3):
    mem.remember_episode("Upload failed with 503, retried with exponential backoff, succeeded",
                         session_id=f"s{attempt}", agent_id="uploader",
                         outcome=Outcome.SUCCESS, importance=0.7,
                         metadata={"action": "retry_with_backoff"})

mem.reflect("Immediate retries make 503s worse",
            lesson="Back off exponentially before retrying uploads")
mem.record_reward("storage API returns 503", "retry_with_backoff", reward=1.0, policy="uploads")
mem.record_reward("storage API returns 503", "retry_immediately", reward=-0.5, policy="uploads")
```

The agent can already use this directly:

```python
mem.reward.get_best_action("storage is returning 503 errors", policy="uploads")
# ("retry_with_backoff", 1.0)
```

---

## 2. Turn experience into a lesson

### Option A — mine it

The Learner's data sources are in-process. Feed them from Agentic Memory inside the Learner process (see [Feeding experience into the Learner](learner.md#feeding-experience-into-the-learner)), then trigger a run:

```bash
curl -X POST "http://localhost:8000/learner/trigger?time_window=daily"
```

With the default `statistical` strategy, three successful `retry_with_backoff` episodes become a `successful_strategy` pattern. That produces a draft lesson suggested for the **Skills** bin. The watcher picks the draft up, enriches it, and it appears in the review queue:

```bash
curl http://localhost:8000/lessons/review/queue
```

### Option B — an agent suggests it

```bash
curl -X POST http://localhost:8000/lessons/inject/ -H "Content-Type: application/json" -d '{
  "title": "Retry flaky uploads with backoff",
  "body_md": "When the storage API returns 503, retry uploads with exponential backoff (max 3 tries).",
  "injector_type": "ai_agent",
  "injected_by": "uploader",
  "dsl_payload": {"action": "retry_with_backoff", "instruction_template": "Retry {operation} with backoff"},
  "metadata": {"priority": "high", "criticality": 0.8, "suggested_bin": "skills_base"}
}'
```

The response has `"status": "pending_review"` and the lesson `id`.

---

## 3. Human review

```bash
curl -X POST http://localhost:8000/lessons/review/<lesson_id>/decide \
  -H "Content-Type: application/json" -d '{"decision": "approve"}'
```

The lesson is now `promoted`:

* its file is in `lessons_repo/skills/<id>.md` and committed to git;
* it is stored as a `skill` object and indexed in the vector store.

A human-authored lesson (`"injector_type": "human"`) skips this step and is promoted immediately.

---

## 4. Apply the lesson at the next task

Add a DSL rule so `flaky_upload` problems match the Skills bin deterministically (`MG_DSL_MATCH_RULES_PATH`):

```json
{"rules": [{"problem_type": "flaky_upload", "target_bin": "skills_base", "query": "retry uploads"}]}
```

Then, in the agent's pipeline:

```python
from memorygrid_incorporator.pipeline.incorporator_hook import IncorporatorHookClient

hook = IncorporatorHookClient("http://localhost:8001")

outcome = await hook.invoke(
    session_id="s42", problem_solving_step_ref="upload-report",
    problem_type="flaky_upload",
    current_task_context={"operation": "upload report.pdf"},
    system_state={"storage_status": "degraded"},
)
print(outcome.source, outcome.action, outcome.instruction)
# dsl retry_with_backoff Retry upload report.pdf with backoff
```

---

## 5. Report the outcome and close the loop

```python
succeeded = run_upload_with_backoff("report.pdf")       # your executor
await hook.report_outcome("upload-report", "s42", succeeded=succeeded)

mem.remember_episode("Uploaded report.pdf using the backoff lesson",
                     session_id="s42", agent_id="uploader",
                     outcome=Outcome.SUCCESS if succeeded else Outcome.FAILURE,
                     metadata={"action": outcome.action, "lesson_id": outcome.match_result.matched_entity_id})
```

Watch how the lesson performs:

```bash
curl "http://localhost:8001/feedback/metrics/success-rate?lesson_skill_id=<lesson_id>"
```

If the lesson fails `MG_FAILURE_THRESHOLD_X` times (3 by default):

* with `MG_REVIEWER_PATH_MODE=human_only`, it goes back to `pending_review` for a human to edit or reject;
* with `auto_only`, it is removed from the Skills store immediately;
* with `both`, both happen.

New episodes recorded in step 5 feed the next mining run, so the loop keeps improving.

---

## 6. Keep agent files under version control (optional)

The agent can keep its working files — plans, generated scripts, reports — in an [Agent FS](agent-fs.md):

```python
from agent_fs import AgentFS

fs = AgentFS("/var/lib/agents", subject_id="uploader")
fs.write("playbooks/uploads.md", "Retry with exponential backoff on 503 (max 3 tries).\n",
         message="adopt backoff lesson")
fs.tag("uploads-playbook-v1", message="after lesson promotion")
```

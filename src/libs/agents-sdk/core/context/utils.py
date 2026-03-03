import time
import uuid
from typing import Any, Dict, List, Optional


class AgentSession:

    def __init__(self, store, agent_id: str, session_id: Optional[str] = None):
        self.agent_id = agent_id
        self.session_id = session_id or str(uuid.uuid4())

        self.store = (
            store.get_namespace("agents")
            .get_namespace(agent_id)
            .get_namespace("sessions")
            .get_namespace(self.session_id)
        )

        self.meta = self.store.get_namespace("meta")
        self.messages = self.store.get_namespace("messages")
        self.working = self.store.get_namespace("working")
        self.tools = self.store.get_namespace("tools")
        self.metrics = self.store.get_namespace("metrics")
        self.workflow = self.store.get_namespace("workflow")
        self.interrupts = self.store.get_namespace("interrupts")
        self.checkpoints = self.store.get_namespace("checkpoints")
        self.locks = self.store.get_namespace("locks")

        if not self.meta.exists("created"):
            self.meta.set("created", time.time())
            self.meta.set("status", "active")

    def status(self):
        return self.meta.get("status")

    def set_status(self, s: str):
        self.meta.set("status", s)

    def touch(self):
        self.meta.set("last_active", time.time())

    def reset(self):
        self.store.clear()

    def export(self):
        return dict(self.store.items())

    def import_state(self, data: Dict):
        self.store.update(data)


class ConversationMemory:

    def __init__(self, session: AgentSession):
        self.store = session.messages

    def add(self, role: str, content: str):
        msgs = self.store.get("items", [])
        msgs.append({"role": role, "content": content, "ts": time.time()})
        self.store.set("items", msgs)

    def update(self, index: int, content: str):
        msgs = self.store.get("items", [])
        msgs[index]["content"] = content
        self.store.set("items", msgs)

    def delete(self, index: int):
        msgs = self.store.get("items", [])
        msgs.pop(index)
        self.store.set("items", msgs)

    def get_all(self):
        return self.store.get("items", [])

    def get_recent(self, n: int):
        return self.get_all()[-n:]

    def clear(self):
        self.store.set("items", [])

    def count(self):
        return len(self.get_all())

    def summarize(self, text: str):
        self.store.set("summary", text)

    def get_summary(self):
        return self.store.get("summary")

    def export(self):
        return dict(self.store.items())


class WorkingMemory:

    def __init__(self, session: AgentSession):
        self.store = session.working

    def set(self, key: str, value: Any):
        self.store.set(key, value)

    def get(self, key: str):
        return self.store.get(key)

    def delete(self, key: str):
        self.store.delete(key)

    def set_goal(self, goal: str):
        self.store.set("goal", goal)

    def get_goal(self):
        return self.store.get("goal")

    def set_plan(self, plan: List[str]):
        self.store.set("plan", plan)

    def get_plan(self):
        return self.store.get("plan")

    def set_step(self, step: str):
        self.store.set("current_step", step)

    def complete_step(self, step: str):
        done = self.store.get("completed", [])
        done.append(step)
        self.store.set("completed", done)

    def state(self):
        return dict(self.store.items())

    def clear(self):
        self.store.clear()


class ToolState:

    def __init__(self, session: AgentSession):
        self.store = session.tools

    def set_pending(self, name: str, payload: Dict):
        self.store.set("pending", {"tool": name, "payload": payload, "ts": time.time()})

    def clear_pending(self):
        self.store.delete("pending")

    def resolve(self, result: Any):
        self.store.set("result", result)
        self.clear_pending()

    def set_history(self, tool: str, output: Any):
        hist = self.store.get("history", [])
        hist.append({"tool": tool, "output": output})
        self.store.set("history", hist)

    def history(self):
        return self.store.get("history", [])

    def pending(self):
        return self.store.get("pending")

    def last_result(self):
        return self.store.get("result")

    def clear(self):
        self.store.clear()


class ExecutionLock:

    def __init__(self, session: AgentSession):
        self.store = session.locks.get_namespace("execution")

    def acquire(self, owner: str, ttl: int = 60):
        if self.store.exists("owner"):
            return False
        self.store.set("owner", owner, ex=ttl)
        return True

    def release(self, owner: str):
        if self.store.get("owner") == owner:
            self.store.delete("owner")

    def owner(self):
        return self.store.get("owner")

    def is_locked(self):
        return self.store.exists("owner")

    def force_release(self):
        self.store.delete("owner")


class InterruptState:

    def __init__(self, session: AgentSession):
        self.store = session.interrupts

    def wait_for(self, event: str):
        self.store.set("waiting", {"event": event, "ts": time.time()})

    def resolve(self, data: Any):
        self.store.set("result", data)
        self.store.delete("waiting")

    def waiting(self):
        return self.store.get("waiting")

    def result(self):
        return self.store.get("result")

    def clear(self):
        self.store.clear()


class WorkflowState:

    def __init__(self, session: AgentSession):
        self.store = session.workflow

    def set_current(self, node: str):
        self.store.set("current", node)

    def get_current(self):
        return self.store.get("current")

    def complete_node(self, node: str, output: Any):
        done = self.store.get("completed", {})
        done[node] = output
        self.store.set("completed", done)

    def completed(self):
        return self.store.get("completed", {})

    def is_complete(self):
        return self.store.get("complete", False)

    def mark_complete(self):
        self.store.set("complete", True)

    def reset(self):
        self.store.clear()

    def state(self):
        return dict(self.store.items())


class MetricsState:

    def __init__(self, session: AgentSession):
        self.store = session.metrics

    def inc(self, key: str, val: int = 1):
        current = self.store.get(key, 0)
        self.store.set(key, current + val)

    def record_latency(self, seconds: float):
        lat = self.store.get("latency", [])
        lat.append(seconds)
        self.store.set("latency", lat)

    def record_tokens(self, count: int):
        self.inc("tokens", count)

    def avg_latency(self):
        lat = self.store.get("latency", [])
        if not lat:
            return 0
        return sum(lat) / len(lat)

    def stats(self):
        return dict(self.store.items())

    def clear(self):
        self.store.clear()


class CheckpointManager:

    def __init__(self, session: AgentSession):
        self.session = session
        self.store = session.checkpoints

    def snapshot(self):
        cid = str(uuid.uuid4())

        data = {
            "messages": self.session.messages.get("items"),
            "working": dict(self.session.working.items()),
            "tools": dict(self.session.tools.items()),
            "workflow": dict(self.session.workflow.items()),
            "metrics": dict(self.session.metrics.items()),
        }

        self.store.set(cid, data)
        return cid

    def restore(self, cid: str):
        data = self.store.get(cid)
        if not data:
            return False

        self.session.messages.set("items", data["messages"])
        self.session.working.update(data["working"])
        self.session.tools.update(data["tools"])
        self.session.workflow.update(data["workflow"])
        self.session.metrics.update(data["metrics"])

        return True

    def list(self):
        return self.store.keys()

    def delete(self, cid: str):
        self.store.delete(cid)


class PromptContextBuilder:

    def __init__(self, session: AgentSession):
        self.session = session

    def build(self, max_messages: int = 20):
        msgs = self.session.messages.get("items", [])
        summary = self.session.messages.get("summary")
        working = dict(self.session.working.items())
        tools = dict(self.session.tools.items())

        return {
            "summary": summary,
            "messages": msgs[-max_messages:],
            "working_memory": working,
            "tool_state": tools,
        }

    def build_flat_text(self):
        ctx = self.build()
        lines = []
        if ctx["summary"]:
            lines.append("SUMMARY: " + ctx["summary"])
        for m in ctx["messages"]:
            lines.append(f"{m['role']}: {m['content']}")
        return "\n".join(lines)
import time
import uuid
from typing import Any, Optional


class TaskQueue:

    def __init__(self, store, name: str = "default"):
        self.store = store.get_namespace("task_queues").get_namespace(name)
        self.meta = self.store.get_namespace("meta")

    def _queue(self):
        return self.store.get("queue", [])

    def _set_queue(self, q):
        self.store.set("queue", q)

    def enqueue(self, task: dict) -> str:
        q = self._queue()
        task_id = str(uuid.uuid4())
        task["_id"] = task_id
        task["_status"] = "pending"
        task["_retries"] = 0
        task["_ts"] = time.time()
        q.append(task)
        self._set_queue(q)
        return task_id

    def dequeue(self) -> Optional[dict]:
        q = self._queue()
        if not q:
            return None
        task = q.pop(0)
        task["_status"] = "processing"
        self._set_queue(q)
        return task

    def retry(self, task_id: str):
        q = self._queue()
        for t in q:
            if t["_id"] == task_id:
                t["_retries"] += 1
                t["_status"] = "pending"
                break
        self._set_queue(q)


class SharedWorkspace:

    def __init__(self, store, name: str = "global"):
        self.store = store.get_namespace("workspace").get_namespace(name)
        self.events = self.store.get_namespace("events")

    def publish(self, key: str, value: Any):
        self.store.set(key, value)
        ev = self.events.get(key, [])
        ev.append({"ts": time.time(), "value": value})
        self.events.set(key, ev)

    def subscribe(self, key: str):
        return self.store.get(key)


class StreamingBuffer:

    def __init__(self, store, name: str):
        self.store = store.get_namespace("streams").get_namespace(name)

    def start(self):
        self.store.set("tokens", [])
        self.store.set("status", "streaming")
        self.store.set("started_at", time.time())

    def append(self, token: str):
        tokens = self.store.get("tokens", [])
        tokens.append(token)
        self.store.set("tokens", tokens)

    def complete(self):
        self.store.set("status", "complete")
        self.store.set("completed_at", time.time())

    def get_partial(self) -> str:
        tokens = self.store.get("tokens", [])
        return "".join(tokens)
import os
import json
import threading
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Protocol, Tuple, Union


from .policy_base import PoliciesManager

try:
    import redis 
except Exception:
    redis = None


class BacklogStore(Protocol):

    def push(self, session_id: str, item: Dict[str, Any]) -> None: ...
    def pop_one(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    def pop_n(self, session_id: str, n: int) -> List[Dict[str, Any]]: ...
    def peek_n(self, session_id: str, n: int) -> List[Dict[str, Any]]: ...
    def clear(self, session_id: str) -> None: ...
    def length(self, session_id: str) -> int: ...


class InMemoryBacklogStore(BacklogStore):

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._q: Dict[str, Deque[Dict[str, Any]]] = defaultdict(deque)

    def push(self, session_id: str, item: Dict[str, Any]) -> None:
        with self._lock:
            self._q[session_id].append(item)

    def pop_one(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._q[session_id]:
                return None
            return self._q[session_id].popleft()

    def pop_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        with self._lock:
            dq = self._q[session_id]
            for _ in range(max(0, n)):
                if not dq:
                    break
                out.append(dq.popleft())
        return out

    def peek_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        with self._lock:
            dq = self._q[session_id]
            # do not modify the queue
            return [dq[i] for i in range(min(n, len(dq)))]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._q[session_id].clear()

    def length(self, session_id: str) -> int:
        with self._lock:
            return len(self._q[session_id])


class RedisBacklogStore(BacklogStore):
    

    def __init__(self, url: str, namespace: str = "backlog") -> None:
        if redis is None:
            raise RuntimeError("redis-py not installed")
        self.r = redis.from_url(url, decode_responses=True)
        self.ns = namespace

    def _key(self, session_id: str) -> str:
        return f"{self.ns}:{session_id}"

    @staticmethod
    def _encode(item: Dict[str, Any]) -> str:
        return json.dumps(item, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _decode(s: Optional[str]) -> Optional[Dict[str, Any]]:
        if s is None:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None

    def push(self, session_id: str, item: Dict[str, Any]) -> None:
        self.r.rpush(self._key(session_id), self._encode(item))

    def pop_one(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._decode(self.r.lpop(self._key(session_id)))

    def pop_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        n = max(0, n)
        if n == 0:
            return []
        key = self._key(session_id)
        pipe = self.r.pipeline()
        for _ in range(n):
            pipe.lpop(key)
        results = pipe.execute()
        out: List[Dict[str, Any]] = []
        for s in results:
            item = self._decode(s)
            if item is not None:
                out.append(item)
        return out

    def peek_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        n = max(0, n)
        if n == 0:
            return []
        key = self._key(session_id)
        raw = self.r.lrange(key, 0, n - 1)
        out: List[Dict[str, Any]] = []
        for s in raw:
            item = self._decode(s)
            if item is not None:
                out.append(item)
        return out

    def clear(self, session_id: str) -> None:
        self.r.delete(self._key(session_id))

    def length(self, session_id: str) -> int:
        return int(self.r.llen(self._key(session_id)))


class MessageBacklogQueue:
 

    def __init__(self, store: Optional[BacklogStore] = None) -> None:
        backend = (os.getenv("BACKLOG_BACKEND") or "memory").lower()
        if store is None:
            if backend == "redis":
                url = os.getenv("REDIS_URL")
                if not url:
                    raise ValueError("REDIS_URL must be set for redis backend")
                store = RedisBacklogStore(url=url)
            else:
                store = InMemoryBacklogStore()
        self.store: BacklogStore = store

    # Queue APIs
    def push(self, session_id: str, message: Dict[str, Any]) -> None:
        self.store.push(session_id, message)

    def pop_one(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.store.pop_one(session_id)

    def pop_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        return self.store.pop_n(session_id, n)

    def peek_n(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        return self.store.peek_n(session_id, n)

    def clear(self, session_id: str) -> None:
        self.store.clear(session_id)

    def length(self, session_id: str) -> int:
        return self.store.length(session_id)

    
Message = Dict[str, Any]
BatchOrSingle = Union[Dict[str, Any], List[Dict[str, Any]]]

class MessageBacklogHandler:
   
    NAME = "message_backlog"

    def __init__(self, policies: "PoliciesManager") -> None:
        self.policies = policies
        self.queue = MessageBacklogQueue()
        try:
            self.policies.add_policy(self.NAME, injects={"backlog_store": self.queue.store})
        except Exception:
            pass

    def default_function(self, data):
        return {"backlogged": False, "messages": [data]}

    def decide(self, session_id: str, message_data: Dict[str, Any]) -> Tuple[bool, Union[Dict[str, Any], List[Dict[str, Any]]]]:
       
        payload = {"session_id": session_id, "message_data": message_data}

        try:
            result = self.policies.execute(self.NAME, payload, default_func=self.default_function)
        except KeyError:
            return False, message_data
        except Exception:
            return False, message_data

        if isinstance(result, dict):
            if result.get("backlogged") is True:
                reason = result.get("reason")
                return True, reason if isinstance(reason, dict) else {}
            if result.get("backlogged") is False:
                if "messages" in result and isinstance(result["messages"], list):
                    return False, [m for m in result["messages"] if isinstance(m, dict)]
                md = result.get("message_data")
                return False, md if isinstance(md, dict) else message_data

        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[0], bool)
            and (isinstance(result[1], dict) or isinstance(result[1], list))
        ):
            if result[0] is True:
                return True, result[1] if isinstance(result[1], dict) else {}
            else:
                return False, result[1]

        return False, message_data
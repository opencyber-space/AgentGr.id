import threading
import queue
import random
import time
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import logging


logger = logging.getLogger(__name__)


try:
    import redis  # redis-py
except Exception:
    redis = None  
Message = Dict[str, Any]
Batch = List[Message]

from .policy_base import PoliciesManager
from .agent import AgentInternalClient


class LoadBalancer:
    NAME = "load_balancer"

    def __init__(
        self,
        policies: "PoliciesManager",
        *,
        name: Optional[str] = None,
        on_dispatch: Optional[Callable[[str, Message, Dict[str, Any]], None]] = None,
        max_in_queue: int = 10000,
        max_out_queue: int = 10000,
        thread_name: str = "LoadBalancerThread",
        poll_timeout: float = 0.5

    ) -> None:
        self.policies = policies
        self.policy_name = name or self.NAME

        self._in_q: "queue.Queue[Message]" = queue.Queue(maxsize=max_in_queue)
        self._out_q: "queue.Queue[Tuple[str, Message, Dict[str, Any]]]" = queue.Queue(maxsize=max_out_queue)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._poll_timeout = poll_timeout

        self.on_dispatch = on_dispatch

        self._lock = threading.Lock()
        self.current_instances: List[str] = []

        # >>> NEW: subject id & redis sink config
        self._subject_id: Optional[str] = None
        self._redis_conns: Dict[Tuple[str, int], "redis.Redis"] = {}
        self._redis_queue_key: str = os.getenv("LB_REDIS_QUEUE_KEY", "jobs:inbox")
        self._redis_max_retries: int = int(os.getenv("LB_REDIS_MAX_RETRIES", "10"))
        self._redis_base_backoff: float = float(os.getenv("LB_REDIS_BASE_BACKOFF_SEC", "0.5"))

        def _get_instances() -> List[str]:
            with self._lock:
                return list(self.current_instances)

        try:
            self.policies.add_policy(
                self.policy_name,
                injects={
                    "get_instances": _get_instances,
                    "load_balancer": self,
                },
            )
        except Exception:
            pass

        self._thread_name = thread_name

    # ---------- lifecycle ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self._thread_name, daemon=True)
        self._thread.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def default_function(self, data: dict):
        selected_instance = random.choice(self.current_instances)
        return selected_instance

    # ---------- instance management ----------
    def update_current_instances(self, instances: List[str]) -> None:
        with self._lock:
            self.current_instances = list(instances or [])

    def set_subject_id(self, subject_id: str) -> None:
        with self._lock:
            self._subject_id = subject_id

    # ---------- submission ----------
    def submit(self, payload: Union[Dict[str, Any], Message, List[Message]]) -> int:
        count = 0
        if isinstance(payload, dict) and "status" in payload:
            if payload.get("status") == "ready" and isinstance(payload.get("messages"), list):
                for msg in payload["messages"]:
                    if isinstance(msg, dict):
                        self._in_q.put(msg)
                        count += 1
            return count

        if isinstance(payload, dict):
            self._in_q.put(payload)
            return 1

        if isinstance(payload, list):
            for msg in payload:
                if isinstance(msg, dict):
                    self._in_q.put(msg)
                    count += 1
            return count

        return 0

    # ---------- output (pull-based) ----------
    def get_next_dispatch(self, timeout: Optional[float] = None) -> Optional[Tuple[str, Message, Dict[str, Any]]]:
        try:
            return self._out_q.get(timeout=timeout)
        except queue.Empty:
            return None

    # ---------- main loop ----------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._in_q.get(timeout=self._poll_timeout)
            except queue.Empty:
                continue

            session_id = msg.get("session_id") or msg.get("sid") or msg.get("session")
            payload = {"session_id": session_id, "message_data": msg}

            try:
                result = self.policies.execute(self.policy_name, payload, self.default_function)
            except KeyError:
                self._emit(None, msg, {"warning": "no_policy"})
                continue
            except Exception as e:
                self._emit(None, msg, {"error": f"policy_exception:{type(e).__name__}"})
                continue

            inst_id, meta = self._parse_policy_result(result)

            self._push_to_instance_redis(inst_id, msg, meta)

            self._emit(inst_id, msg, meta)

    def _emit(self, instance_id: Optional[str], message: Message, meta: Dict[str, Any]) -> None:
        event = (instance_id if instance_id is not None else "", message, meta or {})
        try:
            if self.on_dispatch:
                self.on_dispatch(*event)
        except Exception:
            pass
        try:
            self._out_q.put_nowait(event)
        except queue.Full:
            pass

    # ---------- parse policy output ----------
    def _parse_policy_result(self, result: Any) -> Tuple[Optional[str], Dict[str, Any]]:
        if isinstance(result, dict):
            ok = bool(result.get("ok", True))
            if ok and isinstance(result.get("instance"), str):
                return result["instance"], (result.get("metadata") or {})
            return None, (result.get("reason") or {})

        if isinstance(result, tuple) and len(result) == 2:
            inst, meta = result
            if isinstance(inst, (str, type(None))) and isinstance(meta, dict):
                return inst, meta

        if isinstance(result, str):
            return result, {}

        return None, {"warning": "unrecognized_policy_output"}

    # ---------- NEW: Redis sink ----------
    def _make_target(self, instance_id: Optional[str]) -> Optional[Tuple[str, int]]:
       
        if not instance_id:
            return None
        with self._lock:
            subject_id = self._subject_id
        if not subject_id:
            return None
        host = f"{instance_id}-{subject_id}.agents.svc.cluster.local"
        return host, 6379

    def _get_redis(self, host: str, port: int) -> Optional["redis.Redis"]:
        if redis is None:
            return None
        key = (host, port)
        # cached
        conn = self._redis_conns.get(key)
        if conn is not None:
            return conn
        # create & cache
        logger.info(f"[Redis-Connection] {host} {port}")
        conn = redis.StrictRedis(host=host, port=port, decode_responses=True)  # no auth
        self._redis_conns[key] = conn
        return conn

    def _ping_with_retry(self, r: "redis.Redis") -> bool:
        delay = self._redis_base_backoff
        for _ in range(max(1, self._redis_max_retries)):
            try:
                if r.ping():
                    return True
            except Exception:
                # try again after a backoff
                time.sleep(delay)
                delay = min(delay * 2, 5.0)
        return False

    def _push_to_instance_redis(self, instance_id: Optional[str], message: Message, meta: Dict[str, Any]) -> None:
        
        try:
       
            target = self._make_target(instance_id)
            if target is None:
                return
            if redis is None:
                return

            logger.info(f"[Pushing Message] {message} --> ({target}) ({self._redis_queue_key})")

            host, port = target
            key = (host, port)

            payload = message["message_data"].copy()

        
            data = json.dumps(payload)

            retries = max(1, self._redis_max_retries)
            delay = self._redis_base_backoff

            r = self._get_redis(host, port)
            logger.info(f"[RedisConnection] {r}")
            r.lpush(self._redis_queue_key, data)

            logger.info(f"[message pushed] {data}")

            '''for attempt in range(retries):
                r = self._get_redis(host, port)
                if r is None:
                    return

                if not self._ping_with_retry(r):
                    self._redis_conns.pop(key, None)
                    time.sleep(delay)
                    delay = min(delay * 2, 5.0)
                    continue

                try:
                    r.lpush(self._redis_queue_key, data)
                    return
                except Exception as ee:
                    logger.error(f"[RedisError] {ee}")
                    self._redis_conns.pop(key, None)
                    time.sleep(delay)
                    delay = min(delay * 2, 5.0)'''

            return
        except Exception as e:
            logger.error(f"[error] {e}")

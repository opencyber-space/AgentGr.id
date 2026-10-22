from __future__ import annotations

import os
import time
import json
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .policy_base import PoliciesManager

try:
    import redis
    from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
except Exception:
    redis = None

    class RedisConnectionError(Exception):
        ...

    class RedisTimeoutError(Exception):
        ...


@dataclass
class RateRecord:
    session_id: str
    count: int = 0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class RateStore:
    def incr(self, session_id: str, amount: int = 1,
             expire_seconds: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> int: ...

    def get(self, session_id: str) -> int: ...
    def reset(self, session_id: str) -> None: ...
    def set_metadata(self, session_id: str,
                     metadata: Dict[str, Any], expire_seconds: Optional[int] = None) -> None: ...

    def get_metadata(self, session_id: str) -> Dict[str, Any]: ...
    def update_metadata(self, session_id: str,
                        partial: Dict[str, Any], expire_seconds: Optional[int] = None) -> Dict[str, Any]: ...


class InMemoryRateStore(RateStore):
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, RateRecord] = {}

    def incr(self, session_id: str, amount: int = 1, expire_seconds: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        now = time.time()
        with self._lock:
            rec = self._data.get(session_id)
            if rec is None:
                rec = RateRecord(session_id=session_id)
                self._data[session_id] = rec
            rec.count += amount
            rec.updated_at = now
            if metadata:
                rec.metadata.update(metadata)
            return rec.count

    def get(self, session_id: str) -> int:
        with self._lock:
            rec = self._data.get(session_id)
            return rec.count if rec else 0

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)

    def set_metadata(self, session_id: str, metadata: Dict[str, Any], expire_seconds: Optional[int] = None) -> None:
        with self._lock:
            rec = self._data.get(session_id)
            if rec is None:
                rec = RateRecord(session_id=session_id)
                self._data[session_id] = rec
            rec.metadata = dict(metadata)

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            rec = self._data.get(session_id)
            return dict(rec.metadata) if rec else {}

    def update_metadata(self, session_id: str, partial: Dict[str, Any], expire_seconds: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            rec = self._data.get(session_id)
            if rec is None:
                rec = RateRecord(session_id=session_id)
                self._data[session_id] = rec
            rec.metadata.update(partial or {})
            return dict(rec.metadata)


class RedisRateStore(RateStore):
    def __init__(
        self,
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 2.5,
        max_retries: int = 5,
        base_backoff: float = 0.2,
        key_prefix: str = "rate",
        meta_prefix: str = "rate_meta",
    ):
        if redis is None:
            raise RuntimeError("redis-py not installed")
        self._url = url or os.getenv("REDIS_URL")
        self._conn_kwargs = dict(host=host or os.getenv("REDIS_HOST", "localhost"),
                                 port=port or int(
                                     os.getenv("REDIS_PORT", "6379")),
                                 db=db, password=password or os.getenv(
                                     "REDIS_PASSWORD"),
                                 socket_timeout=socket_timeout, decode_responses=True)
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._lock = threading.Lock()
        self._key_prefix = key_prefix
        self._meta_prefix = meta_prefix
        self._client = self._connect()

    def _connect(self):
        cli = redis.StrictRedis.from_url(
            self._url, decode_responses=True) if self._url else redis.StrictRedis(**self._conn_kwargs)
        self._ping_with_retry(cli)
        return cli

    def _ping_with_retry(self, cli):
        delay = self._base_backoff
        for _ in range(self._max_retries):
            try:
                cli.ping()
                return
            except (RedisConnectionError, RedisTimeoutError):
                time.sleep(delay)
                delay = min(delay * 2, 5.0)
        raise RedisConnectionError("Unable to connect to Redis")

    def _with_retry(self, fn, *args, **kwargs):
        delay = self._base_backoff
        for _ in range(self._max_retries):
            try:
                return fn(*args, **kwargs)
            except (RedisConnectionError, RedisTimeoutError):
                with self._lock:
                    try:
                        self._client = self._connect()
                    except Exception:
                        pass
                time.sleep(delay)
                delay = min(delay * 2, 5.0)
        raise RedisConnectionError("Redis operation failed after retries")

    def _k(self, session_id: str) -> str:
        return f"{self._key_prefix}:{session_id}"

    def _m(self, session_id: str) -> str:
        return f"{self._meta_prefix}:{session_id}"

    def incr(self, session_id: str, amount: int = 1, expire_seconds: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        k, m = self._k(session_id), self._m(session_id)

        def op():
            pipe = self._client.pipeline()
            pipe.incrby(k, amount)
            if expire_seconds:
                pipe.expire(k, expire_seconds)
            if metadata:
                meta_json = json.dumps(
                    metadata, ensure_ascii=False, separators=(",", ":"))
                pipe.set(m, meta_json)
                if expire_seconds:
                    pipe.expire(m, expire_seconds)
            vals = pipe.execute()
            return int(vals[0])
        return self._with_retry(op)

    def get(self, session_id: str) -> int:
        v = self._with_retry(self._client.get, self._k(session_id))
        return int(v) if v is not None else 0

    def reset(self, session_id: str) -> None:
        self._with_retry(self._client.delete, self._k(
            session_id), self._m(session_id))

    def set_metadata(self, session_id: str, metadata: Dict[str, Any], expire_seconds: Optional[int] = None) -> None:
        meta_json = json.dumps(
            metadata or {}, ensure_ascii=False, separators=(",", ":"))
        if expire_seconds:
            self._with_retry(self._client.setex, self._m(
                session_id), expire_seconds, meta_json)
        else:
            self._with_retry(self._client.set, self._m(session_id), meta_json)

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        raw = self._with_retry(self._client.get, self._m(session_id))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def update_metadata(self, session_id: str, partial: Dict[str, Any], expire_seconds: Optional[int] = None) -> Dict[str, Any]:
        def op():
            raw = self._client.get(self._m(session_id))
            meta = {}
            if raw:
                try:
                    meta = json.loads(raw)
                except Exception:
                    meta = {}
            meta.update(partial or {})
            encoded = json.dumps(meta, ensure_ascii=False,
                                 separators=(",", ":"))
            if expire_seconds:
                self._client.setex(self._m(session_id),
                                   expire_seconds, encoded)
            else:
                self._client.set(self._m(session_id), encoded)
            return meta
        return self._with_retry(op)


class RateCounter:
    def __init__(self, store: Optional[RateStore] = None):
        self.store = store or InMemoryRateStore()

    def increment(self, session_id: str, amount: int = 1, expire_seconds: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        return self.store.incr(session_id, amount, expire_seconds, metadata)

    def get(self, session_id: str) -> int:
        return self.store.get(session_id)

    def reset(self, session_id: str) -> None:
        self.store.reset(session_id)

    def set_metadata(self, session_id: str, metadata: Dict[str, Any], expire_seconds: Optional[int] = None) -> None:
        self.store.set_metadata(session_id, metadata, expire_seconds)

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        return self.store.get_metadata(session_id)

    def update_metadata(self, session_id: str, partial: Dict[str, Any], expire_seconds: Optional[int] = None) -> Dict[str, Any]:
        return self.store.update_metadata(session_id, partial, expire_seconds)


class RateLimiterPolicy:
    NAME = "rate_limiter"

    def __init__(self, policies: PoliciesManager, store: Optional[RateStore] = None):
        backend = (os.getenv("RATE_LIMITER_BACKEND") or "memory").lower()
        if store is None:
            store = RedisRateStore(url=os.getenv(
                "REDIS_URL")) if backend == "redis" else InMemoryRateStore()
        self.counter = RateCounter(store=store)
        self.policies = policies
        try:
            self.policies.add_policy(
                self.NAME, injects={"rate_counter": self.counter})
        except Exception:
            pass

    def default_function(self, data):
        return {"allowed": True}

    def is_allowed(self, session_id: str, message_data: Dict[str, Any]) -> bool:
        payload = {"session_id": session_id, "message_data": message_data}
        try:
            result = self.policies.execute(self.NAME, payload, self.default_function)
        except KeyError:
            return True
        except Exception:
            return True

        if isinstance(result, dict):
            allowed = bool(result.get("allowed", True))
            if allowed:
                meta = result.get("metadata")
                if isinstance(meta, dict) and meta:
                    try:
                        self.counter.update_metadata(session_id, meta)
                    except Exception:
                        pass
            return allowed

        if isinstance(result, bool):
            return result

        return True

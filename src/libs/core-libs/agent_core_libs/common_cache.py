from __future__ import annotations
import sys


import json
import logging
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Tuple, Union

import redis

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO)


Encoder = Callable[[Any], str]
Decoder = Callable[[str], Any]


class CommonCache(MutableMapping[str, Any]):
   
    def __init__(
        self,
        *,
        default_url: str,
        url: Optional[str] = None,
        namespace: str = "common",
        separator: str = ":",
        decode_responses: bool = True,
        socket_timeout: Optional[float] = 5.0,
        socket_connect_timeout: Optional[float] = 5.0,
        health_check_interval: int = 15,
        max_connections: int = 128,
        value_serializer: Optional[Encoder] = None,
        value_deserializer: Optional[Decoder] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        If `url` is not provided, `default_url` is used.
        Set `value_serializer/deserializer` to (json.dumps/json.loads) for transparent JSON.
        """
        self.log = logger or log
        self._namespace = namespace.strip(separator) if namespace else ""
        self._sep = separator
        redis_url = (url or default_url).strip()

        self._pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=decode_responses,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            health_check_interval=health_check_interval,
            max_connections=max_connections,
        )
        self._r = redis.Redis(connection_pool=self._pool)

        # serialization (defaults: identity on str, JSON if asked)
        self._enc: Encoder = value_serializer or (lambda v: json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
        self._dec: Decoder = value_deserializer or (lambda s: _try_json_loads(s))

        # Touch connection once (lazy ok too, but this surfaces misconfig early)
        try:
            self._r.ping()
        except Exception as e:
            self.log.error("CommonCache: unable to connect to Redis at %s: %s", redis_url, e)
            raise

    # ----------------------------- namespace utils -----------------------------

    @property
    def namespace(self) -> str:
        return self._namespace

    def with_namespace(self, child: str) -> "CommonCache":
        """Return a new CommonCache instance sharing the same connection but extended namespace."""
        ns = self._join_ns(self._namespace, child)
        return self._clone(namespace=ns)

    def _clone(self, **overrides: Any) -> "CommonCache":
        params = dict(
            default_url="unused://",  # won't be used because we reuse the existing pool
            url="unused://",
            namespace=self._namespace,
            separator=self._sep,
            value_serializer=self._enc,
            value_deserializer=self._dec,
        )
        params.update(overrides)
        clone = object.__new__(CommonCache)  # bypass __init__
        # Copy fields
        clone.log = self.log
        clone._namespace = params["namespace"]
        clone._sep = params["separator"]
        clone._pool = self._pool
        clone._r = redis.Redis(connection_pool=self._pool)
        clone._enc = params["value_serializer"]
        clone._dec = params["value_deserializer"]
        return clone

    def _join_ns(self, *parts: str) -> str:
        parts = [p for p in parts if p]
        return self._sep.join(parts)

    def _k(self, key: str) -> str:
        if not isinstance(key, str):
            key = str(key)
        return self._join_ns(self._namespace, key) if self._namespace else key

    # ----------------------------- dict-like API -------------------------------

    def __getitem__(self, key: str) -> Any:
        raw = self._r.get(self._k(key))
        if raw is None:
            raise KeyError(key)
        return self._dec(raw)

    def __setitem__(self, key: str, value: Any) -> None:
        self._r.set(self._k(key), self._enc(value))

    def __delitem__(self, key: str) -> None:
        if self._r.delete(self._k(key)) == 0:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Iterate logical (un-prefixed) keys in namespace."""
        prefix = self._namespace + self._sep if self._namespace else ""
        for k in self._scan_keys_iter():
            # strip namespace prefix
            yield k[len(prefix):] if prefix and k.startswith(prefix) else k

    def __len__(self) -> int:
        return sum(1 for _ in self._scan_keys_iter())

    # Helpful dict-style extras
    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        raw = self._r.get(self._k(key))
        return default if raw is None else self._dec(raw)

    def setdefault(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        full = self._k(key)
        with self._r.pipeline() as p:
            p.setnx(full, self._enc(default))
            p.get(full)
            _, val = p.execute()
        return self._dec(val)

    def update(self, other: Mapping[str, Any] | Iterable[Tuple[str, Any]] = (), **kwargs: Any) -> None:  # type: ignore[override]
        items: List[Tuple[str, Any]] = []
        if isinstance(other, Mapping):
            items.extend(other.items())
        else:
            items.extend(list(other))
        if kwargs:
            items.extend(list(kwargs.items()))
        if not items:
            return
        m = {self._k(k): self._enc(v) for k, v in items}
        self._r.mset(m)

    # ----------------------------- redis helpers -------------------------------

    @property
    def raw(self) -> redis.Redis:
        """Access the underlying redis client (power users)."""
        return self._r

    # CRUD-ish
    def set(self, key: str, value: Any, *, ex: Optional[int] = None, px: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        return bool(self._r.set(self._k(key), self._enc(value), ex=ex, px=px, nx=nx, xx=xx))

    def get_raw(self, key: str) -> Optional[str]:
        """Return the raw (serialized) value without decoding."""
        return self._r.get(self._k(key))

    def mget(self, keys: Iterable[str]) -> List[Optional[Any]]:
        full = [self._k(k) for k in keys]
        vals = self._r.mget(full)
        return [self._dec(v) if v is not None else None for v in vals]

    def mset(self, mapping: Mapping[str, Any]) -> bool:
        m = {self._k(k): self._enc(v) for k, v in mapping.items()}
        return bool(self._r.mset(m))

    def delete(self, *keys: str) -> int:
        full = [self._k(k) for k in keys]
        return int(self._r.delete(*full) if full else 0)

    def exists(self, *keys: str) -> int:
        full = [self._k(k) for k in keys]
        return int(self._r.exists(*full)) if full else 0

    def expire(self, key: str, seconds: int) -> bool:
        return bool(self._r.expire(self._k(key), seconds))

    def ttl(self, key: str) -> int:
        return int(self._r.ttl(self._k(key)))

    def incr(self, key: str, amount: int = 1) -> int:
        return int(self._r.incr(self._k(key), amount))

    def decr(self, key: str, amount: int = 1) -> int:
        return int(self._r.decr(self._k(key), amount))

    # hash helpers (basic)
    def hget(self, name: str, field: str) -> Optional[str]:
        return self._r.hget(self._k(name), field)

    def hset(self, name: str, field: str, value: Union[str, int, float]) -> int:
        return int(self._r.hset(self._k(name), field, value))

    def hgetall(self, name: str) -> Dict[str, str]:
        return {k: v for k, v in self._r.hgetall(self._k(name)).items()}

    # scanning
    def scan(self, cursor: int = 0, match: Optional[str] = None, count: Optional[int] = None) -> Tuple[int, List[str]]:
      
        ns_match = self._k(match) if match else self._k("*")
        new_cursor, keys = self._r.scan(cursor=cursor, match=ns_match, count=count)
        return int(new_cursor), keys

    def _scan_keys_iter(self, pattern: Optional[str] = None) -> Iterator[str]:
        ns_match = self._k(pattern or "*")
        yield from self._r.scan_iter(match=ns_match)

    # utility
    def clear_namespace(self) -> int:
        """Delete all keys in the current namespace. Returns count deleted."""
        cnt = 0
        pipe = self._r.pipeline()
        batch = 0
        for k in self._scan_keys_iter():
            pipe.delete(k)
            batch += 1
            if batch >= 1000:
                cnt += sum(int(x) for x in pipe.execute())
                batch = 0
        if batch:
            cnt += sum(int(x) for x in pipe.execute())
        return cnt


def _try_json_loads(s: str) -> Any:
    if s is None:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s

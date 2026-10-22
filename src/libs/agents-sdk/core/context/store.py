import os
import json
import pickle
import threading
from typing import Any, Dict, List, Optional

import redis


class _InMemoryBackend:
    def __init__(self):
        self._data: Dict[str, bytes] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = threading.RLock()

    def _now(self):
        import time
        return time.time()

    def _purge(self, key: str):
        exp = self._expiry.get(key)
        if exp is not None and exp <= self._now():
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def set(self, key: str, value: bytes):
        with self._lock:
            self._data[key] = value
            self._expiry.pop(key, None)

    def setex(self, key: str, ex: int, value: bytes):
        with self._lock:
            self._data[key] = value
            self._expiry[key] = self._now() + ex

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            self._purge(key)
            return self._data.get(key)

    def delete(self, *keys: str):
        with self._lock:
            for k in keys:
                self._data.pop(k, None)
                self._expiry.pop(k, None)

    def exists(self, key: str) -> int:
        with self._lock:
            self._purge(key)
            return 1 if key in self._data else 0

    def keys(self, pattern: str) -> List[bytes]:
        import fnmatch
        with self._lock:
            res = []
            for k in list(self._data.keys()):
                self._purge(k)
                if fnmatch.fnmatch(k, pattern):
                    res.append(k.encode())
            return res

    def pipeline(self):
        return _InMemoryPipeline(self)


class _InMemoryPipeline:
    def __init__(self, backend: _InMemoryBackend):
        self._b = backend
        self._ops = []

    def set(self, key, value):
        self._ops.append(("set", key, value))
        return self

    def get(self, key):
        self._ops.append(("get", key))
        return self

    def delete(self, key):
        self._ops.append(("delete", key))
        return self

    def execute(self):
        out = []
        for op in self._ops:
            if op[0] == "set":
                self._b.set(op[1], op[2])
                out.append(True)
            elif op[0] == "get":
                out.append(self._b.get(op[1]))
            elif op[0] == "delete":
                self._b.delete(op[1])
                out.append(True)
        self._ops.clear()
        return out


class RedisStore:
    _LOCAL = None
    _GLOBAL = None
    _SHARED = {}
    _LOCK = threading.Lock()

    @classmethod
    def initialize_local_store(cls, in_memory: bool = False):
        with cls._LOCK:
            if cls._LOCAL is None:
                if in_memory:
                    backend = _InMemoryBackend()
                    cls._LOCAL = RedisStore(backend, "", is_memory=True)
                else:
                    r = redis.Redis.from_url("redis://localhost:6379", decode_responses=False)
                    cls._LOCAL = RedisStore(r, "", is_memory=False)
        return cls._LOCAL

    @classmethod
    def initialize_global_store(cls):
        with cls._LOCK:
            if cls._GLOBAL is None:
                url = os.getenv("REDIS_GLOBAL_STORE_HOST_URL")
                if not url:
                    raise RuntimeError("REDIS_GLOBAL_STORE_HOST_URL not set")
                r = redis.Redis.from_url(url, decode_responses=False)
                cls._GLOBAL = RedisStore(r, "", is_memory=False)
        return cls._GLOBAL

    @classmethod
    def initialize_shared_store(cls, redis_url: str):
        with cls._LOCK:
            if redis_url not in cls._SHARED:
                r = redis.Redis.from_url(redis_url, decode_responses=False)
                cls._SHARED[redis_url] = RedisStore(r, "", is_memory=False)
        return cls._SHARED[redis_url]

    @classmethod
    def get_local_store(cls, in_memory: bool = False):
        if cls._LOCAL is None:
            return cls.initialize_local_store(in_memory=in_memory)
        return cls._LOCAL

    @classmethod
    def get_global_store(cls):
        if cls._GLOBAL is None:
            return cls.initialize_global_store()
        return cls._GLOBAL

    @classmethod
    def get_shared_store(cls, redis_url: str):
        if redis_url not in cls._SHARED:
            return cls.initialize_shared_store(redis_url)
        return cls._SHARED[redis_url]

    def __init__(self, client, namespace: str, is_memory: bool):
        self._r = client
        self._ns = namespace.strip(":")
        self._is_memory = is_memory

    def _prefix(self, key: str) -> str:
        if not self._ns:
            return key
        return f"{self._ns}:{key}"

    def _serialize(self, value: Any) -> bytes:
        if value is None:
            return b"__none__"
        if isinstance(value, bytes):
            return b"__bytes__" + value
        if isinstance(value, str):
            return b"__str__" + value.encode()
        if isinstance(value, bool):
            return b"__bool__" + (b"1" if value else b"0")
        if isinstance(value, int):
            return b"__int__" + str(value).encode()
        if isinstance(value, float):
            return b"__float__" + repr(value).encode()
        if isinstance(value, (dict, list, tuple)):
            try:
                return b"__json__" + json.dumps(value).encode()
            except Exception:
                pass
        return b"__pickle__" + pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    def _deserialize(self, data: Optional[bytes]) -> Any:
        if data is None:
            return None
        if data == b"__none__":
            return None
        if data.startswith(b"__bytes__"):
            return data[9:]
        if data.startswith(b"__str__"):
            return data[7:].decode()
        if data.startswith(b"__bool__"):
            return data[8:] == b"1"
        if data.startswith(b"__int__"):
            return int(data[7:].decode())
        if data.startswith(b"__float__"):
            return float(data[9:].decode())
        if data.startswith(b"__json__"):
            return json.loads(data[8:].decode())
        if data.startswith(b"__pickle__"):
            return pickle.loads(data[10:])
        return pickle.loads(data)

    def get_namespace(self, name: str):
        name = name.strip(":")
        ns = name if not self._ns else f"{self._ns}:{name}"
        return RedisStore(self._r, ns, self._is_memory)

    def set(self, key: str, value: Any, ex: Optional[int] = None):
        k = self._prefix(key)
        v = self._serialize(value)
        if ex:
            self._r.setex(k, ex, v)
        else:
            self._r.set(k, v)

    def get(self, key: str, default=None):
        data = self._r.get(self._prefix(key))
        if data is None:
            return default
        return self._deserialize(data)

    def delete(self, key: str):
        self._r.delete(self._prefix(key))

    def exists(self, key: str) -> bool:
        return bool(self._r.exists(self._prefix(key)))

    def keys(self) -> List[str]:
        pattern = self._prefix("*")
        raw = self._r.keys(pattern)
        res = []
        base = f"{self._ns}:" if self._ns else ""
        for k in raw:
            s = k.decode()
            if base:
                s = s[len(base):]
            res.append(s)
        return res

    def list(self) -> List[str]:
        return self.keys()

    def values(self) -> List[Any]:
        return [self.get(k) for k in self.keys()]

    def items(self):
        return [(k, self.get(k)) for k in self.keys()]

    def clear(self):
        ks = [self._prefix(k) for k in self.keys()]
        if ks:
            self._r.delete(*ks)

    def update(self, mapping: Dict[str, Any]):
        pipe = self._r.pipeline()
        for k, v in mapping.items():
            pipe.set(self._prefix(k), self._serialize(v))
        pipe.execute()

    def pop(self, key: str, default=None):
        k = self._prefix(key)
        pipe = self._r.pipeline()
        pipe.get(k)
        pipe.delete(k)
        val, _ = pipe.execute()
        if val is None:
            return default
        return self._deserialize(val)

    def __getitem__(self, key: str):
        val = self.get(key)
        if val is None and not self.exists(key):
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)

    def __delitem__(self, key: str):
        if not self.exists(key):
            raise KeyError(key)
        self.delete(key)

    def __contains__(self, key: str):
        return self.exists(key)

    def __len__(self):
        return len(self.keys())

    def __iter__(self):
        return iter(self.keys())
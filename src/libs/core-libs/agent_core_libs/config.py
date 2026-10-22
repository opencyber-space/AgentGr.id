# config_manager.py
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple

from .common_cache import CommonCache

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO)


Validator = Callable[[str, Any], None]  # raise on invalid (key, value) -> None


class ConfigManager:
   

    def __init__(
        self,
        cache: CommonCache,
        *,
        namespace: str = "config",
        env_prefix: Optional[str] = None, 
        defaults: Optional[Mapping[str, Any]] = None,
        validator: Optional[Validator] = None,
        announce_changes: bool = True,
    ) -> None:
        self.cache = cache.with_namespace(namespace) if cache.namespace != namespace else cache
        self.namespace = self.cache.namespace
        self.env_prefix = (env_prefix or "").strip() or None
        self.defaults = dict(defaults or {})
        self.validator = validator
        self.announce_changes = announce_changes
        self._channel = f"{self.namespace}::changes"  # Pub/Sub channel name

    # ----------------------- Namespacing -----------------------

    def with_namespace(self, child: str) -> "ConfigManager":
        return ConfigManager(
            cache=self.cache.with_namespace(child),
            env_prefix=(self.env_prefix + child.upper() + "_") if self.env_prefix else None,
            defaults={},  # new layer by default; caller can pass their own
            validator=self.validator,
            announce_changes=self.announce_changes,
        )

    # ----------------------- Core GET / SET -----------------------

    def _validate(self, key: str, value: Any) -> None:
        if self.validator:
            self.validator(key, value)

    def set(self, key: str, value: Any, *, ttl: Optional[int] = None) -> None:
        """Set a config value with optional TTL (seconds)."""
        self._validate(key, value)
        ok = self.cache.set(key, value, ex=ttl)
        if not ok:
            raise RuntimeError(f"Failed to set config key: {key}")
        if self.announce_changes:
            self._publish_change("set", key, value, ttl)

    def get(self, key: str, default: Any = None) -> Any:
        """Layered read: ENV > Redis > Defaults > provided default."""
        # 1) ENV
        if self.env_prefix:
            env_key = self.env_prefix + key.upper().replace(".", "_")
            if env_key in os.environ:
                return os.environ[env_key]

        # 2) Redis
        val = self.cache.get(key, default=None)
        if val is not None:
            return val

        # 3) Defaults
        if key in self.defaults:
            return self.defaults[key]

        # 4) Fallback
        return default

    def exists(self, key: str) -> bool:
        return bool(self.cache.exists(key))

    def delete(self, key: str) -> bool:
        deleted = self.cache.delete(key)
        if deleted and self.announce_changes:
            self._publish_change("delete", key, None, None)
        return bool(deleted)

    # ----------------------- Typed getters -----------------------

    def get_str(self, key: str, default: Optional[str] = None) -> Optional[str]:
        v = self.get(key, default)
        return None if v is None else str(v)

    def get_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        v = self.get(key, default)
        return None if v is None else int(v)

    def get_float(self, key: str, default: Optional[float] = None) -> Optional[float]:
        v = self.get(key, default)
        return None if v is None else float(v)

    def get_bool(self, key: str, default: Optional[bool] = None) -> Optional[bool]:
        v = self.get(key, default)
        if isinstance(v, bool):
            return v
        if v is None:
            return default
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"Cannot coerce to bool: {v!r}")

    def get_json(self, key: str, default: Any = None) -> Any:
        v = self.get(key, default)
        if isinstance(v, (dict, list)):
            return v
        if v is None:
            return default
        try:
            return json.loads(v) if isinstance(v, str) else v
        except Exception:
            return default

    # ----------------------- Bulk ops -----------------------

    def set_many(self, mapping: Mapping[str, Any], *, ttl: Optional[int] = None) -> None:
        if ttl:
            # Need SET with ex per key for TTL; do pipeline
            pipe = self.cache.raw.pipeline()
            for k, v in mapping.items():
                self._validate(k, v)
                pipe.set(self.cache._k(k), self.cache._enc(v), ex=ttl)  # type: ignore[attr-defined]
            res = pipe.execute()
            if self.announce_changes:
                for (k, v) in mapping.items():
                    self._publish_change("set", k, v, ttl)
            if not all(res):
                raise RuntimeError("Partial failure in set_many with TTL")
        else:
            # mset and then single publish event (or per key if you prefer)
            for k, v in mapping.items():
                self._validate(k, v)
            self.cache.mset(mapping)
            if self.announce_changes:
                for (k, v) in mapping.items():
                    self._publish_change("set", k, v, None)

    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        keys = list(keys)
        vals = self.cache.mget(keys)
        out: Dict[str, Any] = {}
        for k, v in zip(keys, vals):
            out[k] = v if v is not None else (
                os.environ.get(self.env_prefix + k.upper().replace(".", "_")) if self.env_prefix else None
            )
            if out[k] is None:
                out[k] = self.defaults.get(k)
        return out

    # ----------------------- Defaults & schema -----------------------

    def set_defaults(self, defaults: Mapping[str, Any]) -> None:
        self.defaults.update(defaults)

    # ----------------------- Discovery & snapshots -----------------------

    def keys(self, pattern: str = "*") -> List[str]:
        """List logical keys in this namespace (pattern supports glob)."""
        # reuse CommonCache iterator which strips namespace
        return [k for k in self.cache._scan_keys_iter(pattern)]  # type: ignore[attr-defined]

    def snapshot(self) -> Dict[str, Any]:
        """Return a snapshot (dict) of all keys/values in the namespace (Redis only)."""
        out: Dict[str, Any] = {}
        for k in self:
            out[k] = self.cache.get(k)
        return out

    def load_snapshot(self, data: Mapping[str, Any], *, ttl: Optional[int] = None, clear_before: bool = False) -> None:
        if clear_before:
            self.cache.clear_namespace()
        self.set_many(data, ttl=ttl)

    # ----------------------- Iteration -----------------------

    def __iter__(self) -> Iterator[str]:
        yield from iter(self.cache)

    def __len__(self) -> int:
        return len(self.cache)

    # ----------------------- Change announcements -----------------------

    def _publish_change(self, op: str, key: str, value: Any, ttl: Optional[int]) -> None:
        try:
            msg = json.dumps({"op": op, "key": key, "value": value, "ttl": ttl, "ts": int(time.time())}, ensure_ascii=False)
            self.cache.raw.publish(self._channel, msg)
        except Exception:
            log.exception("Config change publish failed")

    # ----------------------- Watcher (Pub/Sub) -----------------------

    def watch(self, handler: Callable[[Dict[str, Any]], None], *, run_in_thread: bool = True):
       
        pubsub = self.cache.raw.pubsub()
        pubsub.subscribe(self._channel)

        def _loop():
            for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except Exception:
                    continue
                try:
                    handler(payload)
                except Exception:
                    log.exception("Config watcher handler error")

        if run_in_thread:
            t = threading.Thread(target=_loop, name=f"ConfigWatch:{self.namespace}", daemon=True)
            t.start()
            return t
        else:
            # generator interface
            def _gen():
                for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        try:
                            yield json.loads(msg["data"])
                        except Exception:
                            continue
            return _gen()

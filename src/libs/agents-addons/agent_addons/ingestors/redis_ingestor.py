import logging
from typing import Any, Dict, List, Optional, Union
import json
import redis

from .utils import BaseIngestor, VectorRow, stable_id

logger = logging.getLogger("RedisIngestor")

class RedisIngestor(BaseIngestor):
  

    def __init__(
        self,
        *,
        sink,
        model,
        collection: str,
        redis_url: str = "redis://localhost:6379/0",
        mode: str = "scan",              # "scan" | "stream" | "list"
        key_pattern: str = "docs:*",     # for scan
        stream_key: str = "docs_stream", # for stream mode
        list_key: str = "docs_list",     # for list mode
        block_ms: int = 5000,            # for stream/list BRPOP blocking
        max_read: Optional[int] = None,  # Stop after N entries (None = infinite for stream/list)
        **kwargs,
    ):
        super().__init__(sink=sink, model=model, collection=collection, **kwargs)
        self.r = redis.from_url(redis_url, decode_responses=False)
        self.mode = mode
        self.key_pattern = key_pattern
        self.stream_key = stream_key
        self.list_key = list_key
        self.block_ms = block_ms
        self.max_read = max_read

    def run(self) -> Dict[str, int]:
        if self.mode == "scan":
            return self._run_scan()
        if self.mode == "stream":
            return self._run_stream()
        if self.mode == "list":
            return self._run_list()
        raise ValueError("mode must be one of: scan | stream | list")

    # ---------- scan mode ----------

    def _run_scan(self) -> Dict[str, int]:
        seen = 0
        upserted = 0
        cursor = 0
        while True:
            cursor, keys = self.r.scan(cursor=cursor, match=self.key_pattern, count=500)
            for k in keys:
                try:
                    seen += 1
                    raw = self.r.get(k)
                    if not raw:
                        continue
                    text, md, forced_id = self._decode_payload(raw, key=k.decode())
                    if not text:
                        continue
                    rows = self._rows_from_text(text, base_md={"source": "redis", "redis_key": k.decode(), **md}, forced_id=forced_id)
                    if rows:
                        self._embed_and_upsert(rows)
                        upserted += len(rows)
                except Exception as e:
                    logger.exception(f"Failed ingest key={k}: {e}")
            if cursor == 0:
                break
        return {"seen": seen, "upserted": upserted}

    # ---------- stream mode ----------

    def _run_stream(self) -> Dict[str, int]:
        seen = 0
        upserted = 0
        read = 0
        last_id = "0-0"
        while self.max_read is None or read < self.max_read:
            try:
                resp = self.r.xread({self.stream_key: last_id}, block=self.block_ms, count=100)
                if not resp:
                    continue
                for (stream_name, entries) in resp:
                    for (entry_id, fields) in entries:
                        read += 1
                        seen += 1
                        last_id = entry_id
                        try:
                            payload = next(iter(fields.values()), b"")
                            text, md, forced_id = self._decode_payload(payload, key=f"{stream_name.decode()}:{entry_id.decode()}")
                            if not text:
                                continue
                            rows = self._rows_from_text(text, base_md={"source": "redis-stream", "redis_stream": stream_name.decode(), "entry_id": entry_id.decode(), **md}, forced_id=forced_id)
                            if rows:
                                self._embed_and_upsert(rows)
                                upserted += len(rows)
                        except Exception as inner:
                            logger.exception(f"Stream entry failed {entry_id}: {inner}")
            except Exception as e:
                logger.exception(f"Stream read error: {e}")
        return {"seen": seen, "upserted": upserted}

    # ---------- list mode ----------

    def _run_list(self) -> Dict[str, int]:
        seen = 0
        upserted = 0
        read = 0
        while self.max_read is None or read < self.max_read:
            try:
                # BRPOP returns (key, value) or None on timeout
                resp = self.r.brpop(self.list_key, timeout=int(self.block_ms / 1000))
                if not resp:
                    continue
                _, raw = resp
                read += 1
                seen += 1
                text, md, forced_id = self._decode_payload(raw, key=f"{self.list_key}")
                if not text:
                    continue
                rows = self._rows_from_text(text, base_md={"source": "redis-list", "redis_list": self.list_key, **md}, forced_id=forced_id)
                if rows:
                    self._embed_and_upsert(rows)
                    upserted += len(rows)
            except Exception as e:
                logger.exception(f"List read error: {e}")
        return {"seen": seen, "upserted": upserted}


    def _decode_payload(self, raw: bytes, *, key: str):
        
        forced_id = None
        try:
            s = raw.decode("utf-8")
            try:
                obj = json.loads(s)
                if isinstance(obj, dict) and "text" in obj:
                    text = str(obj.get("text") or "")
                    md = obj.get("metadata") or {}
                    forced_id = str(obj.get("id")) if obj.get("id") else None
                    return text, md, forced_id
                # fallback: flatten any JSON
                text = self.parser._flatten_json(obj)
                return text, {}, None
            except json.JSONDecodeError:
                # plain text
                return s, {}, None
        except Exception:
            # binary unsupported
            logger.warning(f"Unsupported binary payload at {key}, skipping.")
            return "", {}, None

    def _rows_from_text(self, text: str, *, base_md: Dict[str, Any], forced_id: Optional[str]) -> List[VectorRow]:
        rows: List[VectorRow] = []
        for offset, chunk_text in self.chunker.chunk(text):
            vid = forced_id or stable_id(base_md.get("redis_key", base_md.get("redis_stream", "redis")), str(base_md.get("entry_id", "")), str(offset))
            md = dict(base_md)
            rows.append(VectorRow(id=vid, values=[], metadata={**md, "__text__": chunk_text}))
        return rows

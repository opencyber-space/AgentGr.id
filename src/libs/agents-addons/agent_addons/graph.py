import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Union, Callable, Generator

import requests
from arango import ArangoClient
from arango.collection import Collection
from arango.exceptions import DocumentGetError

try:
    import boto3  # optional — required only for S3 ingestion
except Exception:  # pragma: no cover
    boto3 = None

logger = logging.getLogger("ArangoSDK")
logging.basicConfig(level=logging.INFO)

JSONLike = Union[Dict[str, Any], List[Dict[str, Any]]]


class ArangoSDK:
    def __init__(
        self,
        endpoint: str,
        db_name: str = "_system",
        username: Optional[str] = None,
        password: Optional[str] = None,
        jwt_token: Optional[str] = None,
        verify_ssl: bool = True,
        default_timeout: int = 60,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self._username = username
        self._password = password
        self._jwt_token = jwt_token
        self._endpoint = endpoint.rstrip("/")
        self._verify_ssl = verify_ssl
        self._timeout = default_timeout
        self._headers = dict(extra_headers or {})
        if jwt_token:
            self._headers["Authorization"] = f"Bearer {jwt_token}"

        # python-arango client
        self.client = ArangoClient(hosts=self._endpoint, request_timeout=self._timeout)

        # main DB handle (with creds if provided)
        if username and password:
            self.db = self.client.db(db_name, username=username, password=password)
        else:
            self.db = self.client.db(db_name)
        self._apply_auth_to_db(self.db)

        # raw HTTP session for admin/bulk
        self._http = requests.Session()
        self._http.verify = self._verify_ssl
        if self._headers:
            self._http.headers.update(self._headers)
        if username and password and not jwt_token:
            self._http.auth = (username, password)

    # ---------- helpers ----------

    def _apply_auth_to_db(self, db_handle):
        """Re-attach JWT to a db handle if provided."""
        if self._jwt_token:
            if hasattr(db_handle, "replace_jwt"):
                db_handle.replace_jwt(self._jwt_token)
            elif hasattr(db_handle, "update_jwt"):
                db_handle.update_jwt(self._jwt_token)

    def _sys_db(self):
        """Get _system DB with same auth used at init."""
        if self._username and self._password:
            db = self.client.db("_system", username=self._username, password=self._password)
        else:
            db = self.client.db("_system")
        self._apply_auth_to_db(db)
        return db

    def _db_path(self) -> str:
        db_name = getattr(self.db, "name", "_system")
        return f"/_db/{db_name}"

    # ---------------- Connection / AQL ----------------

    def switch_db(self, db_name: str, username: Optional[str] = None, password: Optional[str] = None) -> None:
        """
        Switch active database. If username/password are not provided,
        reuse the stored credentials (if any) so auth isn't dropped.
        """
        if username is None and password is None and self._username and self._password:
            username, password = self._username, self._password
        if username and password:
            self.db = self.client.db(db_name, username=username, password=password)
            # remember if caller explicitly overrides
            self._username, self._password = username, password
        else:
            self.db = self.client.db(db_name)
        self._apply_auth_to_db(self.db)

    def aql(self, query: str, bind_vars: Optional[Dict[str, Any]] = None, batch_size: int = 1000) -> List[Dict[str, Any]]:
        cursor = self.db.aql.execute(query, bind_vars=bind_vars or {}, batch_size=batch_size)
        return list(cursor)

    # ---------------- Database lifecycle (must use _system) ----------------

    def list_databases(self) -> List[str]:
        return self._sys_db().databases()

    def create_database(self, name: str, users: Optional[List[Dict[str, Any]]] = None, options: Optional[Dict[str, Any]] = None) -> bool:
        return self._sys_db().create_database(name=name, users=users or [])

    def delete_database(self, name: str) -> bool:
        return self._sys_db().delete_database(name)

    # ---------------- Collection lifecycle ----------------

    def has_collection(self, name: str) -> bool:
        return self.db.has_collection(name)

    def get_collection(self, name: str) -> Collection:
        return self.db.collection(name)

    def create_collection(
        self,
        name: str,
        edge: bool = False,
        replication_factor: Optional[int] = None,
        write_concern: Optional[int] = None,
        number_of_shards: Optional[int] = None,
        shard_keys: Optional[List[str]] = None,
        key_options: Optional[Dict[str, Any]] = None,
        schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Collection:
        options: Dict[str, Any] = {}
        if replication_factor is not None:
            options["replicationFactor"] = replication_factor
        if write_concern is not None:
            options["writeConcern"] = write_concern
        if number_of_shards is not None:
            options["numberOfShards"] = number_of_shards
        if shard_keys:
            options["shardKeys"] = shard_keys
        if key_options:
            options["keyOptions"] = key_options
        if schema:
            options["schema"] = schema
        options.update(kwargs or {})
        return self.db.create_collection(name=name, edge=edge, **options)

    def delete_collection(self, name: str, ignore_missing: bool = True) -> bool:
        col = self.db.collection(name)
        return col.delete(ignore_missing=ignore_missing)

    # ---------------- CRUD ----------------

    def insert_one(self, collection: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        return self.db.collection(collection).insert(doc)

    def insert_many(self, collection: str, docs: Iterable[Dict[str, Any]], overwrite: bool = False, batch_size: int = 1000) -> Dict[str, Any]:
        col = self.db.collection(collection)
        result = {"inserted": 0, "errors": 0}
        batch: List[Dict[str, Any]] = []
        for d in docs:
            batch.append(d)
            if len(batch) >= batch_size:
                res = col.insert_many(batch, overwrite=overwrite, silent=False)
                result["inserted"] += len([r for r in res if isinstance(r, dict) and r.get("_id")])
                result["errors"] += len([r for r in res if isinstance(r, dict) and r.get("error")])
                batch = []
        if batch:
            res = col.insert_many(batch, overwrite=overwrite, silent=False)
            result["inserted"] += len([r for r in res if isinstance(r, dict) and r.get("_id")])
            result["errors"] += len([r for r in res if isinstance(r, dict) and r.get("error")])
        return result

    def get_one(self, collection: str, key_or_id: str) -> Optional[Dict[str, Any]]:
        col = self.db.collection(collection)
        try:
            doc = col.get(key_or_id)
        except DocumentGetError:
            return None
        if doc is None:
            return None
        # strip system fields except _key
        return {k: v for k, v in doc.items() if k not in ("_id", "_rev")}

    def update_one(self, collection: str, key_or_doc: Union[str, Dict[str, Any]], merge_objects: bool = True, keep_none: bool = True) -> Dict[str, Any]:
        doc = key_or_doc if isinstance(key_or_doc, dict) else {"_key": key_or_doc}
        return self.db.collection(collection).update(doc, merge=merge_objects, keep_none=keep_none)

    def replace_one(self, collection: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        return self.db.collection(collection).replace(doc)

    def delete_one(self, collection: str, key_or_id: str, ignore_missing: bool = True) -> bool:
        col = self.db.collection(collection)
        res = col.delete(key_or_id, ignore_missing=ignore_missing)
        return bool(res)

    def upsert_many(
        self,
        collection: str,
        docs: Iterable[Dict[str, Any]],
        on: str = "_key",
        update_expr: Optional[str] = None,
        batch_size: int = 1000,
    ) -> int:
        update_expr = update_expr or "MERGE(OLD, NEW)"
        aql = f"""
        FOR NEW IN @batch
          UPSERT {{ {on}: NEW.{on} }}
          INSERT NEW
          UPDATE {update_expr}
          IN @@col
        """
        total = 0
        buf: List[Dict[str, Any]] = []
        for d in docs:
            if on not in d:
                raise ValueError(f"upsert_many requires key '{on}' in each doc")
            buf.append(d)
            if len(buf) >= batch_size:
                self.db.aql.execute(aql, bind_vars={"batch": buf, "@col": collection})
                total += len(buf)
                buf = []
        if buf:
            self.db.aql.execute(aql, bind_vars={"batch": buf, "@col": collection})
            total += len(buf)
        return total

    # ---------------- High-throughput HTTP bulk import (DB-scoped) ----------------
    def http_bulk_import(
    self,
    collection: Optional[str] = None,
    docs: Optional[Iterable[Dict[str, Any]]] = None,
    jsonl_path: Optional[str] = None,
    on_duplicate: str = "error",  # "error" | "update" | "replace" | "ignore"
    details: bool = False,
    batch_size: int = 5000,
    ) -> Dict[str, Any]:
    
        if not collection:
            raise ValueError("collection is required")

        col = self.db.collection(collection)
        stats = {"created": 0, "updated": 0, "ignored": 0, "errors": 0}

        def _accumulate(res: Dict[str, Any], fallback_count: int = 0) -> None:
            # Res from import_bulk should have these keys; be defensive anyway.
            stats["created"] += int(res.get("created", 0))
            stats["updated"] += int(res.get("updated", 0))
            stats["ignored"] += int(res.get("ignored", 0))
            stats["errors"]  += int(res.get("errors",  0))
            # If none present (unlikely), assume created == fallback_count
            if res.get("created") is None and res.get("updated") is None and res.get("ignored") is None and res.get("errors") is None:
                stats["created"] += int(fallback_count)

        def _chunks(seq: Iterable[Dict[str, Any]], size: int):
            buf: List[Dict[str, Any]] = []
            for s in seq:
                buf.append(s)
                if len(buf) >= size:
                    yield buf
                    buf = []
            if buf:
                yield buf

        if docs is not None:
            for chunk in _chunks(docs, batch_size):
                res = col.import_bulk(
                    documents=chunk,
                    on_duplicate=on_duplicate,
                    details=details,
                )
                _accumulate(res, fallback_count=len(chunk))

        elif jsonl_path:
            # Read file as either JSON array or JSONL
            with open(jsonl_path, "r", encoding="utf-8") as f:
                first = f.read(1)
                f.seek(0)
                if first == "[":
                    arr = json.load(f)
                    for chunk in _chunks(arr, batch_size):
                        res = col.import_bulk(
                            documents=chunk,
                            on_duplicate=on_duplicate,
                            details=details,
                        )
                        _accumulate(res, fallback_count=len(chunk))
                else:
                    # stream JSONL lines in chunks
                    buf: List[Dict[str, Any]] = []
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        buf.append(json.loads(line))
                        if len(buf) >= batch_size:
                            res = col.import_bulk(
                                documents=buf,
                                on_duplicate=on_duplicate,
                                details=details,
                            )
                            _accumulate(res, fallback_count=len(buf))
                            buf = []
                    if buf:
                        res = col.import_bulk(
                            documents=buf,
                            on_duplicate=on_duplicate,
                            details=details,
                        )
                        _accumulate(res, fallback_count=len(buf))
        else:
            raise ValueError("Provide either docs or jsonl_path")

        return stats

    @staticmethod
    def _iter_json_file(path: str):
    
        with open(path, "r", encoding="utf-8") as f:
            first_char = f.read(1)
            f.seek(0)
            if first_char == "[":
                data = json.load(f)
                for obj in data:
                    yield obj
            else:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)


    def ingest_from_file(
        self,
        collection: str,
        path: str,
        batch_size: int = 1000,
        upsert_on: Optional[str] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        use_http_bulk: bool = False,
        on_duplicate: str = "error",
    ) -> Dict[str, Any]:
        it = (transform(obj) if transform else obj for obj in self._iter_json_file(path))
        if use_http_bulk and not upsert_on:
            stats = self.http_bulk_import(collection=collection, docs=it, on_duplicate=on_duplicate, batch_size=batch_size)
            stats["method"] = "http_bulk_import"
            return stats
        if upsert_on:
            processed = self.upsert_many(collection, it, on=upsert_on, batch_size=batch_size)
            return {"processed": processed, "method": "upsert"}
        else:
            stat = self.insert_many(collection, it, batch_size=batch_size)
            stat["method"] = "insert_many"
            return stat

    def ingest_from_s3(
        self,
        collection: str,
        bucket: str,
        key: str,
        aws_region: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        batch_size: int = 1000,
        upsert_on: Optional[str] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        use_http_bulk: bool = False,
        on_duplicate: str = "error",
    ) -> Dict[str, Any]:
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 ingestion")

        session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=aws_region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        )
        s3 = session.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read().decode("utf-8")

        def _gen() -> Iterable[Dict[str, Any]]:
            nonlocal body
            body_stripped = body.lstrip()
            if body_stripped.startswith("["):
                for x in json.loads(body):
                    yield transform(x) if transform else x
            else:
                for line in body.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    x = json.loads(line)
                    yield transform(x) if transform else x

        if use_http_bulk and not upsert_on:
            stats = self.http_bulk_import(collection=collection, docs=_gen(), on_duplicate=on_duplicate, batch_size=batch_size)
            stats["method"] = "http_bulk_import"
            return stats

        if upsert_on:
            processed = self.upsert_many(collection, _gen(), on=upsert_on, batch_size=batch_size)
            return {"processed": processed, "method": "upsert"}
        else:
            stat = self.insert_many(collection, _gen(), batch_size=batch_size)
            stat["method"] = "insert_many"
            return stat

    # ---------------- Management / Admin helpers ----------------

    def _get_json_or_text(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text}

    def server_status(self) -> Dict[str, Any]:
        r = self._http.get(f"{self._endpoint}/_admin/status", timeout=self._timeout)
        r.raise_for_status()
        return self._get_json_or_text(r)

    def server_role(self) -> Dict[str, Any]:
        r = self._http.get(f"{self._endpoint}/_admin/server/role", timeout=self._timeout)
        r.raise_for_status()
        return self._get_json_or_text(r)

    def cluster_health(self) -> Dict[str, Any]:
        r = self._http.get(f"{self._endpoint}/_admin/cluster/health", timeout=self._timeout)
        r.raise_for_status()
        return self._get_json_or_text(r)

    def routing_reload(self) -> Dict[str, Any]:
        r = self._http.post(f"{self._endpoint}/_admin/routing/reload", timeout=self._timeout)
        r.raise_for_status()
        return self._get_json_or_text(r)

    def run_admin_command(self, path: str, method: str = "GET", json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        m = method.upper()
        resp = self._http.request(m, url, json=json_body, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return self._get_json_or_text(resp)
    
    def ensure_collection(
        self,
        name: str,
        create_if_missing: bool = True,
        **create_kwargs,
    ) -> Collection:
    
        if self.has_collection(name):
            return self.get_collection(name)
        if not create_if_missing:
            raise ValueError(f"Collection '{name}' does not exist.")
        return self.create_collection(name, **create_kwargs)

# tests/test_all.py
from __future__ import annotations

import os
import sys
import io
import json
import tempfile
from pathlib import Path

# Import your libs
# Adjust imports if your modules expose different names
from agent_core_libs.common_cache import CommonCache
from agent_core_libs.config import ConfigManager
from agent_core_libs.sql_inface import SQLHelper, SQLHelperConfig
from agent_core_libs.storage import S3Storage
from agent_core_libs.web_scrapping import ScrapySDK


def ok(msg): print(f"[ OK ] {msg}")
def skip(msg): print(f"[SKIP] {msg}")
def fail(msg):
    print(f"[FAIL] {msg}")
    return False


def test_common_cache() -> bool:
    print("\n== CommonCache ==")
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache = CommonCache(default_url=url, namespace="test_acore")

    try:
        # dict-like
        cache["alpha"] = {"x": 1}
        if cache["alpha"]["x"] != 1:
            return fail("dict set/get mismatch")

        # batch ops / exists / ttl
        cache.mset({"k1": "v1", "k2": 2})
        got = cache.mget(["k1", "k2", "k3"])
        if got != ["v1", 2, None]:
            return fail("mset/mget mismatch")

        cache.set("tmp", "v", ex=2)
        if not cache.exists("tmp"):
            return fail("exists(tmp)=False unexpectedly")

        # namespacing
        sub = cache.with_namespace("sub")
        sub["n"] = 42
        if sub["n"] != 42:
            return fail("namespace set/get failed")

        # cleanup
        deleted = sub.clear_namespace()
        ok(f"cleared {deleted} keys in sub-namespace")

        ok("CommonCache basic ops")
        return True

    except Exception as e:
        return fail(f"CommonCache error: {e}")


def test_config_manager() -> bool:
    print("\n== ConfigManager ==")
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache = CommonCache(default_url=url, namespace="test_cfgroot")
    cfg = ConfigManager(cache, namespace="appcfg", env_prefix="APP_", defaults={"mode": "dev"})

    try:
        cfg.set("db.url", "sqlite:///test.db")
        if not cfg.get_str("db.url", ""):
            return fail("get_str returned empty for db.url")

        if cfg.get("mode") != "dev":
            return fail("defaults not applied for 'mode'")

        # typed getters
        cfg.set("workers", 8)
        if cfg.get_int("workers") != 8:
            return fail("get_int(workers) != 8")

        # bulk
        cfg.set_many({"a": 1, "b": True})
        many = cfg.get_many(["a", "b", "c"])
        if many["a"] != 1 or many["b"] is not True:
            return fail("get_many mismatch")

        # namespacing
        agent = cfg.with_namespace("agent:123")
        agent.set("temperature", 0.25)
        if abs(agent.get_float("temperature") - 0.25) > 1e-9:
            return fail("namespaced float getter mismatch")

        ok("ConfigManager basic ops")
        return True

    except Exception as e:
        return fail(f"ConfigManager error: {e}")


def test_sql_helper() -> bool:
    print("\n== SQLHelper (SQLite in-memory) ==")
    try:
        db = SQLHelper(SQLHelperConfig(url="sqlite+pysqlite:///:memory:", echo=False))
        db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            name  TEXT,
            age   INTEGER
        )
        """)
        db.bulk_execute(
            "INSERT INTO users (email, name, age) VALUES (:email, :name, :age)",
            [
                {"email": "a@example.com", "name": "A", "age": 7},
                {"email": "b@example.com", "name": "B", "age": 11},
            ],
        )
        n = db.fetch_val("SELECT COUNT(*) FROM users")
        if n != 2:
            return fail(f"row count expected 2, got {n}")

        row = db.fetch_one("SELECT name FROM users WHERE email=:e", {"e": "a@example.com"})
        if not row or row.get("name") != "A":
            return fail("fetch_one mismatch")

        # Upsert semantics (sqlite ON CONFLICT)
        db.upsert(
            table="users",
            row={"id": 1, "email": "a@example.com", "name": "Ava", "age": 8},
            conflict_keys=["id"],
            update_columns=["name", "age"],
        )
        name = db.fetch_val("SELECT name FROM users WHERE id=1")
        if name != "Ava":
            return fail("upsert failed to update name")

        ok("SQLHelper basic ops")
        return True

    except Exception as e:
        return fail(f"SQLHelper error: {e}")


def test_s3storage_optional() -> bool:
    print("\n== S3Storage (optional) ==")
    # Skip unless we have creds & bucket
    ak = os.getenv("AWS_ACCESS_KEY_ID")
    sk = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("TEST_S3_BUCKET")
    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint = os.getenv("AWS_S3_ENDPOINT_URL")  # for MinIO/localstack if provided

    if not (ak and sk and bucket):
        skip("S3 test skipped (set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, TEST_S3_BUCKET to enable)")
        return True

    try:
        s3 = S3Storage(
            access_key_id=ak,
            secret_access_key=sk,
            region_name=region,
            endpoint_url=endpoint or None,
        )
        # create bucket if needed (no-op if exists)
        try:
            s3.create_bucket(bucket)
        except Exception:
            pass

        key = "agent-core-libs/test-object.txt"
        payload = b"hello s3"

        # upload bytes
        s3.upload_bytes(bucket, key, payload, extra_args={"ContentType": "text/plain"})
        # head
        meta = s3.head_object(bucket, key)
        if int(meta.get("ContentLength", -1)) != len(payload):
            return fail("S3 head content length mismatch")

        # download as bytes
        got = s3.download_as_bytes(bucket, key)
        if got != payload:
            return fail("S3 download mismatch")

        # copy & delete
        s3.copy_object(bucket, key, bucket, key + ".copy")
        s3.delete_object(bucket, key)
        s3.delete_object(bucket, key + ".copy")

        ok("S3Storage basic ops")
        return True

    except Exception as e:
        return fail(f"S3Storage error: {e}")


def test_scrapy_sdk() -> bool:
    print("\n== ScrapySDK ==")
    try:
        sdk = ScrapySDK().set_user_agent("AgentCoreLibsTest/1.0").collect_items_in_memory(True)
        items = sdk.fetch(
            ["https://example.com"],
            parse=lambda r: [{"url": r.url, "title": (r.css("title::text").get() or "").strip()}],
        )
        if not items or "Example Domain" not in items[0].get("title", ""):
            return fail("ScrapySDK did not extract expected title from example.com")
        ok("ScrapySDK basic crawl")
        return True
    except Exception as e:
        return fail(f"ScrapySDK error: {e}")


def main():
    required = [
        test_common_cache,
        test_config_manager,
        test_sql_helper,
        test_scrapy_sdk,
    ]
    optional = [
        test_s3storage_optional,  # skipped unless env present
    ]

    results = []
    for fn in required:
        results.append(fn())
    for fn in optional:
        results.append(fn())

    print("\n== Summary ==")
    total = len(results)
    passed = sum(bool(r) for r in results)
    print(f"Passed {passed}/{total} checks.")

    # Fail build if any required check failed
    if not all(results[:len(required)]):
        sys.exit(1)


if __name__ == "__main__":
    main()

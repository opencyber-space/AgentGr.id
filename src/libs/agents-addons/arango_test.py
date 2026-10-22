from __future__ import annotations

import io
import json
import os
import time
import uuid
import pathlib
import tempfile
from typing import Dict, Any, List, Iterable

import pytest
import requests

from agent_addons.graph import ArangoSDK


# ---------- Helpers ----------

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v

REQUIRED_VARS = ["ARANGO_ENDPOINT", "ARANGO_DB_NAME", "ARANGO_USERNAME", "ARANGO_PASSWORD"]


def _can_reach(endpoint: str) -> bool:
    try:
        username = os.getenv("ARANGO_USERNAME", "root")
        password = os.getenv("ARANGO_PASSWORD", "root")
        r = requests.get(
            endpoint.rstrip("/") + "/_api/version",
            auth=(username, password),
            timeout=5,
            verify=False,
        )
        return r.ok
    except Exception:
        return False

def pytest_collection_modifyitems(config, items):
    # Group integration tests visually
    for it in items:
        it.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def arango_root_sdk():
    """Connects to the bootstrap DB (likely _system) with credentials."""
    endpoint = _env("ARANGO_ENDPOINT", "http://127.0.0.1:8529")
    db_name = _env("ARANGO_DB_NAME", "_system")
    username = _env("ARANGO_USERNAME")
    password = _env("ARANGO_PASSWORD")

    # Skip if we can't reach the server or env not set
    missing = [k for k in REQUIRED_VARS if not _env(k)]
    if missing:
        pytest.skip(f"Missing env vars for live tests: {missing}")

    if not _can_reach(endpoint):
        pytest.skip(f"ArangoDB not reachable at {endpoint}")

    sdk = ArangoSDK(
        endpoint=endpoint,
        db_name=db_name,
        username=username,
        password=password,
        verify_ssl=False,   # for convenience; set True in prod
    )
    return sdk


@pytest.fixture()
def temp_db(arango_root_sdk: ArangoSDK):
    """Create a temporary DB for isolation and drop it after."""
    tmp_name = f"test_{uuid.uuid4().hex[:8]}"
    created = arango_root_sdk.create_database(tmp_name)
    assert created is True

    # Switch the sdk to the temp DB
    arango_root_sdk.switch_db(tmp_name)

    yield tmp_name

    # Switch back and delete temp db
    arango_root_sdk.switch_db(_env("ARANGO_DB_NAME", "_system"))
    ok = arango_root_sdk.delete_database(tmp_name)
    assert ok is True


@pytest.fixture()
def temp_col_name() -> str:
    return f"col_{uuid.uuid4().hex[:6]}"


# ---------- Tests ----------

def test_server_status_and_role(arango_root_sdk: ArangoSDK):
    st = arango_root_sdk.server_status()
    assert isinstance(st, dict) and st

    role = arango_root_sdk.server_role()
    assert isinstance(role, dict) and "role" in role

    # routing reload should succeed on single server/cluster
    rr = arango_root_sdk.routing_reload()
    assert isinstance(rr, dict) or isinstance(rr, list)


def test_database_lifecycle(arango_root_sdk: ArangoSDK):
    name = f"db_{uuid.uuid4().hex[:8]}"
    assert arango_root_sdk.create_database(name) is True
    dbs = arango_root_sdk.list_databases()
    assert name in dbs
    assert arango_root_sdk.delete_database(name) is True


def test_ensure_collection_and_basic_crud(arango_root_sdk: ArangoSDK, temp_db: str, temp_col_name: str):
    col = arango_root_sdk.ensure_collection(temp_col_name)
    assert col is not None

    # Insert one
    res = arango_root_sdk.insert_one(temp_col_name, {"_key": "k1", "a": 1, "b": "x"})
    assert "_id" in res

    # Get
    got = arango_root_sdk.get_one(temp_col_name, "k1")
    assert got and got["a"] == 1

    # Update
    up = arango_root_sdk.update_one(temp_col_name, {"_key": "k1", "a": 2})
    assert up["_key"] == "k1"
    assert arango_root_sdk.get_one(temp_col_name, "k1")["a"] == 2

    # Replace
    rp = arango_root_sdk.replace_one(temp_col_name, {"_key": "k1", "z": 9})
    assert rp["_key"] == "k1"
    g2 = arango_root_sdk.get_one(temp_col_name, "k1")
    assert g2 == {"_key": "k1", "z": 9}

    # Delete
    assert arango_root_sdk.delete_one(temp_col_name, "k1") is True
    assert arango_root_sdk.get_one(temp_col_name, "k1") is None


def test_insert_many_and_aql_query(arango_root_sdk: ArangoSDK, temp_db: str, temp_col_name: str):
    arango_root_sdk.ensure_collection(temp_col_name)
    docs = [{"_key": f"k{i}", "v": i} for i in range(100)]
    stat = arango_root_sdk.insert_many(temp_col_name, docs, batch_size=17)
    assert stat["inserted"] == 100
    # Query via AQL
    rows = arango_root_sdk.aql(
        f"FOR d IN @@c FILTER d.v >= 90 RETURN d",
        bind_vars={"@c": temp_col_name},
        batch_size=20,
    )
    assert len(rows) == 10


def test_upsert_many(arango_root_sdk: ArangoSDK, temp_db: str, temp_col_name: str):
    arango_root_sdk.ensure_collection(temp_col_name)
    docs = [{"_key": f"k{i}", "n": i} for i in range(5)]
    arango_root_sdk.insert_many(temp_col_name, docs)

    # Modify 2, add 2 more
    ups = [{"_key": "k2", "n": 200}, {"_key": "k4", "n": 400}, {"_key": "k5", "n": 500}, {"_key": "k6", "n": 600}]
    total = arango_root_sdk.upsert_many(temp_col_name, ups, on="_key", update_expr="MERGE(OLD, NEW)", batch_size=2)
    assert total == 4

    # Validate
    got = arango_root_sdk.aql(
        "FOR d IN @@c FILTER d._key IN ['k2','k4','k5','k6'] SORT d._key RETURN d",
        bind_vars={"@c": temp_col_name},
    )
    by_key = {d["_key"]: d["n"] for d in got}
    assert by_key == {"k2": 200, "k4": 400, "k5": 500, "k6": 600}


def test_http_bulk_import_with_docs(arango_root_sdk: ArangoSDK, temp_db: str, temp_col_name: str):
    arango_root_sdk.ensure_collection(temp_col_name)
    docs = [{"_key": f"x{i}", "w": i} for i in range(30)]
    stats = arango_root_sdk.http_bulk_import(collection=temp_col_name, docs=docs, on_duplicate="update", batch_size=13)
    # created+updated should reflect total
    total_seen = (stats.get("created", 0) + stats.get("updated", 0) + stats.get("ignored", 0))
    assert total_seen == 30


def test_ingest_from_file_json_and_jsonl(arango_root_sdk: ArangoSDK, temp_db: str, temp_col_name: str, tmp_path: pathlib.Path):
    arango_root_sdk.ensure_collection(temp_col_name)

    # JSON array file
    arr_path = tmp_path / "arr.json"
    with arr_path.open("w", encoding="utf-8") as f:
        json.dump([{"_key": "a1", "t": 1}, {"_key": "a2", "t": 2}], f)

    stat1 = arango_root_sdk.ingest_from_file(temp_col_name, str(arr_path), batch_size=1)
    assert stat1["method"] == "insert_many"
    assert stat1["inserted"] == 2

    # JSONL file
    jsonl_path = tmp_path / "data.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"_key": "l1", "u": 11}) + "\n")
        f.write(json.dumps({"_key": "l2", "u": 22}) + "\n")

    stat2 = arango_root_sdk.ingest_from_file(temp_col_name, str(jsonl_path), batch_size=2, use_http_bulk=True, on_duplicate="update")
    # http bulk returns created/updated counts rather than "inserted"
    assert stat2["method"] == "http_bulk_import"
    total_seen = (stat2.get("created", 0) + stat2.get("updated", 0) + stat2.get("ignored", 0))
    assert total_seen == 2


'''@pytest.mark.skipif(not os.getenv("S3_BUCKET"), reason="S3 credentials/keys not provided")
def test_ingest_from_s3_optional(arango_root_sdk: ArangoSDK, temp_db: str, tmp_path: pathlib.Path):
    # This assumes your S3 object is JSONL or JSON array of docs with _key.
    bucket = os.environ["S3_BUCKET"]
    key = os.environ["S3_KEY"]
    col = f"col_{uuid.uuid4().hex[:6]}"
    arango_root_sdk.ensure_collection(col)
    stat = arango_root_sdk.ingest_from_s3(
        collection=col,
        bucket=bucket,
        key=key,
        aws_region=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        use_http_bulk=True,
        on_duplicate="update",
    )
    assert stat["method"] in ("upsert", "insert_many", "http_bulk_import")
    # basic sanity on returned counters
    total = sum(stat.get(k, 0) for k in ("processed", "inserted", "created", "updated", "ignored"))
    assert total >= 0'''

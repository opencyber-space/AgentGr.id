# Agent Object Storage

This document describes how to use the `S3Storage` class from the `agent_core_libs` package to work with an S3-compatible object storage backend (AWS S3, MinIO, Ceph, etc.).

---

### Introduction

`S3Storage` is a thin wrapper around `boto3` that provides:

* Uploads from a file path, `bytes`, a file object, or a JSON-serializable object.
* Downloads to a file path, a file object, `bytes`, or parsed JSON.
* Server-side copy and move.
* Deleting single objects or everything under a prefix.
* Listing and iterating objects, reading metadata, and existence checks.
* Bucket helpers and presigned URLs.

It supports:

* Access-key and session-token authentication.
* Custom endpoints (MinIO and other S3-compatible stores), with optional path-style addressing.
* Automatic retries (standard retry mode) and multipart transfers for large files.

All methods log success, and log then re-raise `botocore` `ClientError` / `BotoCoreError` on failure.

---

### Installation

`S3Storage` is part of `agent_core_libs` (`libs/core-libs`), which depends on `boto3>=1.34.0`.

```bash
pip install ./libs/core-libs
```

### Import

```python
from agent_core_libs.storage import S3Storage
```

---

### Usage

#### Initialize the client

All arguments are keyword-only.

```python
store = S3Storage(
    access_key_id="your-access-key",
    secret_access_key="your-secret-key",
    region_name="us-east-1",
)
```

| Argument | Default | Description |
|---|---|---|
| `access_key_id` | — (required) | Access key |
| `secret_access_key` | — (required) | Secret key |
| `region_name` | `"us-east-1"` | Region |
| `session_token` | `None` | Session token for temporary credentials |
| `endpoint_url` | `None` | Custom S3 endpoint (e.g. MinIO) |
| `max_attempts` | `10` | Maximum retry attempts |
| `multipart_threshold_mb` | `8` | Use multipart transfers above this size (MB) |
| `multipart_chunksize_mb` | `8` | Multipart chunk size (MB) |
| `use_path_style` | `False` | Use path-style addressing (`endpoint/bucket/key`) |
| `logger` | module logger | Custom `logging.Logger` |

---

#### Upload a file from a path

```python
store.upload_file("my-bucket", "my-folder/my-file.txt", "/path/to/local/file.txt")

# With extra S3 arguments
store.upload_file(
    "my-bucket", "docs/report.pdf", "/tmp/report.pdf",
    extra_args={"ContentType": "application/pdf", "ACL": "private"},
)
```

#### Upload bytes

```python
store.upload_bytes("my-bucket", "data/hello.txt", b"Hello, world!")
```

#### Upload from a file object (e.g. `BytesIO`)

```python
import io

buffer = io.BytesIO(b"Buffered content")
store.upload_fileobj("my-bucket", "buffer/file.txt", buffer)
```

#### Upload JSON

```python
store.put_json("my-bucket", "configs/settings.json", {"threshold": 0.8})
# Stored with ContentType "application/json"
```

---

#### Download to a local path

```python
store.download_file("my-bucket", "my-folder/my-file.txt", "/path/to/save/file.txt")
```

#### Download to a file object

```python
import io

output_buffer = io.BytesIO()
store.download_to_fileobj("my-bucket", "data/hello.txt", output_buffer)
print(output_buffer.getvalue())
```

#### Download as `bytes`

```python
data = store.download_as_bytes("my-bucket", "data/hello.txt")
print(data.decode())
```

#### Read JSON

```python
settings = store.get_json("my-bucket", "configs/settings.json")
```

---

#### Copy and move

```python
store.copy_object("src-bucket", "a/file.txt", "dest-bucket", "b/file.txt")
store.move_object("src-bucket", "a/file.txt", "dest-bucket", "b/file.txt")  # copy, then delete source
```

#### Delete

```python
store.delete_object("my-bucket", "data/hello.txt")

deleted_count = store.delete_prefix("my-bucket", "tmp/")   # deletes in batches of 1000
```

---

#### List and inspect objects

```python
objects = store.list_objects("my-bucket", prefix="data/", max_keys=100)
for obj in objects:
    print(obj["Key"], obj["Size"], obj["LastModified"])

# Lazily iterate over all objects under a prefix
for obj in store.iter_objects("my-bucket", prefix="logs/"):
    print(obj["Key"])

meta = store.head_object("my-bucket", "data/hello.txt")   # metadata only, no body
store.exists("my-bucket", "data/hello.txt")               # True / False
```

---

#### Buckets and presigned URLs

```python
store.bucket_exists("my-bucket")      # True / False
store.create_bucket("my-bucket")      # no-op if it already exists

url = store.presigned_url("my-bucket", "data/hello.txt", expires_in=3600)              # download URL
put_url = store.presigned_url("my-bucket", "uploads/new.bin", method="put_object")     # upload URL
```

---

### Custom Object Storage (MinIO, Ceph, …)

Pass the store's endpoint as `endpoint_url`. Most self-hosted stores also need path-style addressing:

```python
store = S3Storage(
    access_key_id="your-key",
    secret_access_key="your-secret",
    region_name="us-east-1",
    endpoint_url="https://your-custom-object-store.local",
    use_path_style=True,
)
```

All methods work the same way against the custom endpoint.

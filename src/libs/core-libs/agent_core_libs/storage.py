from __future__ import annotations

import io
import json
import logging
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from boto3.s3.transfer import TransferConfig


log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO)


class S3Storage:
   

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        region_name: str = "us-east-1",
        session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,   # e.g. MinIO / custom S3
        max_attempts: int = 10,
        multipart_threshold_mb: int = 8,      # multipart above this size
        multipart_chunksize_mb: int = 8,
        use_path_style: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.log = logger or log

        self._config = BotoConfig(
            retries={"max_attempts": max_attempts, "mode": "standard"},
            s3={"addressing_style": "path" if use_path_style else "auto"},
            user_agent_extra="S3Storage/1.0",
        )

        self._transfer_cfg = TransferConfig(
            multipart_threshold=multipart_threshold_mb * 1024 * 1024,
            multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
            max_concurrency=8,
            use_threads=True,
        )

        self._session = boto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            region_name=region_name,
        )

        self._client = self._session.client("s3", endpoint_url=endpoint_url, config=self._config)
        self._resource = self._session.resource("s3", endpoint_url=endpoint_url, config=self._config)

    # ----------------------- Core helpers -----------------------

    def _handle_err(self, e: Exception, msg: str) -> None:
        if isinstance(e, ClientError):
            code = e.response.get("Error", {}).get("Code")
            self.log.error("%s | ClientError: %s | %s", msg, code, e, exc_info=True)
        else:
            self.log.error("%s | %s", msg, e, exc_info=True)

    # ----------------------- CREATE / UPDATE -----------------------

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_path: str,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Upload local file -> s3://bucket/key
        extra_args example: {"ContentType": "application/pdf", "ACL": "private"}
        """
        try:
            self._client.upload_file(
                Filename=file_path,
                Bucket=bucket,
                Key=key,
                ExtraArgs=extra_args or {},
                Config=self._transfer_cfg,
            )
            self.log.info("Uploaded file to s3://%s/%s", bucket, key)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"upload_file({bucket}, {key})")
            raise

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upload bytes buffer -> s3://bucket/key"""
        return self.upload_fileobj(bucket, key, io.BytesIO(data), extra_args=extra_args)

    def upload_fileobj(
        self,
        bucket: str,
        key: str,
        fileobj: io.BufferedIOBase,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upload open file object -> s3://bucket/key"""
        try:
            self._client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=bucket,
                Key=key,
                ExtraArgs=extra_args or {},
                Config=self._transfer_cfg,
            )
            self.log.info("Uploaded stream to s3://%s/%s", bucket, key)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"upload_fileobj({bucket}, {key})")
            raise

    def put_json(self, bucket: str, key: str, obj: Any, *, extra_args: Optional[Dict[str, Any]] = None) -> None:
        """Convenience: JSON -> s3://bucket/key"""
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        args = {"ContentType": "application/json"}
        if extra_args:
            args.update(extra_args)
        self.upload_bytes(bucket, key, data, extra_args=args)

    def copy_object(
        self,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Server-side copy within S3."""
        try:
            copy_source = {"Bucket": src_bucket, "Key": src_key}
            self._client.copy(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key, ExtraArgs=extra_args or {})
            self.log.info("Copied s3://%s/%s -> s3://%s/%s", src_bucket, src_key, dest_bucket, dest_key)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"copy_object({src_bucket}/{src_key} -> {dest_bucket}/{dest_key})")
            raise

    def move_object(self, src_bucket: str, src_key: str, dest_bucket: str, dest_key: str) -> None:
        """Copy then delete."""
        self.copy_object(src_bucket, src_key, dest_bucket, dest_key)
        self.delete_object(src_bucket, src_key)

    # ----------------------- READ / DOWNLOAD -----------------------

    def download_file(self, bucket: str, key: str, file_path: str) -> None:
        """Download s3://bucket/key -> local file path"""
        try:
            self._client.download_file(Bucket=bucket, Key=key, Filename=file_path, Config=self._transfer_cfg)
            self.log.info("Downloaded s3://%s/%s -> %s", bucket, key, file_path)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"download_file({bucket}, {key})")
            raise

    def download_to_fileobj(self, bucket: str, key: str, fileobj: io.BufferedIOBase) -> None:
        """Download object to an open file-like object."""
        try:
            self._client.download_fileobj(Bucket=bucket, Key=key, Fileobj=fileobj, Config=self._transfer_cfg)
            self.log.info("Downloaded s3://%s/%s -> fileobj", bucket, key)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"download_to_fileobj({bucket}, {key})")
            raise

    def download_as_bytes(self, bucket: str, key: str) -> bytes:
        """Download full object content as bytes (non-streaming)."""
        try:
            resp = self._client.get_object(Bucket=bucket, Key=key)
            data = resp["Body"].read()
            self.log.info("Downloaded %d bytes from s3://%s/%s", len(data), bucket, key)
            return data
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"download_as_bytes({bucket}, {key})")
            raise

    def get_json(self, bucket: str, key: str) -> Any:
        """Convenience: read JSON from s3://bucket/key"""
        data = self.download_as_bytes(bucket, key)
        return json.loads(data.decode("utf-8"))

    # ----------------------- DELETE -----------------------

    def delete_object(self, bucket: str, key: str) -> None:
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
            self.log.info("Deleted s3://%s/%s", bucket, key)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"delete_object({bucket}, {key})")
            raise

    def delete_prefix(self, bucket: str, prefix: str, *, batch_size: int = 1000) -> int:
        """
        Delete up to all objects under a prefix in batches.
        Returns number of objects deleted.
        """
        deleted = 0
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                contents = page.get("Contents") or []
                if not contents:
                    continue
                for i in range(0, len(contents), batch_size):
                    obj_batch = [{"Key": o["Key"]} for o in contents[i : i + batch_size]]
                    resp = self._client.delete_objects(Bucket=bucket, Delete={"Objects": obj_batch})
                    deleted += len(resp.get("Deleted") or [])
            self.log.info("Deleted %d objects under s3://%s/%s", deleted, bucket, prefix)
            return deleted
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"delete_prefix({bucket}, {prefix})")
            raise

    # ----------------------- LIST / META -----------------------

    def list_objects(
        self,
        bucket: str,
        *,
        prefix: str = "",
        max_keys: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List objects under prefix. Returns dicts with at least Key, Size, LastModified, ETag.
        """
        out: List[Dict[str, Any]] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            count = 0
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    out.append(obj)
                    count += 1
                    if max_keys is not None and count >= max_keys:
                        self.log.info("Listed %d objects (truncated by max_keys)", count)
                        return out
            self.log.info("Listed %d objects from s3://%s/%s", len(out), bucket, prefix)
            return out
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"list_objects({bucket}, prefix={prefix})")
            raise

    def iter_objects(self, bucket: str, *, prefix: str = "") -> Generator[Dict[str, Any], None, None]:
        """Generator over objects under prefix."""
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    yield obj
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"iter_objects({bucket}, prefix={prefix})")
            raise

    def head_object(self, bucket: str, key: str) -> Dict[str, Any]:
        """Return metadata without downloading the object body."""
        try:
            meta = self._client.head_object(Bucket=bucket, Key=key)
            return meta
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"head_object({bucket}, {key})")
            raise

    def exists(self, bucket: str, key: str) -> bool:
        """Check if s3://bucket/key exists."""
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NotFound", "NoSuchKey"):
                return False
            self._handle_err(e, f"exists({bucket}, {key})")
            raise
        except BotoCoreError as e:
            self._handle_err(e, f"exists({bucket}, {key})")
            raise

    # ----------------------- BUCKET / URL UTILS -----------------------

    def bucket_exists(self, bucket: str) -> bool:
        try:
            self._client.head_bucket(Bucket=bucket)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchBucket"):
                return False
            self._handle_err(e, f"bucket_exists({bucket})")
            raise

    def create_bucket(self, bucket: str) -> None:
        """Create bucket in configured region (if allowed)."""
        try:
            if self.bucket_exists(bucket):
                return
            location = {"LocationConstraint": self._client.meta.region_name}
            # us-east-1 does not accept LocationConstraint
            if (self._client.meta.region_name or "").lower() == "us-east-1":
                self._client.create_bucket(Bucket=bucket)
            else:
                self._client.create_bucket(Bucket=bucket, CreateBucketConfiguration=location)
            self.log.info("Created bucket: %s", bucket)
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"create_bucket({bucket})")
            raise

    def presigned_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_in: int = 3600,
        method: str = "get_object",
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> str:
      
        try:
            params = {"Bucket": bucket, "Key": key}
            if extra_params:
                params.update(extra_params)
            url = self._client.generate_presigned_url(
                ClientMethod=method,
                Params=params,
                ExpiresIn=expires_in,
            )
            return url
        except (ClientError, BotoCoreError) as e:
            self._handle_err(e, f"presigned_url({bucket}, {key}, {method})")
            raise

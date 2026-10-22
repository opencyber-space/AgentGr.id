import logging
from typing import Any, Dict, Iterable, List, Optional
import boto3
from botocore.config import Config

from .utils import BaseIngestor, VectorRow, stable_id

logger = logging.getLogger("S3Ingestor")

class S3Ingestor(BaseIngestor):
    

    def __init__(
        self,
        *,
        sink,
        model,
        collection: str,
        bucket: str,
        prefix: str = "",
        s3_client=None,
        region_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(sink=sink, model=model, collection=collection, **kwargs)
        self.bucket = bucket
        self.prefix = prefix or ""
        if s3_client is None:
            self.s3 = boto3.client("s3", region_name=region_name, config=Config(retries={"max_attempts": 3}))
        else:
            self.s3 = s3_client

    def run(self, *, max_files: Optional[int] = None) -> Dict[str, int]:
        seen = 0
        upserted = 0

        paginator = self.s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)

        for page in pages:
            contents = page.get("Contents") or []
            for obj in contents:
                key = obj["Key"]
                if key.endswith("/") or key.strip() == "":
                    continue
                try:
                    seen += 1
                    if max_files is not None and seen > max_files:
                        return {"seen": seen, "upserted": upserted}

                    # fetch object
                    head = self.s3.head_object(Bucket=self.bucket, Key=key)
                    ct = head.get("ContentType")
                    b = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

                    # parse
                    text, meta_p = self.parser.parse(data=b, key=key, content_type=ct)
                    if not text.strip():
                        logger.info(f"Empty text after parse: s3://{self.bucket}/{key}")
                        continue

                    # chunk
                    rows: List[VectorRow] = []
                    for offset, chunk_text in self.chunker.chunk(text):
                        vid = stable_id(self.bucket, key, str(offset))
                        md = {
                            "source": "s3",
                            "s3_bucket": self.bucket,
                            "s3_key": key,
                            "offset": offset,
                            **meta_p,
                        }
                        md = self.metadata_builder(md)
                        rows.append(VectorRow(id=vid, values=[], metadata={**md, "__text__": chunk_text}))

                    if not rows:
                        continue

                    self._embed_and_upsert(rows)
                    upserted += len(rows)
                except Exception as e:
                    logger.exception(f"Failed ingest s3://{self.bucket}/{key}: {e}")

        return {"seen": seen, "upserted": upserted}

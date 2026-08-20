import hashlib
import io
import os
from pathlib import Path

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None

from .config import settings


class ObjectStorage:
    def __init__(self):
        self.client = boto3.client("s3", endpoint_url=settings.rustfs_endpoint, aws_access_key_id=settings.rustfs_access_key, aws_secret_access_key=settings.rustfs_secret_key, region_name="us-east-1") if boto3 else None

    def ensure_bucket(self):
        if not self.client:
            return
        try:
            self.client.head_bucket(Bucket=settings.rustfs_bucket)
        except Exception:
            self.client.create_bucket(Bucket=settings.rustfs_bucket)

    def put(self, key: str, content: bytes, content_type: str):
        if not self.client:
            raise RuntimeError("boto3 is required for RustFS storage")
        self.ensure_bucket()
        self.client.put_object(Bucket=settings.rustfs_bucket, Key=key, Body=io.BytesIO(content), ContentType=content_type)

    def url(self, key: str) -> str:
        return f"{settings.rustfs_endpoint}/{settings.rustfs_bucket}/{key}"


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


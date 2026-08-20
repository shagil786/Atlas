import os

import pytest


@pytest.mark.integration
def test_rustfs_integration_when_available():
    """Run automatically when the configured RustFS endpoint is available."""
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    endpoint = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000")
    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=os.getenv("RUSTFS_ACCESS_KEY", "atlas"), aws_secret_access_key=os.getenv("RUSTFS_SECRET_KEY", "atlas-secret"), region_name="us-east-1", config=Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 1}))
    bucket = os.getenv("RUSTFS_BUCKET", "atlas-documents")
    try:
        client.head_bucket(Bucket=bucket)
    except (BotoCoreError, ClientError):
        try:
            client.create_bucket(Bucket=bucket)
        except (BotoCoreError, ClientError):
            pytest.skip(f"RustFS is not available at {endpoint}")
    client.put_object(Bucket=bucket, Key="integration/check.txt", Body=b"atlas")
    assert client.get_object(Bucket=bucket, Key="integration/check.txt")["Body"].read() == b"atlas"

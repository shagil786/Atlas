from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "data/atlas.db")
    session_secret: str = os.getenv("SESSION_SECRET", "local-demo-secret")
    rustfs_endpoint: str = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000")
    rustfs_access_key: str = os.getenv("RUSTFS_ACCESS_KEY", "atlas")
    rustfs_secret_key: str = os.getenv("RUSTFS_SECRET_KEY", "atlas-secret")
    rustfs_bucket: str = os.getenv("RUSTFS_BUCKET", "atlas-documents")


settings = Settings()


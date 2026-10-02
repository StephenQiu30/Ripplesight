"""The existing Evidence bucket stores and serves bounded, lifecycle-owned media objects."""

from __future__ import annotations

import io

from minio import Minio
from urllib3 import PoolManager
from urllib3.util import Timeout

from core.config import Settings
from evidence.schemas import CleanupTargetKind, CleanupTargetSpec


class MinioMediaObjectStorage:
    def __init__(self, client: Minio, bucket: str, *, pool: PoolManager | None = None) -> None:
        self.client, self.bucket, self.pool = client, bucket, pool

    def close(self) -> None:
        if self.pool is not None:
            self.pool.clear()

    @staticmethod
    def _name(name: str) -> str:
        CleanupTargetSpec(kind=CleanupTargetKind.MINIO_OBJECT, reference=name)
        if not name.startswith("media/"):
            raise ValueError("media objects require their Evidence namespace")
        return name

    def check_bucket(self) -> None:
        if self.client.get_bucket_versioning(self.bucket).status in {"Enabled", "Suspended"}:
            raise ValueError("versioned media buckets need version-aware cleanup")

    def put(self, name: str, body: bytes, mime_type: str) -> None:
        if not 1 <= len(body) <= 128 * 1024 * 1024:
            raise ValueError("media object size limit")
        # A bounded body and an explicit part size keep this one object write to one PUT.
        self.client.put_object(
            self.bucket,
            self._name(name),
            io.BytesIO(body),
            len(body),
            content_type=mime_type,
            part_size=128 * 1024 * 1024,
        )

    def get(self, name: str, *, max_bytes: int) -> bytes:
        if not 1 <= max_bytes <= 128 * 1024 * 1024:
            raise ValueError("media read size limit")
        response = self.client.get_object(self.bucket, self._name(name))
        try:
            result = bytearray()
            for chunk in response.stream(64 * 1024):
                if len(result) + len(chunk) > max_bytes:
                    raise ValueError("stored media exceeds frozen size")
                result.extend(chunk)
            return bytes(result)
        finally:
            response.close()
            response.release_conn()


def create_media_storage(settings: Settings) -> MinioMediaObjectStorage | None:
    """Construct only; never check/create a bucket or make HTTP requests on startup."""
    if (
        not settings.minio_endpoint
        or not settings.minio_access_key
        or not settings.minio_secret_key
        or not settings.minio_bucket
    ):
        return None
    pool = PoolManager(timeout=Timeout(connect=20, read=20), retries=False)
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        region="us-east-1",
        http_client=pool,
    )
    return MinioMediaObjectStorage(client, settings.minio_bucket, pool=pool)

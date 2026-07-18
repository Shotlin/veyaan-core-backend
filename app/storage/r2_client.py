"""Cloudflare R2 object storage adapter — GAP-P1-12.

In Project 1 this adapter provides:
  - Temporary screenshot upload
  - Encrypted backup artifact storage
  - Expiring presigned download URLs

It is safe to leave R2 credentials unconfigured — the client detects
missing settings and disables itself gracefully (no runtime crash).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class R2Client:
    """
    Adapter for Cloudflare R2 (S3-compatible).

    Configuration is read from app settings. If R2 credentials are not
    set, all methods no-op and log a warning.
    """

    def __init__(self):
        self._client = None
        self._bucket: Optional[str] = None
        self._enabled = False

    def _ensure_client(self) -> bool:
        """Lazy-init the boto3 S3 client on first use."""
        if self._client is not None:
            return self._enabled

        try:
            from app.config import settings

            if not all(
                [
                    getattr(settings, "R2_ACCESS_KEY_ID", None),
                    getattr(settings, "R2_SECRET_ACCESS_KEY", None),
                    getattr(settings, "R2_ENDPOINT_URL", None),
                    getattr(settings, "R2_BUCKET_NAME", None),
                ]
            ):
                logger.info("R2 storage disabled — credentials not configured")
                self._enabled = False
                return False

            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.R2_ENDPOINT_URL,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
            self._bucket = settings.R2_BUCKET_NAME
            self._enabled = True
            logger.info("R2 storage client initialized", bucket=self._bucket)
        except Exception as e:
            logger.warning("R2 storage init failed", error=str(e))
            self._enabled = False

        return self._enabled

    def upload_file(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> bool:
        """Upload bytes to R2. Returns True on success, False if R2 is disabled/failed."""
        if not self._ensure_client():
            return False
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.info("r2_upload_success", key=key, size=len(data))
            return True
        except Exception as e:
            logger.error("r2_upload_failed", key=key, error=str(e))
            return False

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned download URL. Returns None if R2 is disabled/failed."""
        if not self._ensure_client():
            return None
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error("r2_presign_failed", key=key, error=str(e))
            return None

    def delete_file(self, key: str) -> bool:
        """Delete an object from R2. Returns True on success."""
        if not self._ensure_client():
            return False
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            logger.info("r2_delete_success", key=key)
            return True
        except Exception as e:
            logger.error("r2_delete_failed", key=key, error=str(e))
            return False

    @property
    def is_enabled(self) -> bool:
        return self._ensure_client()


# Module-level singleton
r2_client = R2Client()

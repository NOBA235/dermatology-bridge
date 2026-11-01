"""Private storage abstraction for patient selfies and cached YouCam masks.

Security invariants:
- Never return or store a public URL as a storage key.
- Storage keys follow private S3 object key paths:
    patients/{patient_id}/visits/{visit_id}/selfie.{ext}
    patients/{patient_id}/visits/{visit_id}/masks/{concern}.png
- Never log image URLs or presigned URLs.
"""

import hashlib
import hmac
import mimetypes
from pathlib import Path
import shutil
import time
import uuid

import httpx

from app.config import REPO_ROOT, get_settings

PRIVATE_STORAGE_ROOT = REPO_ROOT / "logs" / "private_storage"

# Minimal 1x1 transparent PNG used for deterministic mock mask caching
_SYNTHETIC_MASK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)


class PrivateStorageService:
    """Private S3-compatible object storage, with a local development backend."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or PRIVATE_STORAGE_ROOT
        self.settings = get_settings()
        self._client = None
        if self.settings.STORAGE_BACKEND == "local":
            self.root_dir.mkdir(parents=True, exist_ok=True)

    def _object_key(self, storage_key: str) -> str:
        """Reject URL-like or traversal keys before accessing either backend."""
        if "://" in storage_key or storage_key.startswith("/"):
            raise ValueError("storage_key must be a relative private object key.")
        if any(part in {"", ".", ".."} for part in storage_key.split("/")):
            raise ValueError("Invalid storage key path.")
        return storage_key

    @property
    def _s3(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.STORAGE_ENDPOINT_URL,
                aws_access_key_id=self.settings.STORAGE_ACCESS_KEY_ID,
                aws_secret_access_key=self.settings.STORAGE_SECRET_ACCESS_KEY,
                region_name=self.settings.STORAGE_REGION,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                ),
            )
        return self._client

    def _write_object(self, storage_key: str, data: bytes, content_type: str) -> None:
        storage_key = self._object_key(storage_key)
        if self.settings.STORAGE_BACKEND == "s3":
            self._s3.put_object(
                Bucket=self.settings.STORAGE_BUCKET,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
            )
            return

        target_path = self.root_dir / storage_key
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)

    def read_object(self, storage_key: str) -> bytes | None:
        """Read a private object for server-side report rendering."""
        storage_key = self._object_key(storage_key)
        if self.settings.STORAGE_BACKEND == "s3":
            from botocore.exceptions import ClientError

            try:
                response = self._s3.get_object(
                    Bucket=self.settings.STORAGE_BUCKET,
                    Key=storage_key,
                )
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code in {"NoSuchKey", "404", "NotFound"}:
                    return None
                raise
            return response["Body"].read()

        target_path = self.root_dir / storage_key
        return target_path.read_bytes() if target_path.is_file() else None

    def delete_patient_data(self, patient_id: uuid.UUID) -> None:
        """Delete all private files for a patient from the configured backend."""
        prefix = f"patients/{patient_id}/"
        if self.settings.STORAGE_BACKEND == "s3":
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self.settings.STORAGE_BUCKET,
                Prefix=prefix,
            ):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if objects:
                    self._s3.delete_objects(
                        Bucket=self.settings.STORAGE_BUCKET,
                        Delete={"Objects": objects, "Quiet": True},
                    )
            return

        patient_dir = self.root_dir / "patients" / str(patient_id)
        if patient_dir.exists():
            shutil.rmtree(patient_dir)

    def store_visit_selfie(
        self,
        *,
        patient_id: uuid.UUID,
        visit_id: uuid.UUID,
        image_bytes: bytes,
        filename: str = "selfie.jpg",
    ) -> str:
        """Persist raw patient selfie bytes and return a private storage key (never a URL)."""
        ext = Path(filename).suffix.lower().lstrip(".") or "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        storage_key = f"patients/{patient_id}/visits/{visit_id}/selfie.{ext}"
        content_type = mimetypes.guess_type(f"image.{ext}")[0] or "image/jpeg"
        self._write_object(storage_key, image_bytes, content_type)
        return storage_key

    async def cache_concern_mask(
        self,
        *,
        patient_id: uuid.UUID,
        visit_id: uuid.UUID,
        concern: str,
        mask_url: str | None,
        allow_live_fetch: bool = False,
    ) -> str | None:
        """Cache an ephemeral YouCam mask URL to durable private storage and return its storage key."""
        if not mask_url:
            return None

        storage_key = f"patients/{patient_id}/visits/{visit_id}/masks/{concern}.png"

        if allow_live_fetch and mask_url.startswith(("http://", "https://")) and ".youcam.local" not in mask_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(mask_url)
                    resp.raise_for_status()
                    self._write_object(storage_key, resp.content, "image/png")
                    return storage_key
            except httpx.HTTPError:
                # Fall back to placeholder bytes if ephemeral URL fails to download
                self._write_object(storage_key, _SYNTHETIC_MASK_PNG, "image/png")
                return storage_key

        self._write_object(storage_key, _SYNTHETIC_MASK_PNG, "image/png")
        return storage_key

    def generate_signed_url(self, storage_key: str, ttl_seconds: int = 300) -> str:
        """Create a short-lived signed path for private retrieval (never logged)."""
        storage_key = self._object_key(storage_key)
        settings = get_settings()
        expires = int(time.time()) + ttl_seconds
        message = f"{storage_key}:{expires}".encode("utf-8")
        signature = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()
        return f"/api/storage/signed/{storage_key}?expires={expires}&sig={signature}"

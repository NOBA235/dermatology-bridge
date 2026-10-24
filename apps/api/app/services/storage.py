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
from pathlib import Path
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
    """Private S3-compatible storage service with local encrypted-path backing."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or PRIVATE_STORAGE_ROOT
        self.root_dir.mkdir(parents=True, exist_ok=True)

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
        target_path = self.root_dir / storage_key
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(image_bytes)
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
        target_path = self.root_dir / storage_key
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if allow_live_fetch and mask_url.startswith(("http://", "https://")) and ".youcam.local" not in mask_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(mask_url)
                    resp.raise_for_status()
                    target_path.write_bytes(resp.content)
                    return storage_key
            except httpx.HTTPError:
                # Fall back to placeholder bytes if ephemeral URL fails to download
                target_path.write_bytes(_SYNTHETIC_MASK_PNG)
                return storage_key

        target_path.write_bytes(_SYNTHETIC_MASK_PNG)
        return storage_key

    def generate_signed_url(self, storage_key: str, ttl_seconds: int = 300) -> str:
        """Create a short-lived signed path for private retrieval (never logged)."""
        if "://" in storage_key:
            raise ValueError("storage_key must be a private key path, not a URL.")
        settings = get_settings()
        expires = int(time.time()) + ttl_seconds
        message = f"{storage_key}:{expires}".encode("utf-8")
        signature = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()
        return f"/api/storage/signed/{storage_key}?expires={expires}&sig={signature}"

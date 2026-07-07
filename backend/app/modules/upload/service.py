from __future__ import annotations

import io
from pathlib import Path

import structlog
from PIL import Image

from app.models.document import Document, DocumentStatus
from app.providers.repository import DocumentRepository
from app.providers.storage.base import StorageProvider

logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}


class UploadService:
    def __init__(
        self,
        storage: StorageProvider,
        repository: DocumentRepository,
        max_size_mb: int,
        allowed_mime_types: list[str],
    ) -> None:
        self._storage = storage
        self._repository = repository
        self._max_size = max_size_mb * 1024 * 1024
        self._allowed_mime = set(allowed_mime_types)

    def validate(self, filename: str, content_type: str | None, size: int) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Allowed: PDF, PNG, JPG, JPEG, TIFF")
        if content_type and content_type not in self._allowed_mime:
            raise ValueError(f"Unsupported MIME type: {content_type}")
        if size > self._max_size:
            raise ValueError(f"File exceeds maximum size of {self._max_size // (1024 * 1024)} MB")

    async def upload(self, filename: str, content: bytes, content_type: str | None) -> Document:
        self.validate(filename, content_type, len(content))
        document = Document(
            name=filename,
            status=DocumentStatus.UPLOADED,
            file_size=len(content),
            mime_type=content_type or "application/octet-stream",
        )
        path = await self._storage.save_upload(document.id, filename, content)
        document.file_path = str(path.relative_to(self._storage.root))
        await self._repository.save(document)
        logger.info("document_uploaded", document_id=document.id, filename=filename, size=len(content))
        return document

    async def generate_placeholder_thumbnail(self, document_id: str, page_number: int = 1) -> str:
        img = Image.new("RGB", (200, 280), color=(245, 245, 245))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        path = await self._storage.save_thumbnail(document_id, page_number, buf.getvalue())
        return str(path.relative_to(self._storage.root))

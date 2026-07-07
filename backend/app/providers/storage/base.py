from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.document import Document


class StorageProvider(ABC):
    @abstractmethod
    async def ensure_directories(self) -> None: ...

    @abstractmethod
    async def save_upload(self, document_id: str, filename: str, content: bytes) -> Path: ...

    @abstractmethod
    async def save_document_model(self, document: Document) -> Path: ...

    @abstractmethod
    async def load_document_model(self, document_id: str) -> Document | None: ...

    @abstractmethod
    async def list_documents(self) -> list[str]: ...

    @abstractmethod
    async def delete_document(self, document_id: str) -> bool: ...

    @abstractmethod
    async def save_thumbnail(self, document_id: str, page_number: int, content: bytes) -> Path: ...

    @abstractmethod
    async def save_asset(self, document_id: str, asset_name: str, content: bytes) -> Path: ...

    @abstractmethod
    async def save_output(self, document_id: str, filename: str, content: bytes) -> Path: ...

    @abstractmethod
    async def get_upload_path(self, document_id: str) -> Path | None: ...

    @abstractmethod
    async def is_writable(self) -> bool: ...

    @abstractmethod
    def resolve_path(self, relative: str) -> Path: ...

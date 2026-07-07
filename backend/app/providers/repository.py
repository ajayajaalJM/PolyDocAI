from __future__ import annotations

import json
from pathlib import Path

import aiofiles

from app.models.document import Document, TranslatorSettings
from app.providers.storage.base import StorageProvider


class DocumentRepository:
    def __init__(self, storage: StorageProvider) -> None:
        self._storage = storage

    async def save(self, document: Document) -> Document:
        document.touch()
        await self._storage.save_document_model(document)
        return document

    async def get(self, document_id: str) -> Document | None:
        return await self._storage.load_document_model(document_id)

    async def get_or_raise(self, document_id: str) -> Document:
        document = await self.get(document_id)
        if document is None:
            raise KeyError(f"Document {document_id} not found")
        return document

    async def list_all(self) -> list[Document]:
        ids = await self._storage.list_documents()
        documents: list[Document] = []
        for doc_id in ids:
            doc = await self.get(doc_id)
            if doc:
                documents.append(doc)
        return sorted(documents, key=lambda d: d.updated_at, reverse=True)

    async def delete(self, document_id: str) -> bool:
        return await self._storage.delete_document(document_id)


class SettingsRepository:
    def __init__(self, storage: StorageProvider) -> None:
        self._path = Path(storage.root) / "settings.json"

    async def load(self, defaults: TranslatorSettings) -> TranslatorSettings:
        if not self._path.exists():
            return defaults
        async with aiofiles.open(self._path, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return TranslatorSettings.model_validate(data)

    async def save(self, settings: TranslatorSettings) -> TranslatorSettings:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(settings.model_dump_json(indent=2))
        return settings

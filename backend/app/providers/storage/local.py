from __future__ import annotations

import json
from pathlib import Path

import aiofiles

from app.models.document import Document
from app.providers.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.uploads = self.root / "uploads"
        self.documents = self.root / "documents"
        self.outputs = self.root / "outputs"
        self.models = self.root / "models"

    async def ensure_directories(self) -> None:
        for directory in (self.uploads, self.documents, self.outputs, self.models):
            directory.mkdir(parents=True, exist_ok=True)

    def _doc_dir(self, document_id: str) -> Path:
        return self.uploads / document_id

    async def save_upload(self, document_id: str, filename: str, content: bytes) -> Path:
        doc_dir = self._doc_dir(document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / filename
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def save_document_model(self, document: Document) -> Path:
        path = self.documents / f"{document.id}.json"
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(document.model_dump_json(indent=2))
        return path

    async def load_document_model(self, document_id: str) -> Document | None:
        path = self.documents / f"{document_id}.json"
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return Document.model_validate(data)

    async def list_documents(self) -> list[str]:
        if not self.documents.exists():
            return []
        return [p.stem for p in self.documents.glob("*.json")]

    async def delete_document(self, document_id: str) -> bool:
        model_path = self.documents / f"{document_id}.json"
        doc_dir = self._doc_dir(document_id)
        deleted = False
        if model_path.exists():
            model_path.unlink()
            deleted = True
        if doc_dir.exists():
            for item in doc_dir.rglob("*"):
                if item.is_file():
                    item.unlink()
            for item in sorted(doc_dir.rglob("*"), reverse=True):
                if item.is_dir():
                    item.rmdir()
            doc_dir.rmdir()
            deleted = True
        return deleted

    async def save_thumbnail(self, document_id: str, page_number: int, content: bytes) -> Path:
        thumb_dir = self._doc_dir(document_id) / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        path = thumb_dir / f"page_{page_number:04d}.png"
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def save_translated_raster(
        self, document_id: str, page_number: int, content: bytes
    ) -> Path:
        out_dir = self._doc_dir(document_id) / "translated"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"page_{page_number:04d}.png"
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def save_stripped_raster(
        self, document_id: str, page_number: int, content: bytes
    ) -> Path:
        out_dir = self._doc_dir(document_id) / "stripped"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"page_{page_number:04d}.png"
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def save_asset(self, document_id: str, asset_name: str, content: bytes) -> Path:
        assets_dir = self._doc_dir(document_id) / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        path = assets_dir / asset_name
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def save_output(self, document_id: str, filename: str, content: bytes) -> Path:
        out_dir = self.outputs / document_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def get_upload_path(self, document_id: str) -> Path | None:
        doc_dir = self._doc_dir(document_id)
        if not doc_dir.exists():
            return None
        files = [p for p in doc_dir.iterdir() if p.is_file()]
        return files[0] if files else None

    async def is_writable(self) -> bool:
        try:
            await self.ensure_directories()
            test = self.root / ".write_test"
            test.write_text("ok")
            test.unlink()
            return True
        except OSError:
            return False

    def resolve_path(self, relative: str) -> Path:
        return (self.root / relative).resolve()

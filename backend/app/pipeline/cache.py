"""Content-hash cache for expensive pipeline stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PipelineCache:
    def __init__(self, root: Path) -> None:
        self._root = root / "cache" / "pipeline"
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_path(self, document_id: str, page_number: int, stage: str, content_hash: str) -> Path:
        return self._root / document_id / f"page_{page_number:04d}" / stage / f"{content_hash}.json"

    @staticmethod
    def hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def get(self, document_id: str, page_number: int, stage: str, content_hash: str) -> dict[str, Any] | None:
        path = self._key_path(document_id, page_number, stage, content_hash)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.debug("pipeline_cache_hit", stage=stage, page=page_number)
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def put(
        self,
        document_id: str,
        page_number: int,
        stage: str,
        content_hash: str,
        payload: dict[str, Any],
    ) -> None:
        path = self._key_path(document_id, page_number, stage, content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

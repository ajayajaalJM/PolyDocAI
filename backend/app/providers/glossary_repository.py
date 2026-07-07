from __future__ import annotations

import json
from pathlib import Path

from app.providers.translators.base import Glossary


class GlossaryRepository:
    def __init__(self, storage_root: Path | str) -> None:
        self._path = Path(storage_root) / "glossary.json"

    async def load(self) -> Glossary:
        if not self._path.exists():
            return Glossary()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return Glossary({str(k): str(v) for k, v in data.items()})
        except (json.JSONDecodeError, OSError):
            pass
        return Glossary()

    async def save(self, glossary: Glossary) -> Glossary:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(glossary.entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return glossary

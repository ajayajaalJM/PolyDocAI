from __future__ import annotations

from functools import lru_cache

from app.core.device import detect_device, paddle_device
from app.core.settings import Settings
from app.modules.export.service import ExportService
from app.modules.layout.doclayout_service import DocLayoutService
from app.modules.ocr.paddle_service import PaddleOCRService
from app.modules.ocr.structure_service import PPStructureService
from app.modules.pipeline.model_builder import DocumentModelBuilder
from app.modules.pipeline.orchestrator import PipelineOrchestrator
from app.modules.reconstruction.engine import ReconstructionEngine
from app.modules.translation.service import TranslationService
from app.modules.upload.service import UploadService
from app.models.document import TranslatorSettings
from app.providers.fonts.manager import FontManager
from app.providers.glossary_repository import GlossaryRepository
from app.providers.repository import DocumentRepository, SettingsRepository
from app.providers.storage.local import LocalStorageProvider


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = LocalStorageProvider(settings.storage_root)
        self.document_repository = DocumentRepository(self.storage)
        self.settings_repository = SettingsRepository(self.storage)
        self.translator_settings = TranslatorSettings(
            provider=settings.default_translator,  # type: ignore[arg-type]
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.default_ollama_model,
            openai_compatible_base_url=settings.openai_compatible_base_url,
            openai_compatible_model=settings.default_openai_model,
            source_language=settings.source_language,
            target_language=settings.target_language,
        )
        self.font_manager = FontManager()
        self.glossary_repository = GlossaryRepository(settings.storage_root)
        self.ocr = PaddleOCRService(lang=settings.ocr_lang, use_gpu=paddle_device() == "gpu")
        self.structure = PPStructureService(lang=settings.ocr_lang, use_gpu=paddle_device() == "gpu")
        self.layout = DocLayoutService(
            device=detect_device(),
            confidence=settings.layout_confidence,
            imgsz=settings.layout_imgsz,
        )
        self.model_builder = DocumentModelBuilder()
        self.translation = TranslationService(self.translator_settings)
        self.reconstruction = ReconstructionEngine(self.font_manager)
        self.export = ExportService(self.reconstruction, self.storage.root)
        self.upload = UploadService(
            self.storage,
            self.document_repository,
            settings.max_upload_size_mb,
            settings.allowed_mime_types,
        )
        self.pipeline = PipelineOrchestrator(
            self.storage,
            self.document_repository,
            self.ocr,
            self.layout,
            self.structure,
            self.translation,
            self.reconstruction,
            ocr_dpi=settings.ocr_dpi,
        )

    async def initialize(self) -> None:
        await self.storage.ensure_directories()
        self.translator_settings = await self.settings_repository.load(self.translator_settings)
        glossary = await self.glossary_repository.load()
        self.translation.update_settings(self.translator_settings)
        self.translation.update_glossary(glossary)
        self.ocr.initialize()
        self.layout.initialize()
        self.structure.initialize()

    async def shutdown(self) -> None:
        pass

    async def reload_settings(self) -> TranslatorSettings:
        self.translator_settings = await self.settings_repository.load(self.translator_settings)
        glossary = await self.glossary_repository.load()
        self.translation.update_settings(self.translator_settings)
        self.translation.update_glossary(glossary)
        return self.translator_settings

    async def save_settings(self, settings: TranslatorSettings) -> TranslatorSettings:
        saved = await self.settings_repository.save(settings)
        glossary = await self.glossary_repository.load()
        self.translator_settings = saved
        self.translation.update_settings(saved)
        self.translation.update_glossary(glossary)
        return saved

    async def save_glossary(self, entries: dict[str, str]):
        from app.providers.translators.base import Glossary

        glossary = await self.glossary_repository.save(Glossary(entries))
        self.translation.update_glossary(glossary)
        return glossary.entries

    async def load_glossary(self) -> dict[str, str]:
        glossary = await self.glossary_repository.load()
        return glossary.entries


@lru_cache
def get_container() -> Container:
    from app.core.settings import get_settings

    return Container(get_settings())

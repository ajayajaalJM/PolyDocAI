from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_container_from_request
from app.core.container import Container
from app.models.document import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    container: Container = Depends(get_container_from_request),
) -> HealthResponse:
    storage_ok = await container.storage.is_writable()
    settings = container.translator_settings
    warnings: list[str] = []

    translation_ok, translation_msg, _ = await container.translation.test_connection()
    if not translation_ok:
        warnings.append(translation_msg)

    ollama_ok = False
    openai_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            ollama_resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = ollama_resp.status_code == 200
    except httpx.HTTPError:
        pass
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            openai_resp = await client.get(
                f"{settings.openai_compatible_base_url}/models",
                headers={"Authorization": f"Bearer {settings.openai_compatible_api_key}"},
            )
            openai_ok = openai_resp.status_code == 200
    except httpx.HTTPError:
        pass

    if settings.provider == "ollama" and not ollama_ok:
        warnings.append(f"Ollama not reachable at {settings.ollama_base_url}")
    if settings.provider == "openai_compatible" and not openai_ok:
        warnings.append(
            f"OpenAI-compatible server not reachable at {settings.openai_compatible_base_url}"
        )
    if not container.ocr.is_available:
        warnings.append("OCR (PaddleOCR) is not available")
    if not container.layout.is_available:
        warnings.append("Layout detection (DocLayout-YOLO) is not available — using fallback")

    status = "ok" if storage_ok and translation_ok else "degraded"
    if not storage_ok:
        status = "degraded"

    return HealthResponse(
        status=status,
        version="0.1.0",
        storage_writable=storage_ok,
        ocr_available=container.ocr.is_available,
        layout_available=container.layout.is_available,
        translation_available=translation_ok,
        translation_provider=settings.provider,
        ollama_available=ollama_ok,
        openai_compatible_available=openai_ok,
        warnings=warnings,
    )

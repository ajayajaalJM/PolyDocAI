from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_container_from_request
from app.core.container import Container
from app.models.document import ConnectionTestResponse, SettingsResponse, TranslatorSettings

router = APIRouter(prefix="/settings", tags=["settings"])


class GlossaryBody(BaseModel):
    entries: dict[str, str]


@router.get("", response_model=SettingsResponse)
async def get_settings(
    container: Container = Depends(get_container_from_request),
) -> SettingsResponse:
    settings = await container.reload_settings()
    return SettingsResponse(translator=settings)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: TranslatorSettings,
    container: Container = Depends(get_container_from_request),
) -> SettingsResponse:
    saved = await container.save_settings(body)
    return SettingsResponse(translator=saved)


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    provider: str | None = None,
    container: Container = Depends(get_container_from_request),
) -> ConnectionTestResponse:
    available, message, models = await container.translation.test_connection(provider)
    return ConnectionTestResponse(
        provider=provider or container.translator_settings.provider,
        available=available,
        message=message,
        models=models,
    )


@router.get("/glossary")
async def get_glossary(
    container: Container = Depends(get_container_from_request),
) -> dict[str, str]:
    return await container.load_glossary()


@router.put("/glossary")
async def save_glossary(
    body: GlossaryBody,
    container: Container = Depends(get_container_from_request),
) -> dict[str, str]:
    return await container.save_glossary(body.entries)

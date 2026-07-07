from fastapi import APIRouter

from app.api.v1 import documents, health, settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(settings.router)

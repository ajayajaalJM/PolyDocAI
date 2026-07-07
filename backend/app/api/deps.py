from __future__ import annotations

from fastapi import Request

from app.core.container import Container


def get_container_from_request(request: Request) -> Container:
    return request.app.state.container

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.container import Container
from app.core.settings import Settings
from app.main import app


@pytest.fixture
async def client(tmp_path):
    settings = Settings(storage_root=str(tmp_path / "storage"))
    container = Container(settings)
    await container.initialize()
    app.state.container = container
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await container.shutdown()

import pytest
from httpx import AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_healthz_integration():
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_users_integration():
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/users/")
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        assert len(users) >= 2

        resp_one = await ac.get("/users/1")
        assert resp_one.status_code == 200
        assert resp_one.json()["id"] == 1

        resp_missing = await ac.get("/users/9999")
        assert resp_missing.status_code == 404


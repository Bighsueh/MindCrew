import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "teacher@test.com",
        "password": "password123",
        "display_name": "Teacher One",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["role"] == "teacher"
    assert data["user"]["can_create_project"] is True
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "dup@test.com",
        "password": "pass",
        "display_name": "Dup",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@test.com",
        "password": "pass",
        "display_name": "Dup",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "login@test.com",
        "password": "password123",
        "display_name": "Login User",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@test.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "wrong@test.com",
        "password": "correct",
        "display_name": "Wrong",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "wrong@test.com",
        "password": "incorrect",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(client: AsyncClient):
    reg = await client.post("/api/auth/register", json={
        "email": "me@test.com",
        "password": "pass",
        "display_name": "Me User",
    })
    token = reg.json()["access_token"]
    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"


@pytest.mark.asyncio
async def test_refresh(client: AsyncClient):
    reg = await client.post("/api/auth/register", json={
        "email": "refresh@test.com",
        "password": "pass",
        "display_name": "Refresh",
    })
    refresh_token = reg.json()["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_me_no_auth(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)

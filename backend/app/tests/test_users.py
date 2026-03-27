import pytest
from httpx import AsyncClient


async def _register_teacher(client: AsyncClient, email: str = "t@test.com") -> str:
    resp = await client.post("/api/auth/register", json={
        "email": email,
        "password": "pass",
        "display_name": "Teacher",
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_student(client: AsyncClient):
    token = await _register_teacher(client, "teacher_cs@test.com")
    resp = await client.post("/api/teacher/students", json={
        "email": "student1@test.com",
        "password": "studentpass",
        "display_name": "Student One",
        "can_create_project": False,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "student"
    assert resp.json()["can_create_project"] is False


@pytest.mark.asyncio
async def test_list_students(client: AsyncClient):
    token = await _register_teacher(client, "teacher_ls@test.com")
    await client.post("/api/teacher/students", json={
        "email": "ls_student@test.com",
        "password": "pass",
        "display_name": "LS Student",
    }, headers={"Authorization": f"Bearer {token}"})
    resp = await client.get("/api/teacher/students", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_permission(client: AsyncClient):
    token = await _register_teacher(client, "teacher_up@test.com")
    create_resp = await client.post("/api/teacher/students", json={
        "email": "up_student@test.com",
        "password": "pass",
        "display_name": "UP Student",
    }, headers={"Authorization": f"Bearer {token}"})
    student_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/api/teacher/students/{student_id}",
        json={"can_create_project": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["can_create_project"] is True


@pytest.mark.asyncio
async def test_student_cannot_create_students(client: AsyncClient):
    token = await _register_teacher(client, "teacher_sc@test.com")
    create_resp = await client.post("/api/teacher/students", json={
        "email": "sc_student@test.com",
        "password": "pass",
        "display_name": "SC Student",
    }, headers={"Authorization": f"Bearer {token}"})

    # Login as student
    login_resp = await client.post("/api/auth/login", json={
        "email": "sc_student@test.com",
        "password": "pass",
    })
    student_token = login_resp.json()["access_token"]

    resp = await client.post("/api/teacher/students", json={
        "email": "another@test.com",
        "password": "pass",
        "display_name": "Another",
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 403

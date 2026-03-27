import pytest
from httpx import AsyncClient


async def _register_teacher(client: AsyncClient, email: str) -> str:
    resp = await client.post("/api/auth/register", json={
        "email": email,
        "password": "pass",
        "display_name": "Teacher",
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    token = await _register_teacher(client, "proj_t@test.com")
    resp = await client.post("/api/projects", json={
        "name": "Test Project",
        "description": "A test project",
        "ai_contribution": "medium",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert len(data["seats"]) == 5
    assert all(s["occupant_type"] == "ai" for s in data["seats"])


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    token = await _register_teacher(client, "proj_list@test.com")
    await client.post("/api/projects", json={
        "name": "List Project",
    }, headers={"Authorization": f"Bearer {token}"})
    resp = await client.get("/api/projects", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient):
    token = await _register_teacher(client, "proj_get@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Get Project",
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]
    resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Project"
    assert len(resp.json()["seats"]) == 5


@pytest.mark.asyncio
async def test_join_and_leave(client: AsyncClient):
    token = await _register_teacher(client, "proj_jl@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Join Project",
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]

    # Join
    join_resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "crew_1",
    }, headers={"Authorization": f"Bearer {token}"})
    assert join_resp.status_code == 200
    assert join_resp.json()["seat"]["occupant_type"] == "human"

    # Verify seat changed
    get_resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    seats = get_resp.json()["seats"]
    crew1 = next(s for s in seats if s["seat_role"] == "crew_1")
    assert crew1["occupant_type"] == "human"

    # Leave
    leave_resp = await client.post(f"/api/projects/{project_id}/leave", headers={
        "Authorization": f"Bearer {token}",
    })
    assert leave_resp.status_code == 200

    # Verify seat reverted
    get_resp2 = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    seats2 = get_resp2.json()["seats"]
    crew1_after = next(s for s in seats2 if s["seat_role"] == "crew_1")
    assert crew1_after["occupant_type"] == "ai"


@pytest.mark.asyncio
async def test_join_occupied_seat(client: AsyncClient):
    token = await _register_teacher(client, "proj_occ@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Occupied Project",
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]

    # Join crew_1
    await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "crew_1",
    }, headers={"Authorization": f"Bearer {token}"})

    # Create another teacher and try to join same seat
    token2 = await _register_teacher(client, "proj_occ2@test.com")
    resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "crew_1",
    }, headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_student_no_permission_cannot_create(client: AsyncClient):
    teacher_token = await _register_teacher(client, "proj_noperm@test.com")
    await client.post("/api/teacher/students", json={
        "email": "noperm_s@test.com",
        "password": "pass",
        "display_name": "NoPerm Student",
        "can_create_project": False,
    }, headers={"Authorization": f"Bearer {teacher_token}"})

    login_resp = await client.post("/api/auth/login", json={
        "email": "noperm_s@test.com",
        "password": "pass",
    })
    student_token = login_resp.json()["access_token"]

    resp = await client.post("/api/projects", json={
        "name": "Should Fail",
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 403

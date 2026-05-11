import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_flow(client: AsyncClient):
    """Full integration: teacher register → create student → student login → create project → join seat."""

    # 1. Teacher registers
    reg_resp = await client.post("/api/auth/register", json={
        "email": "flow_teacher@test.com",
        "password": "teacherpass",
        "display_name": "Flow Teacher",
    })
    assert reg_resp.status_code == 201
    teacher_token = reg_resp.json()["access_token"]

    # 2. Teacher creates student with project permission
    student_resp = await client.post("/api/teacher/students", json={
        "email": "flow_student@test.com",
        "password": "studentpass",
        "display_name": "Flow Student",
        "can_create_project": True,
    }, headers={"Authorization": f"Bearer {teacher_token}"})
    assert student_resp.status_code == 201

    # 3. Student logs in
    login_resp = await client.post("/api/auth/login", json={
        "email": "flow_student@test.com",
        "password": "studentpass",
    })
    assert login_resp.status_code == 200
    student_token = login_resp.json()["access_token"]

    # 4. Student creates project
    proj_resp = await client.post("/api/projects", json={
        "name": "Flow Project",
        "description": "Full flow test",
        "ai_contribution": "high",
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]
    assert len(proj_resp.json()["seats"]) == 5

    # 5. Student joins a crew seat
    # Phase 18：supervisor 席位由 AI 鎖定，人類使用者僅能佔 crew_1..4。
    join_resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "crew_1",
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert join_resp.status_code == 200
    assert join_resp.json()["seat"]["occupant_type"] == "human"

    # 5b. Verify supervisor seat remains AI-locked (Phase 18 SOP)
    sup_join_resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "supervisor",
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert sup_join_resp.status_code == 403

    # 6. Verify project state
    get_resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {student_token}",
    })
    assert get_resp.status_code == 200
    seats = get_resp.json()["seats"]
    crew_1 = next(s for s in seats if s["seat_role"] == "crew_1")
    assert crew_1["occupant_type"] == "human"
    supervisor = next(s for s in seats if s["seat_role"] == "supervisor")
    assert supervisor["occupant_type"] == "ai"
    assert sum(1 for s in seats if s["occupant_type"] == "ai") == 4

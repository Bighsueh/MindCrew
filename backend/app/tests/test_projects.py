import pytest
from httpx import AsyncClient

from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG


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
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    # Phase 21：預設 ai_crew_count=3 → 3 crew + 1 supervisor = 4 seats
    assert len(data["seats"]) == 4
    assert all(s["occupant_type"] == "ai" for s in data["seats"])
    # Phase 21：建立時 AI 全部 dormant（is_active=False）
    assert all(s.get("is_active") is False for s in data["seats"])


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    token = await _register_teacher(client, "proj_list@test.com")
    await client.post("/api/projects", json={
        "name": "List Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
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
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]
    resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Project"
    # Phase 21：預設 ai_crew_count=3 → 4 seats
    assert len(resp.json()["seats"]) == 4


@pytest.mark.asyncio
async def test_join_and_leave(client: AsyncClient):
    token = await _register_teacher(client, "proj_jl@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Join Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
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
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
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
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_project_rejects_missing_personas(client: AsyncClient):
    """Spec §17.3.3：缺 personas 必須回 422，不再退回 legacy 4-crew。"""
    token = await _register_teacher(client, "proj_nopers@test.com")
    resp = await client.post(
        "/api/projects",
        json={"name": "No Personas"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_one_human_one_seat_in_project(client: AsyncClient):
    """Phase 21：同一專案內，一個人類只能佔一個席位。"""
    token = await _register_teacher(client, "proj_1seat@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "1-Seat Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    # 第一個席位 — 成功
    first = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200

    # 同一個人嘗試坐第二個席位 — 應該被擋
    second = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_first_human_activates_dormant_seats(client: AsyncClient):
    """Phase 21：建立專案時 AI 全部 dormant，第一位真人入座後其餘席位陸續激活。"""
    token = await _register_teacher(client, "proj_activate@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Activate Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    # 剛建立 — 所有 AI 席位 is_active=False
    before_join = await client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert all(s["is_active"] is False for s in before_join.json()["seats"])

    # 第一位真人入座 crew_1
    await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Supervisor 應該被立刻激活；其餘 crew 由 background task 錯開激活——
    # 此處只斷言 supervisor 與真人席位狀態，避免 race condition。
    after_join = await client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    seats = {s["seat_role"]: s for s in after_join.json()["seats"]}
    assert seats["supervisor"]["is_active"] is True
    assert seats["crew_1"]["occupant_type"] == "human"


@pytest.mark.asyncio
async def test_custom_ai_crew_count(client: AsyncClient):
    """Phase 21：教師可指定 ai_crew_count=1 → 只開 1 個 AI 組員 + 1 supervisor。"""
    token = await _register_teacher(client, "proj_count1@test.com")
    from app.tests._persona_fixtures import make_personas_payload

    resp = await client.post(
        "/api/projects",
        json={
            "name": "Mini Project",
            "ai_crew_count": 1,
            "personas": make_personas_payload(1),
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    seats = resp.json()["seats"]
    roles = sorted(s["seat_role"] for s in seats)
    assert roles == ["crew_1", "supervisor"]


@pytest.mark.asyncio
async def test_ai_crew_count_personas_mismatch(client: AsyncClient):
    """Phase 21：personas 數量必須與 ai_crew_count 匹配。"""
    token = await _register_teacher(client, "proj_mismatch@test.com")
    from app.tests._persona_fixtures import make_personas_payload

    resp = await client.post(
        "/api/projects",
        json={
            "name": "Mismatch Project",
            "ai_crew_count": 4,
            "personas": make_personas_payload(2),  # only 2 — should fail
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_leave_keeps_seat_dormant_when_no_humans_remain(client: AsyncClient):
    """人類離席後若場上 0 人類 → 該席位保留 dormant，作為下一位人類的就座暗示。"""
    token = await _register_teacher(client, "proj_reserve@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Reserve Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    leave_resp = await client.post(
        f"/api/projects/{project_id}/leave",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert leave_resp.status_code == 200

    after = await client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    crew1 = next(s for s in after.json()["seats"] if s["seat_role"] == "crew_1")
    assert crew1["occupant_type"] == "ai"
    assert crew1["is_active"] is False, "離席後場上 0 人類，crew_1 應保留 dormant"


@pytest.mark.asyncio
async def test_join_second_human_returns_409_project_full(client: AsyncClient):
    """Phase 23 v1.4：每專案最多 1 位人類。第二位 user join → 409。

    spec/17 §3.4 + spec/06 §2.3：detail 必須等於 'This project already has a human participant'。
    """
    teacher_token = await _register_teacher(client, "proj_full_t@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Full Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    project_id = create_resp.json()["id"]

    # 註冊第二位學生帳號
    await client.post(
        "/api/teacher/students",
        json={
            "email": "proj_full_s@test.com",
            "password": "pass",
            "display_name": "Student B",
            "can_create_project": False,
        },
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "proj_full_s@test.com", "password": "pass"},
    )
    student_token = login_resp.json()["access_token"]

    # 教師先佔 crew_1
    first = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert first.status_code == 200

    # 第二位 user 嘗試佔 crew_2 → 預期 409 project-has-human
    second = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_2"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "This project already has a human participant"


@pytest.mark.asyncio
async def test_join_user_already_occupies_beats_project_full(client: AsyncClient):
    """Phase 23 v1.4 檢查順序：user-already-occupies 優先於 project-has-human。"""
    teacher_token = await _register_teacher(client, "proj_order_t@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Order Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    project_id = create_resp.json()["id"]

    first = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert first.status_code == 200

    # 同一位 user 再 join crew_2 → 應該打到「user 已佔位」(409) 而非「project 已有人類」
    again = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "crew_2"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "You already occupy a seat in this project"


@pytest.mark.asyncio
async def test_join_supervisor_returns_403(client: AsyncClient):
    """Phase 18 supervisor AI-only lock 仍是最高優先（403），不會被 409 蓋過。"""
    teacher_token = await _register_teacher(client, "proj_sup_t@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Sup Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    project_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": "supervisor"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 403
    assert "Supervisor" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_project_rejects_partial_personas(client: AsyncClient):
    token = await _register_teacher(client, "proj_partpers@test.com")
    # Phase 21：personas 數量必須等於 ai_crew_count（預設 3），給 2 位應該 422。
    resp = await client.post(
        "/api/projects",
        json={
            "name": "Partial Personas",
            "personas": VALID_PERSONAS_PAYLOAD[:2],  # only crew_1, crew_2
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

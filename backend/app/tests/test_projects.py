import pytest
from httpx import AsyncClient

from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG

# 座位模型：supervisor(AI) + crew_1..N(常駐 AI) + human_creator(真人專屬席，綁 creator)。
# 預設 ai_crew_count=3 → supervisor + crew_1..3 + human_creator = 5 席。
HUMAN_SEAT = "human_creator"


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
    # ai_crew_count=3 → supervisor + 3 crew + human_creator = 5 席。
    assert len(data["seats"]) == 5
    by_role = {s["seat_role"]: s for s in data["seats"]}
    assert HUMAN_SEAT in by_role
    # 真人席：occupant_type='human' 但尚未入座（user_id 空、is_active False）。
    assert by_role[HUMAN_SEAT]["occupant_type"] == "human"
    assert by_role[HUMAN_SEAT].get("user_id") in (None, "")
    # AI 席（supervisor + crew_*）建立時全 dormant。
    ai_seats = [s for s in data["seats"] if s["seat_role"] != HUMAN_SEAT]
    assert all(s["occupant_type"] == "ai" for s in ai_seats)
    # 建立時所有席位（含空真人席）is_active=False。
    assert all(s.get("is_active") is False for s in data["seats"])
    # 建立者的 viewer_role 為 creator。
    assert data.get("viewer_role") == "creator"


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
    # supervisor + 3 crew + human_creator = 5 席。
    assert len(resp.json()["seats"]) == 5


@pytest.mark.asyncio
async def test_creator_join_and_leave_human_seat(client: AsyncClient):
    """creator 入座唯一的真人專屬席，離席後回到空置（vacant，不轉 AI）。"""
    token = await _register_teacher(client, "proj_jl@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Join Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]

    # creator 入座真人席
    join_resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": HUMAN_SEAT,
    }, headers={"Authorization": f"Bearer {token}"})
    assert join_resp.status_code == 200, join_resp.text
    assert join_resp.json()["seat"]["occupant_type"] == "human"

    # 驗證席位已入座
    get_resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    human = next(s for s in get_resp.json()["seats"] if s["seat_role"] == HUMAN_SEAT)
    assert human["occupant_type"] == "human"
    assert human["user_id"] is not None
    assert human["is_active"] is True

    # 離席
    leave_resp = await client.post(f"/api/projects/{project_id}/leave", headers={
        "Authorization": f"Bearer {token}",
    })
    assert leave_resp.status_code == 200

    # 驗證席位回到空置：仍是 human、但 user_id 清空、is_active False，且未生 AI。
    get_resp2 = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {token}",
    })
    human_after = next(s for s in get_resp2.json()["seats"] if s["seat_role"] == HUMAN_SEAT)
    assert human_after["occupant_type"] == "human"
    assert human_after["user_id"] is None
    assert human_after["is_active"] is False


@pytest.mark.asyncio
async def test_crew_seats_are_ai_only(client: AsyncClient):
    """crew_* 為常駐 AI，真人不可入座 → 403。"""
    token = await _register_teacher(client, "proj_crewlock@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Crew Lock Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {token}"})
    project_id = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": "crew_1",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, resp.text
    assert "AI-only" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_only_creator_can_take_human_seat(client: AsyncClient):
    """真人席綁定 creator：非建立者入座 → 403。"""
    teacher_token = await _register_teacher(client, "proj_owner@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Owner Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {teacher_token}"})
    project_id = create_resp.json()["id"]

    # 另一位使用者（非 creator）嘗試入座真人席 → 403
    other_token = await _register_teacher(client, "proj_owner_other@test.com")
    resp = await client.post(f"/api/projects/{project_id}/join", json={
        "seat_role": HUMAN_SEAT,
    }, headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 403, resp.text
    assert "creator" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_non_member_cannot_read_project(client: AsyncClient):
    """既非 creator 亦非列管老師的隨機登入者 → 403，連讀都不行。"""
    teacher_token = await _register_teacher(client, "proj_priv@test.com")
    create_resp = await client.post("/api/projects", json={
        "name": "Private Project",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }, headers={"Authorization": f"Bearer {teacher_token}"})
    project_id = create_resp.json()["id"]

    stranger_token = await _register_teacher(client, "proj_priv_stranger@test.com")
    resp = await client.get(f"/api/projects/{project_id}", headers={
        "Authorization": f"Bearer {stranger_token}",
    })
    assert resp.status_code == 403, resp.text


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
async def test_creator_cannot_double_occupy(client: AsyncClient):
    """creator 已入座真人席後，再次入座同席 → 409。"""
    token = await _register_teacher(client, "proj_1seat@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "1-Seat Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    first = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": HUMAN_SEAT},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200, first.text

    # 再次入座同一席 → 409
    second = await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": HUMAN_SEAT},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_first_human_activates_dormant_seats(client: AsyncClient):
    """建立專案時 AI 全部 dormant，creator 入座真人席後 AI 陸續激活。"""
    token = await _register_teacher(client, "proj_activate@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Activate Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    # 剛建立 — 所有席位 is_active=False
    before_join = await client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert all(s["is_active"] is False for s in before_join.json()["seats"])

    # creator 入座真人席
    await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": HUMAN_SEAT},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Supervisor 立刻激活；其餘 crew 由 background task 錯開激活——此處只斷言 supervisor 與真人席。
    after_join = await client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    seats = {s["seat_role"]: s for s in after_join.json()["seats"]}
    assert seats["supervisor"]["is_active"] is True
    assert seats[HUMAN_SEAT]["occupant_type"] == "human"
    assert seats[HUMAN_SEAT]["user_id"] is not None


@pytest.mark.asyncio
async def test_custom_ai_crew_count(client: AsyncClient):
    """教師指定 ai_crew_count=1 → 1 AI 組員 + supervisor + 真人席。"""
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
    assert roles == ["crew_1", "human_creator", "supervisor"]


@pytest.mark.asyncio
async def test_ai_crew_count_personas_mismatch(client: AsyncClient):
    """personas 數量必須與 ai_crew_count 匹配（真人席不計入）。"""
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
async def test_leave_returns_human_seat_to_vacant(client: AsyncClient):
    """creator 離席後真人席回到 vacant（occupant_type 仍 human、user_id 空、不生 AI）。"""
    token = await _register_teacher(client, "proj_reserve@test.com")
    create_resp = await client.post(
        "/api/projects",
        json={"name": "Reserve Project", "personas": VALID_PERSONAS_PAYLOAD, "timer_config": VALID_TIMER_CONFIG},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = create_resp.json()["id"]

    await client.post(
        f"/api/projects/{project_id}/join",
        json={"seat_role": HUMAN_SEAT},
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
    human = next(s for s in after.json()["seats"] if s["seat_role"] == HUMAN_SEAT)
    assert human["occupant_type"] == "human", "離席後仍是真人專屬席，不轉 AI"
    assert human["user_id"] is None
    assert human["is_active"] is False, "離席後回到空置 vacant"


@pytest.mark.asyncio
async def test_join_supervisor_returns_403(client: AsyncClient):
    """supervisor AI-only lock 仍是最高優先（403）。"""
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
    # personas 數量必須等於 ai_crew_count（預設 3），給 2 位應該 422。
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


async def _create_project(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/api/projects",
        json={
            "name": name,
            "personas": VALID_PERSONAS_PAYLOAD,
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_list_does_not_leak_other_users_projects(client: AsyncClient):
    """GET /api/projects 只回自己的專案；不得外洩他人專案。

    回歸 ``list_user_projects`` 關聯子查詢漏綁 ``Seat.project_id == Project.id`` 的
    缺陷——該缺陷會讓任何佔過 1 個席位的使用者看到全系統所有專案。
    """
    alice_token = await _register_teacher(client, "leak_alice@test.com")
    bob_token = await _register_teacher(client, "leak_bob@test.com")

    alice_pid = await _create_project(client, alice_token, "Alice Project")
    bob_pid = await _create_project(client, bob_token, "Bob Project")

    bob_list = await client.get(
        "/api/projects", headers={"Authorization": f"Bearer {bob_token}"}
    )
    assert bob_list.status_code == 200
    bob_ids = {p["id"] for p in bob_list.json()}
    assert bob_pid in bob_ids
    assert alice_pid not in bob_ids, "Bob 不應看到 Alice 的專案"


@pytest.mark.asyncio
async def test_non_member_cannot_read_subendpoints(client: AsyncClient):
    """非 creator / 列管老師的隨機登入者，連子端點都應 403（無外洩）。"""
    owner_token = await _register_teacher(client, "sub_owner@test.com")
    project_id = await _create_project(client, owner_token, "Sub Endpoint Project")

    stranger_token = await _register_teacher(client, "sub_stranger@test.com")
    headers = {"Authorization": f"Bearer {stranger_token}"}
    for path in (
        f"/api/projects/{project_id}/stage",
        f"/api/projects/{project_id}/history",
        f"/api/projects/{project_id}/messages",
        f"/api/projects/{project_id}/timer",
    ):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path} 應 403，實得 {resp.status_code}"

    # 反向驗證：creator 本人讀同樣的子端點皆可（非全擋）。
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    ok_stage = await client.get(
        f"/api/projects/{project_id}/stage", headers=owner_headers
    )
    assert ok_stage.status_code == 200

"""Phase 28 — turn_policy field + PATCH endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG


async def _register(
    client: AsyncClient, email: str, role: str = "teacher"
) -> tuple[str, dict]:
    """Register a user and return (access_token, user_dict)."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "pass-abc-123",
            "display_name": email.split("@")[0],
            "role": role,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]


async def _create_project(
    client: AsyncClient,
    token: str,
    *,
    name: str = "Turn Policy Test",
    turn_policy: str | None = None,
    teacher_signature_code: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "ai_contribution": "medium",
        "personas": VALID_PERSONAS_PAYLOAD,
        "timer_config": VALID_TIMER_CONFIG,
    }
    if turn_policy is not None:
        payload["turn_policy"] = turn_policy
    if teacher_signature_code is not None:
        payload["teacher_signature_code"] = teacher_signature_code
    resp = await client.post(
        "/api/projects",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Defaults & creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_defaults_to_cued_policy(client: AsyncClient):
    """新建專案在未指定 turn_policy 時，預設為 cued。"""
    token, _ = await _register(client, "tp_default@test.com")
    project = await _create_project(client, token)
    assert project["turn_policy"] == "cued"


@pytest.mark.asyncio
async def test_project_accepts_initial_turn_policy(client: AsyncClient):
    """建立時可指定 turn_policy（用於 pilot 反平衡的 baseline 設定）。"""
    token, _ = await _register(client, "tp_init@test.com")
    project = await _create_project(client, token, turn_policy="round_robin")
    assert project["turn_policy"] == "round_robin"


@pytest.mark.asyncio
async def test_project_rejects_invalid_initial_turn_policy(client: AsyncClient):
    token, _ = await _register(client, "tp_invalid_init@test.com")
    resp = await client.post(
        "/api/projects",
        json={
            "name": "Bad",
            "ai_contribution": "medium",
            "personas": VALID_PERSONAS_PAYLOAD,
            "timer_config": VALID_TIMER_CONFIG,
            "turn_policy": "free_for_all",  # 不在允許 enum
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/projects/{id}/turn-policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_turn_policy_by_linked_teacher_succeeds(client: AsyncClient):
    """教師被 link 之後，可切換該專案的 turn_policy。"""
    teacher_token, teacher = await _register(client, "tp_t1@test.com", role="teacher")
    teacher_sig = teacher["signature_code"]

    student_token, _ = await _register(client, "tp_s1@test.com", role="student")
    project = await _create_project(
        client,
        student_token,
        teacher_signature_code=teacher_sig,
    )

    resp = await client.patch(
        f"/api/projects/{project['id']}/turn-policy",
        json={"policy": "open_floor"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["policy"] == "open_floor"

    # GET 回來確認 DB 已更新
    get_resp = await client.get(
        f"/api/projects/{project['id']}",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert get_resp.json()["turn_policy"] == "open_floor"


@pytest.mark.asyncio
async def test_patch_turn_policy_by_non_linked_teacher_forbidden(client: AsyncClient):
    """未 link 該專案的教師不可改 — 防止跨班亂改。"""
    owning_teacher_token, owning_teacher = await _register(
        client, "tp_owner@test.com", role="teacher"
    )
    other_teacher_token, _ = await _register(
        client, "tp_other@test.com", role="teacher"
    )

    student_token, _ = await _register(client, "tp_s2@test.com", role="student")
    project = await _create_project(
        client,
        student_token,
        teacher_signature_code=owning_teacher["signature_code"],
    )

    resp = await client.patch(
        f"/api/projects/{project['id']}/turn-policy",
        json={"policy": "round_robin"},
        headers={"Authorization": f"Bearer {other_teacher_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_turn_policy_by_student_forbidden(client: AsyncClient):
    """學生（含 creator）不可走 teacher PATCH endpoint — creator 想改自己的活動請走 PATCH /{id}。"""
    teacher_token, teacher = await _register(client, "tp_t3@test.com", role="teacher")
    student_token, _ = await _register(client, "tp_s3@test.com", role="student")
    project = await _create_project(
        client,
        student_token,
        teacher_signature_code=teacher["signature_code"],
    )

    resp = await client.patch(
        f"/api/projects/{project['id']}/turn-policy",
        json={"policy": "round_robin"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_turn_policy_rejects_invalid_value(client: AsyncClient):
    teacher_token, teacher = await _register(client, "tp_t4@test.com", role="teacher")
    student_token, _ = await _register(client, "tp_s4@test.com", role="student")
    project = await _create_project(
        client,
        student_token,
        teacher_signature_code=teacher["signature_code"],
    )

    resp = await client.patch(
        f"/api/projects/{project['id']}/turn-policy",
        json={"policy": "anything_goes"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_turn_policy_404_on_missing_project(client: AsyncClient):
    teacher_token, _ = await _register(client, "tp_t5@test.com", role="teacher")
    resp = await client.patch(
        "/api/projects/00000000-0000-0000-0000-000000000000/turn-policy",
        json={"policy": "round_robin"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_creator_can_update_turn_policy_via_generic_patch(client: AsyncClient):
    """creator 可透過 PATCH /api/projects/{id}（generic update）一起改 turn_policy。"""
    token, _ = await _register(client, "tp_gp@test.com")
    project = await _create_project(client, token)
    assert project["turn_policy"] == "cued"

    resp = await client.patch(
        f"/api/projects/{project['id']}",
        json={"turn_policy": "round_robin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["turn_policy"] == "round_robin"


@pytest.mark.asyncio
async def test_project_list_includes_turn_policy(client: AsyncClient):
    token, _ = await _register(client, "tp_list@test.com")
    await _create_project(client, token, turn_policy="open_floor")
    resp = await client.get(
        "/api/projects", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert all("turn_policy" in item for item in items)
    assert any(item["turn_policy"] == "open_floor" for item in items)

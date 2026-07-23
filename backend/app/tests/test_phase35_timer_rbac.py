"""Phase 35: Timer pause/resume/extend RBAC (spec/16 §3.1).

teacher 或 project creator 通過；student 且非 creator → 403。
也驗證 TimerExtendRequest 範圍 1..30。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG


async def _register(client: AsyncClient, email: str, role: str = "teacher") -> str:
    resp = await client.post("/api/auth/register", json={
        "email": email,
        "password": "pass",
        "display_name": f"User {email}",
        "role": role,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


async def _create_project(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/projects",
        json={
            "name": "Phase35 RBAC test",
            "personas": VALID_PERSONAS_PAYLOAD,
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_student_pause_forbidden(client: AsyncClient) -> None:
    teacher_token = await _register(client, "p35_t1@test.com", role="teacher")
    project_id = await _create_project(client, teacher_token)
    student_token = await _register(client, "p35_s1@test.com", role="student")

    resp = await client.post(
        f"/api/projects/{project_id}/timer/pause",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_teacher_pause_ok(client: AsyncClient) -> None:
    teacher_token = await _register(client, "p35_t2@test.com", role="teacher")
    project_id = await _create_project(client, teacher_token)

    # 同帳號既是 teacher 又是 creator，通過
    resp = await client.post(
        f"/api/projects/{project_id}/timer/pause",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_other_teacher_can_control(client: AsyncClient) -> None:
    # spec/16 §3.1: teacher 角色（即使不是 creator）可控制 timer
    creator_token = await _register(client, "p35_t3@test.com", role="teacher")
    project_id = await _create_project(client, creator_token)
    other_teacher_token = await _register(client, "p35_t4@test.com", role="teacher")

    resp = await client.post(
        f"/api/projects/{project_id}/timer/resume",
        headers={"Authorization": f"Bearer {other_teacher_token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_extend_30_accepted(client: AsyncClient) -> None:
    teacher_token = await _register(client, "p35_e1@test.com", role="teacher")
    project_id = await _create_project(client, teacher_token)

    resp = await client.post(
        f"/api/projects/{project_id}/timer/extend",
        json={"additional_minutes": 30},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_extend_31_rejected(client: AsyncClient) -> None:
    teacher_token = await _register(client, "p35_e2@test.com", role="teacher")
    project_id = await _create_project(client, teacher_token)

    resp = await client.post(
        f"/api/projects/{project_id}/timer/extend",
        json={"additional_minutes": 31},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_extend_zero_rejected(client: AsyncClient) -> None:
    teacher_token = await _register(client, "p35_e3@test.com", role="teacher")
    project_id = await _create_project(client, teacher_token)

    resp = await client.post(
        f"/api/projects/{project_id}/timer/extend",
        json={"additional_minutes": 0},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 422, resp.text

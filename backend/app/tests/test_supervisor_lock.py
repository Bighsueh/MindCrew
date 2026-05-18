"""Phase 18 — Supervisor 席位鎖定為 AI 專屬。

驗收項目：
1. POST /api/projects/:id/join {seat_role: "supervisor"} → 403
2. POST /api/projects/:id/join {seat_role: "crew_*"} 仍正常
3. SeatManager.assign_human(seat_role="supervisor") raise ValueError
4. 教師（專案建立者）可透過 advance-stage 強制推進
5. 非建立者使用者呼叫 advance-stage → 403
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.seats.manager import SeatManager


async def _register(client: AsyncClient, email: str, role: str = "teacher") -> str:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "pass", "display_name": email.split("@")[0]},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


async def _create_project(client: AsyncClient, token: str, name: str = "Lock Test") -> str:
    from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG

    resp = await client.post(
        "/api/projects",
        json={
            "name": name,
            "ai_contribution": "medium",
            "personas": VALID_PERSONAS_PAYLOAD,
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_join_supervisor_rejected_403(client: AsyncClient):
    """真人嘗試入座 Supervisor 一律 403。"""
    token = await _register(client, "lock_sup@test.com")
    pid = await _create_project(client, token)

    resp = await client.post(
        f"/api/projects/{pid}/join",
        json={"seat_role": "supervisor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert "AI-only" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_join_crew_still_works(client: AsyncClient):
    """Crew 入座路徑不受影響。"""
    token = await _register(client, "lock_crew@test.com")
    pid = await _create_project(client, token)

    resp = await client.post(
        f"/api/projects/{pid}/join",
        json={"seat_role": "crew_1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["seat"]["occupant_type"] == "human"


@pytest.mark.asyncio
async def test_assign_human_supervisor_raises():
    """SeatManager 內部 guard：assign_human 對 supervisor raise ValueError。"""
    manager = SeatManager()
    with pytest.raises(ValueError, match="AI-only"):
        await manager.assign_human(
            project_id=uuid4(),
            seat_role="supervisor",
            user_id=uuid4(),
            user_name="Teacher",
            session=None,
        )


@pytest.mark.asyncio
async def test_teacher_can_force_advance_stage(client: AsyncClient):
    """專案建立者（teacher）可透過 advance-stage 強制推進，覆蓋舊的 supervisor seat 檢查。"""
    token = await _register(client, "force_adv@test.com")
    pid = await _create_project(client, token, name="Force Advance")

    resp = await client.post(
        f"/api/projects/{pid}/advance-stage",
        json={"from": "discover", "to": "define", "reason": "test force advance"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_stage"] == "define"


@pytest.mark.asyncio
async def test_non_creator_cannot_advance_stage(client: AsyncClient):
    """非專案建立者呼叫 advance-stage → 403。"""
    creator_token = await _register(client, "owner@test.com")
    other_token = await _register(client, "other_teacher@test.com")
    pid = await _create_project(client, creator_token, name="Owner Only")

    resp = await client.post(
        f"/api/projects/{pid}/advance-stage",
        json={"from": "discover", "to": "define"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403, resp.text

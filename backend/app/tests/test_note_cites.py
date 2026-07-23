"""cites 管線測試 — Phase 42 C0，spec 06 v4.25。

涵蓋：
1. PATCH /{project_id}/canvas/notes/{note_id}：404（不存在）/ 403（非作者 /
   未佔真人席）/ 200（作者本人）
2. HumanNoteRequest 不收 time_box_forced（只有 C2 強推路徑可寫）、收 cites
3. CanvasNoteResponse 帶 cites / time_box_forced 欄位
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.seat import Seat


async def _register(client: AsyncClient, email: str, name: str) -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "pass", "display_name": name},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {"token": data["access_token"], "user_id": UUID(data["user"]["id"])}


async def _create_project(client: AsyncClient, token: str) -> UUID:
    from app.tests._persona_fixtures import VALID_PERSONAS_PAYLOAD, VALID_TIMER_CONFIG

    resp = await client.post(
        "/api/projects",
        json={
            "name": "Cites Test Project",
            "personas": VALID_PERSONAS_PAYLOAD,
            "timer_config": VALID_TIMER_CONFIG,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


async def _seat_human(
    db_session: AsyncSession, project_id: UUID, user_id: UUID
) -> None:
    """確保 user 佔該專案真人席（既有席就改派、沒有就補一張）。"""
    existing = (
        await db_session.execute(
            select(Seat).where(
                Seat.project_id == project_id, Seat.seat_role == "human_creator"
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.occupant_type = "human"
        existing.user_id = user_id
    else:
        db_session.add(
            Seat(
                project_id=project_id,
                seat_role="human_creator",
                occupant_type="human",
                user_id=user_id,
                state="human_active",
            )
        )
    await db_session.flush()


@pytest.fixture
def _canvas(monkeypatch):
    """Mock sidecar：白板上有一張真人便條、一張 AI 便條。"""
    notes = [
        {"id": "shape:note_h1", "author": "作者甲(human)", "x": 100, "y": 100},
        {"id": "shape:note_a1", "author": "小美(ai)", "x": 300, "y": 100},
    ]
    captured: dict = {}

    from app.bridge.canvas_ops import CanvasOps

    async def _fake_full(self, project_id):
        return notes

    async def _fake_update(self, project_id, note_id, cites):
        captured["note_id"] = note_id
        captured["cites"] = cites
        return True

    monkeypatch.setattr(CanvasOps, "get_canvas_state_full", _fake_full)
    monkeypatch.setattr(CanvasOps, "update_note_cites", _fake_update)
    return captured


@pytest.mark.asyncio
class TestPatchCitesEndpoint:
    async def test_cites_endpoint_matrix(self, client, db_session, _canvas) -> None:
        """404 / 403（AI 便條）/ 403（未佔席）/ 200（作者本人）。

        合併為單一測試（單 event loop、單專案）：跨測試重建專案會踩到全域
        engine pool 跨 loop 重用的既存 flakiness（同 test_projects.py 整檔現象）。
        """
        user = await _register(client, "cites-a@test.com", "作者甲")
        stranger = await _register(client, "cites-b@test.com", "路人")
        project_id = await _create_project(client, user["token"])

        # (3) 未佔真人席（席位尚未指派給任何人）→ 403
        resp = await client.patch(
            f"/api/projects/{project_id}/canvas/notes/shape:note_h1",
            json={"cites": []},
            headers={"Authorization": f"Bearer {stranger['token']}"},
        )
        assert resp.status_code == 403

        await _seat_human(db_session, project_id, user["user_id"])

        # (1) 便條不存在 → 404
        resp = await client.patch(
            f"/api/projects/{project_id}/canvas/notes/shape:note_missing",
            json={"cites": []},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 404

        # (2) AI 便條 → 403（非作者）
        resp = await client.patch(
            f"/api/projects/{project_id}/canvas/notes/shape:note_a1",
            json={"cites": ["shape:note_h1"]},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 403

        # (4) 作者本人 + 佔真人席 → 200，全量覆蓋 cites
        resp = await client.patch(
            f"/api/projects/{project_id}/canvas/notes/shape:note_h1",
            json={"cites": ["shape:note_a1"]},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "success": True,
            "note_id": "shape:note_h1",
            "cites": ["shape:note_a1"],
        }
        assert _canvas == {"note_id": "shape:note_h1", "cites": ["shape:note_a1"]}


class TestSchemas:
    def test_human_note_request_rejects_time_box_forced_field(self) -> None:
        """time_box_forced 只有 C2 強推路徑可寫——人類請求模型沒有此欄位。"""
        from app.projects.router import HumanNoteRequest

        assert "time_box_forced" not in HumanNoteRequest.model_fields
        assert "cites" in HumanNoteRequest.model_fields

        # 帶了也不會進到模型（pydantic 預設忽略未知欄位）
        req = HumanNoteRequest(
            text="概念", x=1.0, y=2.0, sub_phase_id="1.1b",
            time_box_forced=True,  # type: ignore[call-arg]
        )
        assert not hasattr(req, "time_box_forced") or "time_box_forced" not in req.model_dump()

    def test_canvas_note_response_carries_new_fields(self) -> None:
        from app.projects.schemas import CanvasNoteResponse

        note = CanvasNoteResponse(id="n1", content="c", color="yellow")
        assert note.cites == []
        assert note.time_box_forced is False

        note2 = CanvasNoteResponse(
            id="n2", content="c", color="yellow",
            cites=["n1"], time_box_forced=True,
        )
        assert note2.cites == ["n1"]
        assert note2.time_box_forced is True

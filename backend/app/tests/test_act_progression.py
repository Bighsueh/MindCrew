"""組長 advance_sub_phase action handler（Phase 42 A1，agents/act_progression.py）。

驗證「宣布→系統執行」的執行層：成功不疊樣板、gate 未過轉內容層 reason_zh、
終局/異常靜默。act.py 白名單三層見 test_comm_mode_validator.py。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents import act_progression as ap
from app.progression import advance_router as ar


@pytest.mark.asyncio
async def test_success_passes_announce_false_and_gates_on() -> None:
    """成功推進：gate 照常（skip=False）、不疊系統樣板（announce=False）。"""
    pid = uuid4()
    with patch(
        "app.progression.advance_router.execute_advance_target",
        new=AsyncMock(return_value="sub_advanced_to_1.1b"),
    ) as ex:
        result = await ap.execute_advance_action(
            project_id=pid, agent_id="supervisor", current_sub_phase="1.1a",
        )
    assert result["success"] is True
    kwargs = ex.call_args.kwargs
    assert kwargs["skip_gate_check"] is False  # 組長不繼承教師 force 權限
    assert kwargs["announce"] is False  # 組長已自行宣布
    assert kwargs["target"].kind == "sub"


@pytest.mark.asyncio
async def test_blocked_maps_to_content_layer_reason_zh() -> None:
    """gate 未過 → rejection.reason_zh 為內容層話術（無機制詞、無英文鍵）。"""
    pid = uuid4()
    blocked = (
        "sub_advance_blocked:artifact_gate:"
        "「利害關係人」便條目前 3 張、需要 8 張"
    )
    with patch(
        "app.progression.advance_router.execute_advance_target",
        new=AsyncMock(return_value=blocked),
    ):
        result = await ap.execute_advance_action(
            project_id=pid, agent_id="supervisor", current_sub_phase="1.1b",
        )
    assert result["success"] is False
    reason = result["rejection"]["reason_zh"]
    assert "利害關係人" in reason
    for banned in ("gate", "artifact", "sub_advance", "blocked", "推進條件未達成"):
        assert banned not in reason


@pytest.mark.asyncio
async def test_gate_blocked_reason_composed_from_canonical() -> None:
    """artifact gate 拒絕字串（spec 25 §6 canonical，上游已無鍵名）收攏成組長話術。

    Phase 42 補正 R2（G11）：上游 format_gate_rejection_zh 已統一大白話，
    本層只剝 canonical 開頭＋條列轉分號——不再做逐鍵字串手術。"""
    pid = uuid4()
    blocked = (
        "sub_advance_blocked:artifact_gate:還差一點才能往下：\n"
        "  - 利害關係人便條還不夠：目前 3 張，至少要 8 張。"
    )
    with patch(
        "app.progression.advance_router.execute_advance_target",
        new=AsyncMock(return_value=blocked),
    ):
        result = await ap.execute_advance_action(
            project_id=pid, agent_id="supervisor", current_sub_phase="1.1b",
        )
    reason = result["rejection"]["reason_zh"]
    assert reason.startswith("先別急著往下")
    assert "還差一點才能往下" not in reason  # canonical 開頭由外層句子承載
    assert "利害關係人便條還不夠：目前 3 張，至少要 8 張" in reason
    assert "——；" not in reason


@pytest.mark.asyncio
async def test_terminal_position_silently_ignored() -> None:
    """已是終點（kind='none'）→ 失敗但不產生聊天噪音（rejection=None）。"""
    pid = uuid4()
    with patch.object(
        ar, "resolve_advance_target",
        return_value=ar.AdvanceTarget(kind="none", from_sub_phase="x"),
    ):
        result = await ap.execute_advance_action(
            project_id=pid, agent_id="supervisor", current_sub_phase="x",
        )
    assert result["success"] is False
    assert result["rejection"] is None


@pytest.mark.asyncio
async def test_no_sub_phase_returns_gentle_rejection() -> None:
    result = await ap.execute_advance_action(
        project_id=uuid4(), agent_id="supervisor", current_sub_phase=None,
    )
    assert result["success"] is False
    assert result["rejection"]["reason_zh"]


@pytest.mark.asyncio
async def test_system_failure_is_silent() -> None:
    """DB 等系統性失敗（如 sub_advance_failed）→ 不對聊天室發話（log 留痕）。"""
    pid = uuid4()
    with patch(
        "app.progression.advance_router.execute_advance_target",
        new=AsyncMock(return_value="sub_advance_failed"),
    ):
        result = await ap.execute_advance_action(
            project_id=pid, agent_id="supervisor", current_sub_phase="1.1a",
        )
    assert result["success"] is False
    assert result["rejection"] is None

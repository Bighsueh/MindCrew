"""2.6 time-box 強制收口（內容層安全閥）— spec 16 v2.0 §4.3 / 04-06 v4.25 §5.8.

2.6「依準則挑問題定義」取消投票後，收口僵持時唯一保證流程不死的是時間安全閥。
**時間層**（time-box 到必推進）已由 advance 的 ``skip_gate_check`` 兜底；本模組補
**內容層**：time-box 到而選定區不滿足收口閘（0 張、或有問題定義缺理由）時，由系統
硬邏輯把最有共識的 1 張候選搬進選定區、自動補一張 ``time_box_forced`` 選定理由便條，
保證 **2.7 配對閘永遠有合法輸入**（spec 25 v2.0 §3.2：forced 理由視為有效配對）。

「最有共識」採決定性啟發：候選問題定義中 ``cites`` 最多者（引用最多痛點來源＝涵蓋面
最廣）；平手取最前。組長話術與點名由 04-06 §5.8 規範（本模組只做硬邏輯兜底）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# 強制搬入選定 section 的相對落點（section 帶 w=2400 / h=700，留足邊距）。
_FORCED_PS_OFFSET = (240.0, 200.0)
_FORCED_REASON_OFFSET = (760.0, 200.0)
_FORCED_REASON_TEXT = "時間到了，先選這張往下走"


def _note_text(note: Any) -> str:
    return (getattr(note, "text", None) or getattr(note, "content", "") or "").strip()


async def force_close_selection(project_id: UUID) -> bool:
    """2.6 內容層強制收口。回 True 表示有實際補搬/補理由動作。

    Best-effort：任一步驟失敗只記 log、不拋（time-box 推進不被兜底卡住）。
    冪等性：收口閘已滿足時直接 return False（不重複補）。

    RC3（2026-07-03 review must-fix）：整段「讀-算-搬-驗」持 per-project 放置鎖——
    與 auto_reflow 讓位／create／move 序列化，杜絕「reflow 用舊快照把剛搬進選定區
    的 PS 又搬回牆上」的交錯（選定區被清空、2.7 配對閘斷炊）。本函式只直呼
    canvas_ops（不經 tool_create_note），無鎖重入問題。
    """
    from app.canvas.placement_lock import placement_lock

    async with placement_lock(project_id):
        return await _force_close_selection_locked(project_id)


async def _force_close_selection_locked(project_id: UUID) -> bool:
    from app.canvas.artifact_gate import (
        check_artifact_gate,
        _selection_members,
        _is_problem_statement,
        criteria_notes,
        is_qualified_selection_reason,
    )

    # 收口閘已滿足 → 無須兜底。
    try:
        gate = await check_artifact_gate(project_id, "2.6")
        if gate.passed:
            return False
    except Exception as exc:  # pragma: no cover - 閘檢查失敗仍嘗試兜底
        logger.debug("force_close: gate check failed (%s) — proceed", exc)

    # 讀 canvas（鎖內 fresh：寫後一致）。
    try:
        from app.canvas.analyzer import get_spatial_analyzer

        analysis = await get_spatial_analyzer().analyze(project_id, fresh=True)
        notes = list(analysis.notes)
    except Exception as exc:
        logger.warning("force_close: canvas analyze failed project=%s: %s", project_id, exc)
        return False

    # 確保有一個選定 section（組長沒開過就由系統補開，spec 27 §14）。
    section = await _ensure_selection_section(project_id)
    if section is None:
        logger.warning("force_close: no selection section and open failed project=%s", project_id)
        return False

    members = await _selection_members(project_id, notes)
    member_ids = {str(getattr(m, "id", "")) for m in members}
    selected_ps = [n for n in members if _is_problem_statement(n)]

    from app.bridge.canvas_ops import canvas_ops
    from app.agents.personas.display import resolve_display_name

    sup_name = resolve_display_name("supervisor")
    acted = False

    # (1) 選定區無問題定義 → 挑最有共識的 1 張候選搬進去。
    if not selected_ps:
        candidates = [
            n for n in notes
            if _is_problem_statement(n) and str(getattr(n, "id", "")) not in member_ids
        ]
        if not candidates:
            logger.info("force_close: no problem_statement candidates project=%s", project_id)
            return False
        chosen = max(candidates, key=lambda n: len(getattr(n, "cites", None) or ()))
        chosen_id = str(getattr(chosen, "id", ""))
        tx = float(section["x"]) + _FORCED_PS_OFFSET[0]
        ty = float(section["y"]) + _FORCED_PS_OFFSET[1]
        try:
            moved = await canvas_ops.batch_update_coordinates(
                project_id,
                [{"id": chosen_id, "x": tx, "y": ty}],
                moved_by="agent_supervisor",
            )
        except Exception as exc:
            logger.warning("force_close: move PS failed project=%s: %s", project_id, exc)
            return False
        # batch_update_coordinates 回 False＝sidecar 找不到該 id／拒絕（404）→ 別謊報選好了。
        if not moved:
            logger.warning(
                "force_close: move rejected project=%s id=%s (sidecar 找不到便條?)",
                project_id, chosen_id,
            )
            return False
        # 搬完重讀驗證：確認選定 PS 真的落進選定區帶內（batch_update 已失效快取→重抓為新）。
        # 不在區內＝雙 section 幾何不符／搬動沒持久化／被覆蓋——誠實回 False、不謊報 selected=1。
        if not await _confirm_in_selection(project_id, chosen_id):
            logger.warning(
                "force_close: moved PS not in selection after move project=%s id=%s section=%s",
                project_id, chosen_id, section.get("id"),
            )
            return False
        selected_ps = [chosen]
        acted = True

    # (2) 每張選定問題定義若缺合格/forced 配對理由 → 補一張 time_box_forced 理由便條。
    # 與 2.6 收口閘同一把尺（is_qualified_selection_reason，含準則指名判定）——
    # 否則「編造準則名」的理由會讓兜底誤以為已配對、不補 forced 理由，閘門持續卡住。
    criteria = criteria_notes(notes)

    def _is_reason(n: Any) -> bool:
        return is_qualified_selection_reason(n, criteria)

    reason_notes = [
        n for n in members
        if str(getattr(n, "id", "")) not in {str(getattr(p, "id", "")) for p in selected_ps}
        and _is_reason(n)
    ]
    for idx, p in enumerate(selected_ps):
        pid = str(getattr(p, "id", ""))
        if any(pid in (getattr(r, "cites", None) or ()) for r in reason_notes):
            continue
        rx = float(section["x"]) + _FORCED_REASON_OFFSET[0]
        ry = float(section["y"]) + _FORCED_REASON_OFFSET[1] + idx * 180.0
        try:
            await canvas_ops.add_note(
                project_id,
                content=_FORCED_REASON_TEXT,
                position={"x": rx, "y": ry},
                author_id="agent_supervisor",
                author_name=sup_name,
                cites=[pid],
                time_box_forced=True,
            )
            acted = True
        except Exception as exc:
            logger.warning("force_close: add forced reason failed project=%s: %s", project_id, exc)

    if acted:
        logger.info(
            "force_close: 2.6 selection forced project=%s selected=%d", project_id, len(selected_ps)
        )
    return acted


async def _confirm_in_selection(project_id: UUID, note_id: str) -> bool:
    """搬動後重讀，確認 note_id 真的落進某選定 section 帶內（best-effort、不拋）。

    ``batch_update_coordinates`` 成功後已失效 spatial 快取（D1d），故重抓 ``analyze``
    為搬動後的新狀態。抓不到成員＝搬動沒落地（雙 section 幾何不符／未持久化／被覆蓋），
    誠實回 False。同時 log 供 live 鑑識「搬動到底有沒有進選定區」。
    """
    from app.canvas.analyzer import get_spatial_analyzer
    from app.canvas.sections import selection_members

    try:
        fresh = await get_spatial_analyzer().analyze(project_id, fresh=True)
        members = await selection_members(project_id, list(fresh.notes))
    except Exception as exc:  # pragma: no cover - 重讀失敗保守回 False
        logger.debug("force_close: post-move re-read failed project=%s: %s", project_id, exc)
        return False
    in_zone = note_id in {str(getattr(m, "id", "")) for m in members}
    logger.info(
        "force_close: post-move check project=%s id=%s in_selection=%s members=%d",
        project_id, note_id, in_zone, len(members),
    )
    return in_zone


async def _ensure_selection_section(project_id: UUID) -> dict[str, Any] | None:
    """回傳那唯一的 canonical 選定 section（最早開的那條）；不存在則由系統補開。

    取 ``sections[0]``（最低 order＝組長最早開、crew 被導向搬入的那條）與 closing／
    perception 的 union 讀取對齊；冪等保證（spec 10 §5.9）下本就只會有一條。
    """
    from app.canvas.sections import list_sections

    sections = await list_sections(project_id)
    if not sections:
        try:
            from app.canvas.tools_zones import tool_open_section
            from app.agents.personas.display import resolve_display_name

            await tool_open_section(
                project_id,
                title="選定區｜要往下做的問題",
                author_id="agent_supervisor",
                author_name=resolve_display_name("supervisor"),
            )
        except Exception as exc:
            logger.warning("force_close: open_section failed project=%s: %s", project_id, exc)
            return None
        sections = await list_sections(project_id)
    return sections[0] if sections else None


__all__ = ["force_close_selection"]

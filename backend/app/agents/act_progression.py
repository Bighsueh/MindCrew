"""組長 `advance_sub_phase` action 的執行 handler（Phase 42 A1，spec 04-06 §5.8）。

獨立模組（act.py 已逼近行數上限）。「宣布→系統執行」：組長在同一批 actions 裡
先發轉場 chat_message、再發本 action；本 handler 解析三層推進位置並執行。

硬 gate 仍由系統強制（skip_gate_check 恆 False——組長 AI 不繼承教師 force 權限）。
gate 未過 → 回 canvas-rejection 風格 dict，act.py 沿用 `_explain_canvas_rejection`
通道把內容層 reason_zh 發進聊天室（每回合上限沿用，不講機制名 #29）。

成功推進不發樣板交代——組長已自行宣布（樣板僅 watcher 兜底，04-03 §3.0.2）。
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def execute_advance_action(
    project_id: UUID,
    agent_id: str,
    current_sub_phase: str | None,
) -> dict:
    """執行組長宣布的推進。回傳 {success, result, rejection?{reason_zh}}。"""
    from app.progression.advance_router import (
        execute_advance_target,
        resolve_advance_target,
    )

    if not current_sub_phase:
        return {
            "success": False,
            "result": "sub_advance_blocked:no_sub_phase",
            "rejection": {"reason_zh": "我們先把目前這一步走穩，晚點再往下。"},
        }

    target = resolve_advance_target(current_sub_phase)
    if target.kind == "none":
        return {
            "success": False,
            "result": "sub_advance_blocked:terminal",
            "rejection": None,  # 已是終點：靜默忽略，不對聊天室造成噪音
        }

    result = await execute_advance_target(
        project_id=project_id,
        agent_id=agent_id,
        target=target,
        skip_gate_check=False,
        announce=False,  # 組長已自行宣布轉場，不再疊系統樣板
    )
    logger.info(
        "supervisor advance project=%s from=%s kind=%s result=%s",
        project_id, current_sub_phase, target.kind, result,
    )

    if isinstance(result, str) and result.startswith("sub_advance_blocked"):
        return {
            "success": False,
            "result": result,
            "rejection": {"reason_zh": _blocked_reason_zh(result)},
        }
    if isinstance(result, str) and (
        result.startswith("sub_advanced")
        or result.startswith("micro_advanced")
        or result.startswith("advanced_to_")
    ):
        return {"success": True, "result": result}
    return {
        "success": False,
        "result": str(result),
        "rejection": None,  # 系統性失敗（DB 等）：log 已留痕，不對聊天室噪音
    }


def _blocked_reason_zh(result: str) -> str:
    """把 blocked 結果字串轉成給組長唸的內容層話術（無機制名、無英文模板鍵）。

    Phase 42 補正 R2（G11）：上游 format_gate_rejection_zh 已是 spec 25 §6
    canonical 大白話（標籤表統一、無鍵名洩漏），本函式只做格式收攏——
    刪掉舊「推進條件未達成：」剝除與逐鍵字串手術。
    """
    detail = ""
    # Phase 42 D1d (G01)：真人硬閘——reason 已是內容層完整句（human_gate_blocks 產），
    # 直接用、別把「human_gate:」機器前綴唸出去（#29）。
    if result.startswith("sub_advance_blocked:human_gate:"):
        return result.split(":", 2)[2].strip()
    if result.startswith("sub_advance_blocked:artifact_gate:"):
        detail = result.split(":", 2)[2].strip()
        # canonical 開頭「還差一點才能往下：」在本話術裡由外層句子承載，收掉；
        # 條列轉分號串接。
        detail = detail.replace("還差一點才能往下：", "").strip()
        detail = detail.replace("\n  - ", "；").lstrip("；").rstrip("。").strip()
    elif result.startswith("sub_advance_blocked:"):
        detail = result.split(":", 1)[1].strip()
    if detail and detail not in ("no_sub_phase", "terminal", "unknown_position"):
        return f"先別急著往下——{detail}。帶大家把這些補齊，我們再走。"
    return "先別急著往下——這一關還有關鍵的東西沒到位，帶大家補一下再走。"

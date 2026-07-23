"""「本關訊號」面板（Phase 42 A1，spec 04-06 §5.8 / spec 16 §4 v2.0）。

只餵組長（supervisor）：gate 計數／真人參與狀態／群數／時間餘量／邊界評估訊號。
由 context_buffer 注入（seat_role gate）、context_serializer passthrough 渲染。

輸出為已序列化的繁中字串（與 tool_status 同模式），決定性、可單元測試。
面板是 agent 內部資訊；prompt 層已教組長不得對學員轉述機制詞（spec 04-03 §3.0.1）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.stages.sub_phases import SUB_PHASES

logger = logging.getLogger(__name__)

async def build_signal_panel(
    project_id: UUID,
    sub_phase: str,
    *,
    time_budget_used_pct: float | None = None,
    cluster_count: int | None = None,
    current_micro_phase: str | None = None,
    share_status=None,
) -> str | None:
    """組出面板字串；sub_phase 未知時回 None。

    ``share_status``（``share_experience.ShareStatus`` 或 None）：1.1a 經驗分享參與快照，
    由 context_buffer 預算好傳入（避免雙重 round_lock 讀）；未傳則本函式自行計算。
    """
    sp = SUB_PHASES.get(sub_phase)
    if sp is None:
        return None

    # 暖場（Phase 42 B1，spec 28 v2.0 §5）：專屬面板——便條進度／軟硬時間／
    # 全員參與／三情境收尾指引，組長據此辨識情境並決定收尾時機。
    if sp.macro_stage == "warmup":
        return await _warmup_panel(project_id, sub_phase)

    lines: list[str] = ["【本關訊號】（推進節奏判斷用；不要對學員提到這個區塊）"]
    lines.append(await _artifact_line(project_id, sp))
    lines.append(await _human_line(project_id, sub_phase))
    # 1.1a 經驗分享（Phase 42，spec 22 1.1a「每位 crew 接過 ≥1 自身經驗」）：全員分享
    # 進度——讓組長依「真實完成條件」推進，而非在隊友沉默時被時間默默推走。
    share_line = await _share_line(project_id, sub_phase, share_status)
    if share_line:
        lines.append(share_line)
    if cluster_count is not None:
        lines.append(f"- 白板群數：{cluster_count}")
    time_line = await _time_line(project_id, sub_phase, time_budget_used_pct)
    if time_line:
        lines.append(time_line)
    boundary_line = await _boundary_line(project_id, current_micro_phase, sub_phase)
    if boundary_line:
        lines.append(boundary_line)
    return "\n".join(lines)


# 三情境收尾指引（spec 28 §5.2；組長內部判斷用、不可逐字唸給學員）。
_WARMUP_SCENARIO_HINTS: dict[int, str] = {
    1: (
        "已達標——可以收尾了：替團隊高興、點 1–2 張具體點子當亮點，"
        "做完收尾橋接（回顧＋肯定＋接到真實題目、邀使用者先講）再宣布往下"
    ),
    2: (
        "軟目標時間到、還沒達標——**先不要收尾**：明講現在幾張、離目標還差幾張，"
        "宣布把時間延長到 5 分鐘、鼓勵大家再衝一波（換個方向想）"
    ),
    3: (
        "硬上限到了——直接收尾：坦白沒湊到目標（不假裝達標、不責備任何人）、"
        "肯定已有點子的具體內容，做完收尾橋接再宣布往下，不要硬卡"
    ),
}


async def _warmup_panel(project_id: UUID, sub_phase: str) -> str:
    """暖場版本關訊號（Phase 42 B1）：N/目標、軟3硬5、全員參與、情境指引。"""
    from app.progression.warmup_exit import WARMUP_SOFT_SECONDS, warmup_status

    lines: list[str] = ["【本關訊號】（推進節奏判斷用；不要對學員提到這個區塊）"]
    try:
        status = await warmup_status(project_id)
    except Exception:
        logger.debug("warmup panel status failed", exc_info=True)
        lines.append("- 暖場狀態暫時讀不到，先以現場觀察為準")
        return "\n".join(lines)

    if status.note_count is None:
        lines.append(f"- 暖場進度：白板暫時讀不到（團隊目標 {status.goal} 張）")
    else:
        mark = (
            "已達標"
            if status.goal_reached
            else f"還差 {status.goal - status.note_count} 張"
        )
        lines.append(
            f"- 暖場進度：便條 {status.note_count} / 目標 {status.goal} 張（{mark}）"
        )

    if status.elapsed_seconds is None:
        lines.append("- 時間：計時器還沒啟動（軟目標 3 分鐘、硬上限 5 分鐘）")
    else:
        m, s = divmod(int(status.elapsed_seconds), 60)
        soft_min = WARMUP_SOFT_SECONDS // 60
        lines.append(
            f"- 時間：已過 {m} 分 {s:02d} 秒（軟目標 {soft_min} 分鐘、硬上限 5 分鐘）"
        )

    lines.append(await _human_line(project_id, sub_phase))

    if status.missing_crews:
        lines.append(
            "- 全員參與：" + "、".join(status.missing_crews) + " 還沒玩到（點他們接一個）"
        )
    elif status.human_participated:
        lines.append("- 全員參與：大家都玩過了")
    else:
        lines.append("- 全員參與：使用者還沒玩到（先邀他貼一張便條、說一句想法）")

    if status.scenario is not None:
        lines.append("- 收尾指引：" + _WARMUP_SCENARIO_HINTS[status.scenario])
    else:
        lines.append(
            "- 收尾指引：還在衝量——維持回合節奏（每輪都等使用者），時間還夠、先不收"
        )
    return "\n".join(lines)


async def _share_line(
    project_id: UUID, sub_phase: str, share_status=None
) -> str | None:
    """1.1a「全員分享」訊號行（Phase 42，spec 22 1.1a）。非 1.1a 回 None。

    口徑與 B13 邀請 trigger、cued 安全網同源（share_experience.share_status）。
    """
    from app.progression.share_experience import SHARE_SUB_PHASE

    if sub_phase != SHARE_SUB_PHASE:
        return None
    try:
        if share_status is None:
            from app.progression.share_experience import (
                share_status as _share_status,
            )

            share_status = await _share_status(project_id)
    except Exception:
        logger.debug("signal panel share line failed", exc_info=True)
        return None
    if not share_status.has_human:
        return "- 全員分享：這間是全 AI 房，沒有逐一邀請的門檻"
    if share_status.missing_crews:
        return (
            "- 全員分享："
            + "、".join(share_status.missing_crews)
            + " 還沒分享過自身經驗（一位一位點名邀他們講，一次一位）"
        )
    if not share_status.human_shared:
        return "- 全員分享：隊友都分享過了，還沒聽到使用者的經驗（邀他講一段）"
    return "- 全員分享：大家都分享過自身經驗了，內容夠了就可以往下"


async def _artifact_line(project_id: UUID, sp) -> str:
    """gate 計數：硬格列各類產出現量/門檻；軟格說明無硬性門檻。"""
    has_counts = bool(sp.min_artifact_counts)
    has_deliverables = bool(sp.deliverables_required)
    if not has_counts and not has_deliverables:
        return "- 產出：本關沒有硬性產出門檻（節奏由你判斷，聊得夠深就可以往下）"

    pieces: list[str] = []
    if has_counts:
        try:
            from app.canvas.artifact_gate import check_artifact_gate
            from app.canvas.text_templates import TEMPLATES

            gate = await check_artifact_gate(project_id, sp.id)
            if not gate.counts and gate.passed and gate.missing == {} and gate.requirements:
                # 分析失敗時 artifact_gate 會 graceful pass 且 counts 為空——
                # 標示「讀不到」而非 0，避免組長被誤導去催繳已存在的產出。
                pieces.append("白板狀態暫時讀不到，先以聊天觀察為準")
            else:
                for key, need in gate.requirements.items():
                    tpl = TEMPLATES.get(key)
                    label = tpl.name_zh if tpl is not None else key
                    have = gate.counts.get(key, 0)
                    mark = "已達標" if have >= need else f"還差 {need - have}"
                    pieces.append(f"{label} {have}/{need}（{mark}）")
        except Exception:
            logger.debug("signal panel artifact gate failed", exc_info=True)
            pieces.append("白板狀態暫時讀不到，先以聊天觀察為準")
    if has_deliverables:
        try:
            from app.stages.deliverables import check_deliverables

            check = await check_deliverables(project_id, sp.id)
            if check.passed:
                pieces.append("指定產出已備齊")
            else:
                pieces.append("；".join(check.missing))
        except Exception:
            logger.debug("signal panel deliverables failed", exc_info=True)
    return "- 產出：" + ("；".join(pieces) if pieces else "讀取中")


def _required_zh(required: dict) -> str:
    """把回合鎖 required 型態轉成內部白話（供組長判斷用，非對學員話術）。"""
    labels: list[str] = []
    if required.get("note"):
        labels.append("貼一張便條")
    if required.get("chat"):
        labels.append("在聊天說想法")
    if required.get("move"):
        labels.append("在白板上挪便條")
    if required.get("confirm"):
        labels.append("做個確認")
    if not labels:
        return "回應一下"
    joiner = "、也要" if required.get("mode") == "all" else "、或"
    return joiner.join(labels)


async def _human_line(project_id: UUID, sub_phase: str) -> str:
    """真人參與：A2 起改讀回合鎖權威狀態（取代 A1 的 ≥15 字近似）。"""
    from app.agents import round_lock

    try:
        state = await round_lock.get_state(project_id, sub_phase)
        if not state.get("has_human"):
            return "- 真人參與：這間是全 AI 房，沒有真人參與門檻"
        round_no = state.get("round", 1)
        if state.get("waiting"):
            need = _required_zh(state.get("required") or {})
            return (
                f"- 真人參與：第 {round_no} 回合 AI 都講過了，正在等使用者{need}"
                "（先別替他做、先邀請他）"
            )
        if state.get("human_satisfied"):
            return f"- 真人參與：第 {round_no} 回合，使用者已經有有效參與了"
        acted = len(state.get("crews_acted") or [])
        total = state.get("ai_crew_total") or 0
        return (
            f"- 真人參與：第 {round_no} 回合進行中（AI 已發言 {acted}/{total}）；"
            "輪到使用者時記得先邀請他"
        )
    except Exception:
        logger.debug("signal panel human line failed", exc_info=True)
        return "- 真人參與：狀態暫時讀不到"


async def _time_line(
    project_id: UUID, sub_phase: str, used_pct: float | None
) -> str | None:
    if used_pct is None:
        return "- 時間：計時器還沒啟動"
    if used_pct >= 100.0:
        return "- 時間：本關時間已用完——請誠實收尾（明講時間到了）並宣布往下"
    remain_pct = 100.0 - used_pct
    line = f"- 時間：已用 {used_pct:.0f}%、剩 {remain_pct:.0f}%"
    try:
        from app.timer.calculator import get_phase_budget_seconds
        from app.timer.service import TimerService

        config = await TimerService.get_config(project_id)
        budget = get_phase_budget_seconds(config, sub_phase)
        if budget:
            remain_min = budget * remain_pct / 100.0 / 60.0
            line += f"（約 {max(1, round(remain_min))} 分鐘）"
    except Exception:
        logger.debug("signal panel time line budget failed", exc_info=True)
    return line


async def _boundary_line(
    project_id: UUID,
    current_micro_phase: str | None,
    current_sub_phase: str | None = None,
) -> str | None:
    """Evaluator 邊界訊號（僅 micro 末格有意義；換格/無訊號時不顯示）。"""
    try:
        from app.progression.boundary_signal import get_boundary_signal

        sig = await get_boundary_signal(
            project_id, current_micro_phase, current_sub_phase
        )
    except Exception:
        return None
    if not sig:
        return None
    if sig.get("ready"):
        return "- 內容評估：這一段的內容看起來夠了，產出與真人參與都到位就可以宣布往下"
    weak = sig.get("weak_areas") or []
    if weak:
        return "- 內容評估：還可以更好——" + "；".join(str(w) for w in weak[:3])
    return None

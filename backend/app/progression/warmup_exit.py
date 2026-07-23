"""暖場退場狀態彙整（Phase 42 B1，spec 28 v2.0 §5 / spec 16 v2.0 §4.4）。

單一真相來源：evaluator（邊界訊號）、advance gate（組長推進檢查）、signal_panel
（組長面板）、watcher（兜底）四處共用同一份 ``warmup_status``，不各算各的。

退場公式（spec 28 v2.1 §5.1）::

    退場 = (達團隊目標 AND 全員至少參與一次) OR 硬上限 5 分鐘到

歷史：spec 28 v2.0 §5.1 字面為 `(達標 OR 硬上限) AND 全員參與`，2026-06-12 B1 live
驗收實證該字面在「某 crew 失能不輸出＋組長健在」時把房間軟卡在 0.0a（watcher
「硬上限＋失能」雙條件兜底永不開火），與 §5.3 防死鎖明文「硬上限 5 分鐘到仍走
情境 3 收尾推進（對照 2026-06-08 盲測 1.1b 死鎖教訓）」矛盾。**spec 28 v2.1
（2026-06-14，落差核對 G02）已以模擬為準改為上式，本 code 不再是偏離**——硬上限
＝最終覆蓋（與一般格 time-box 語意一致，spec 04-06 §4.2）；「全員參與」只擋「達標
提前收尾」，硬上限後改記入 missing_zh 供組長誠實帶過。

「收尾橋接」由推進路徑結構性保證——常態唯一推進路徑＝組長宣布（含回顧＋肯定＋
橋接，04-03 §3.0.5）；watcher 兜底樣板自帶橋接交代。

口徑（spec 28 §3.2 / §5.1；B1 裁定記錄於 progress.md）：
- 計數：0.0a 牆上 kind=content 便條（label 不計；組長示範便條計入；去重靠建立時擋）。
- 真人參與：round_lock round ≥2 或本回合已有過檢核的輸入（≥1 次實質輸出即算）。
- AI crew 參與：round_lock 累積 participated 集合（每席 ≥1 則實質輸出，不做字數檢核）。
- 全 AI 房：真人 gate 與回合鎖自動滿足（不卡死）；crew 參與亦自動滿足
  （round_lock 在全 AI 房不追蹤——crew 衝量本來就是他們唯一在做的事）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

# 軟目標 3 分／硬上限 5 分（固定、所有 preset 相同；spec 16 §2.1/§4.4 v2.0）。
# re-export 給消費端（signal_panel 等）。
from app.timer.calculator import WARMUP_SOFT_SECONDS

logger = logging.getLogger(__name__)

WARMUP_SUB_PHASE = "0.0a"


@dataclass(frozen=True)
class WarmupStatus:
    """暖場退場判定的完整訊號快照。"""

    note_count: int | None        # 牆上替代用途便條數（讀不到＝None，保守不當 0）
    goal: int                     # 團隊目標張數（max(8, round(20×intensity))）
    elapsed_seconds: int | None   # 本關已用秒數（timer 未啟動＝None）
    soft_reached: bool            # 軟目標 3 分已到
    hard_reached: bool            # 硬上限 5 分已到
    goal_reached: bool            # 達標（note_count ≥ goal；讀不到視為未達）
    human_participated: bool      # 真人至少參與一次（全 AI 房恆 True）
    missing_crews: tuple[str, ...]  # 還沒出過聲的 AI crew 顯示名（全 AI 房恆空）
    scenario: int | None          # 三情境：1=達標慶祝 2=軟到未達宣延長 3=硬到坦白收尾
    ready: bool                   # §5.1 前兩項：(達標 OR 硬上限) AND 全員參與
    missing_zh: tuple[str, ...] = field(default_factory=tuple)  # 內容層缺項（給組長）


def classify_scenario(
    goal_reached: bool, soft_reached: bool, hard_reached: bool
) -> int | None:
    """三情境判定（spec 28 §5.2）。回 None＝還在玩（未達標且軟目標未到）。

    達標（不論幾分鐘）→ 情境 1（3–5 分中途達標立即進情境 1）；
    硬上限到仍未達 → 情境 3；軟目標到未達 → 情境 2。
    """
    if goal_reached:
        return 1
    if hard_reached:
        return 3
    if soft_reached:
        return 2
    return None


async def _count_warmup_notes(project_id: UUID) -> int | None:
    """牆上 kind=content 便條數（0.0a 期間全牆都是暖場便條；label 標題不計）。"""
    try:
        from app.canvas.analyzer import get_spatial_analyzer

        analysis = await get_spatial_analyzer().analyze(project_id)
    except Exception:
        logger.debug("warmup note count failed project=%s", project_id, exc_info=True)
        return None
    return sum(
        1 for n in analysis.notes
        if getattr(n, "kind", "content") == "content"
    )


async def _participation(
    project_id: UUID,
) -> tuple[bool, tuple[str, ...]]:
    """(真人已參與, 還沒出過聲的 crew 顯示名)。全 AI 房 → (True, ())。"""
    from app.agents import round_lock

    state = await round_lock.get_state(project_id, WARMUP_SUB_PHASE)
    if not state.get("has_human"):
        return True, ()

    human_ok = (
        int(state.get("round") or 1) >= 2
        or bool(state.get("human_inputs"))
    )
    ai_crew = set(state.get("ai_crew") or [])
    participated = set(state.get("participated_crews") or [])
    missing = sorted(ai_crew - participated)

    names: list[str] = []
    for seat_role in missing:
        try:
            from app.agents.personas.display import resolve_display_name

            names.append(resolve_display_name(seat_role))
        except Exception:
            names.append(seat_role)
    return human_ok, tuple(names)


async def warmup_status(project_id: UUID) -> WarmupStatus:
    """彙整暖場退場訊號（evaluator / gate / panel / watcher 共用）。"""
    from app.timer.calculator import get_phase_budget_seconds
    from app.timer.scaling import effective_warmup_goal
    from app.timer.service import TimerService

    config = None
    try:
        config = await TimerService.get_config(project_id)
    except Exception:
        logger.debug("warmup config read failed project=%s", project_id, exc_info=True)
    goal = effective_warmup_goal(config)

    elapsed: int | None = None
    try:
        elapsed = await TimerService.get_used_seconds(project_id)
    except Exception:
        logger.debug("warmup elapsed read failed project=%s", project_id, exc_info=True)

    hard_budget = get_phase_budget_seconds(config, WARMUP_SUB_PHASE)
    soft_reached = elapsed is not None and elapsed >= WARMUP_SOFT_SECONDS
    hard_reached = (
        elapsed is not None and hard_budget > 0 and elapsed >= hard_budget
    )

    note_count = await _count_warmup_notes(project_id)
    goal_reached = note_count is not None and note_count >= goal

    human_ok, missing_crews = await _participation(project_id)
    all_participated = human_ok and not missing_crews

    # 防死鎖（§5.3 為準、§5.1 字面偏離——見模組 docstring）：硬上限＝最終覆蓋。
    ready = (goal_reached and all_participated) or hard_reached
    scenario = classify_scenario(goal_reached, soft_reached, hard_reached)

    # 缺項話術注意（#29、B1 review）：這些字串會經 act_progression 的 gate 回饋
    # 通道進聊天室（包裝為「先別急著往下——{detail}。帶大家把這些補齊…」），
    # 須是內容層、可被「補齊」承接的大白話；不可用「使用者」等系統視角詞。
    missing_zh: list[str] = []
    if not ready:
        if note_count is None:
            missing_zh.append("白板的張數我這邊一時看不清楚，先帶大家再多貼幾張、等一下再收")
        elif not goal_reached and not hard_reached:
            missing_zh.append(
                f"暖場便條目前 {note_count} 張、目標 {goal} 張——還可以再衝一波"
            )
        if not human_ok:
            missing_zh.append("還沒聽到你的點子喔——先貼一張便條、再到聊天室說一句想法")
        for name in missing_crews:
            missing_zh.append(f"{name} 還沒玩到（點他接一個）")

    return WarmupStatus(
        note_count=note_count,
        goal=goal,
        elapsed_seconds=elapsed,
        soft_reached=soft_reached,
        hard_reached=hard_reached,
        goal_reached=goal_reached,
        human_participated=human_ok,
        missing_crews=missing_crews,
        scenario=scenario,
        ready=ready,
        missing_zh=tuple(missing_zh),
    )


async def warmup_gate(project_id: UUID) -> tuple[bool, str]:
    """組長推進 0.0a 時的退場 gate：(passed, 內容層中文原因)。

    advance_router.gates_pass_with_reason 的暖場分支消費；原因字串走
    `_explain_canvas_rejection` 通道發進聊天室（內容層、無機制名 #29）。
    """
    try:
        status = await warmup_status(project_id)
    except Exception:
        logger.debug("warmup gate failed project=%s", project_id, exc_info=True)
        return False, "暖場還沒收完，先帶大家把這一段玩完"
    if status.ready:
        return True, ""
    return False, "；".join(status.missing_zh) or "暖場還沒收完，先帶大家把這一段玩完"

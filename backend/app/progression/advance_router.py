"""三層推進路由（Phase 42 A1，spec 04-06 §5.8 v4.25）。

組長宣布推進（`advance_sub_phase` action）與 watcher 兜底共用同一條執行路徑：
依「當前 sub_phase 在 micro / macro 結構中的位置」決定要呼叫哪一層推進函式——

  - micro 內細格        → ``stage_advancement.advance_sub_phase``（內建 gate）
  - micro 末格、同 macro → ``stage_advancement.advance_micro_phase``（本模組先補 gate 檢查）
  - macro 邊界 / 終局    → ``stage_advancement.advance_stage``（本模組先補 gate 檢查）

一致性 guard（v4.15 起保留）：只有走到 micro 最後一格才允許跨界，避免略過細格。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.stages.micro_phases import get_next_micro_phase, is_macro_boundary
from app.stages.sub_phases import (
    SUB_PHASE_ORDER,
    SUB_PHASES,
    get_next_sub_phase,
    is_hard_gate,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvanceTarget:
    """一次推進的解析結果。kind ∈ {'sub', 'micro', 'stage', 'none'}。"""

    kind: str
    from_sub_phase: str
    to_sub_phase: str | None = None   # kind == 'sub'
    from_micro: str | None = None     # kind == 'micro'
    to_micro: str | None = None       # kind == 'micro'
    from_stage: str | None = None     # kind == 'stage'


def is_last_sub_of_micro(sub_id: str) -> bool:
    """True 若 sub_id 是其 parent_micro_phase 的最後一格（跨界的一致性 guard）。"""
    sp = SUB_PHASES.get(sub_id)
    if sp is None:
        return True  # 未知格保守視為邊界（不做細格推進）
    micro = sp.parent_micro_phase
    subs = [s for s in SUB_PHASE_ORDER if SUB_PHASES[s].parent_micro_phase == micro]
    return bool(subs) and subs[-1] == sub_id


def resolve_advance_target(current_sub_phase: str) -> AdvanceTarget:
    """解析「往下一關」在三層結構中對應的推進動作。"""
    sp = SUB_PHASES.get(current_sub_phase)
    if sp is None:
        return AdvanceTarget(kind="none", from_sub_phase=current_sub_phase)

    if not is_last_sub_of_micro(current_sub_phase):
        nxt = get_next_sub_phase(current_sub_phase)
        if nxt is None:
            return AdvanceTarget(kind="none", from_sub_phase=current_sub_phase)
        return AdvanceTarget(
            kind="sub", from_sub_phase=current_sub_phase, to_sub_phase=nxt,
        )

    micro = sp.parent_micro_phase
    next_micro = get_next_micro_phase(micro) if micro else None
    if next_micro is None:
        # 終局（如 2.3 → completed）：交給 advance_stage 觸發結業鏈。
        return AdvanceTarget(
            kind="stage", from_sub_phase=current_sub_phase,
            from_stage=sp.macro_stage,
        )
    if is_macro_boundary(micro, next_micro):
        return AdvanceTarget(
            kind="stage", from_sub_phase=current_sub_phase,
            from_stage=sp.macro_stage,
        )
    return AdvanceTarget(
        kind="micro", from_sub_phase=current_sub_phase,
        from_micro=micro, to_micro=next_micro,
    )


async def gates_pass_with_reason(
    project_id: UUID, sub_phase: str
) -> tuple[bool, str]:
    """Dry-run 兩道 advance gate，回傳 (passed, 內容層中文原因)。

    與 ``stage_advancement.advance_sub_phase`` 內建檢查同調；任一檢查拋錯時
    保守視為未過（不貿然跨界）。原因字串給組長看（內容層、無機制名）。

    暖場（0.0a）無 deliverable / artifact gate，改走 spec 28 §5.1 退場公式
    （(達標 OR 硬上限) AND 全員參與；Phase 42 B1）——組長提早宣布收尾會被
    誠實擋下，缺什麼以內容層話術回饋。
    """
    sp = SUB_PHASES.get(sub_phase)
    if sp is not None and sp.macro_stage == "warmup":
        from app.progression.warmup_exit import warmup_gate

        return await warmup_gate(project_id)
    try:
        from app.stages.deliverables import check_deliverables

        check = await check_deliverables(project_id, sub_phase)
        if not check.passed:
            return False, "；".join(check.missing)
    except Exception:
        logger.debug("deliverable dry-run failed sub=%s", sub_phase, exc_info=True)
        return False, "這一關的關鍵產出還沒到位，再帶大家補一下"
    try:
        from app.canvas.artifact_gate import check_artifact_gate

        gate = await check_artifact_gate(project_id, sub_phase)
        if not gate.passed:
            return False, format_gate_missing_zh(gate)
    except Exception:
        logger.debug("artifact gate dry-run failed sub=%s", sub_phase, exc_info=True)
        return False, "這一關的關鍵產出還沒到位，再帶大家補一下"
    return True, ""


def format_gate_missing_zh(gate) -> str:
    """把 artifact gate 缺口轉成內容層中文——與 format_gate_rejection_zh 共用
    單一素材源（spec 25 v2.0 §6；Phase 42 補正 R2／G11 三 formatter 收斂）。"""
    from app.canvas.artifact_gate import gate_shortfall_lines_zh

    lines = [ln.rstrip("。") for ln in gate_shortfall_lines_zh(gate)]
    return "；".join(lines) if lines else "這一關的關鍵產出還沒到位"


async def human_gate_blocks(
    project_id: UUID, sub_phase: str
) -> tuple[bool, str]:
    """G01 真人硬閘（Phase 42 D1d；spec 22 §4.3／25 §5.1c／20 §11）。回 (擋, 內容層原因)。

    **硬格**（``is_hard_gate``＝6 格 1.1b/1.2/2.1/2.2/2.6/2.7）若房內有真人、且本回合
    真人尚未完成有效參與（round_lock ``human_satisfied`` 為假）→ 擋推進，把空間留給
    真人（spec 20 §11；推翻 C2「真人 gate 軟」暫定）。各格所需參與型態由 round_lock
    逐關表決定（如 2.1/2.6＝拖＋說，#27）。

    安全性：
    - **fail-closed**：``round_lock.get_state`` 在 Redis 失敗時回 ``human_satisfied=False``
      （有真人就不誤放行）；本層只在 get_state 整體拋錯（理論上不會，內部已吞例外）時
      回「不擋」以免推進因基礎設施 bug 全卡。
    - **time-box 逃生豁免**：呼叫端（execute_advance_target）以 ``not skip_gate_check``
      守衛本判定，故時間到的強推路徑永不評估真人閘（spec 20 §11.7 防死鎖）。
    - **全 AI 房**：``has_human`` 為假 → 不擋。
    """
    sp = SUB_PHASES.get(sub_phase)
    if sp is None or not is_hard_gate(sp):
        return False, ""
    try:
        from app.agents.round_lock import get_state

        state = await get_state(project_id, sub_phase)
    except Exception:
        logger.debug("human_gate get_state failed sub=%s", sub_phase, exc_info=True)
        return False, ""
    if state.get("has_human") and not state.get("human_satisfied"):
        return True, "這一步想請使用者也動手參與一下，等他這一回合做了我們再往下。"
    return False, ""


async def execute_advance_target(
    project_id: UUID,
    agent_id: str,
    target: AdvanceTarget,
    *,
    skip_gate_check: bool = False,
    announce: bool = True,
) -> str:
    """執行已解析的推進。回傳 stage_advancement 風格結果字串。

    - kind='sub'：gate 由 ``advance_sub_phase`` 內建（skip 透傳）。
    - kind='micro' / 'stage'：``advance_micro_phase`` / ``advance_stage`` 本身
      不帶 gate，本函式先對**當前格**補 dry-run gate（除非 skip_gate_check，
      即 time-box 誠實收尾路徑——時間到＝最終覆蓋，spec 04-06 §4.2）。
    """
    from app.agents.stage_advancement import (
        advance_micro_phase,
        advance_stage,
        advance_sub_phase,
    )

    # Phase 42 補正 R4（P1-9）：終態 guard——completed 房一律靜默 terminal。
    # 修復前 supervisor 迴圈無停止條件，completed 後仍反覆對 2.7 advance→gate 擋→
    # rejection 話術，LLM 空轉（兩房競爭實證燒 ~1.5h）。回值不帶 sub_advance_blocked
    # 前綴 → act 層 rejection=None 不產生聊天噪音。
    try:
        from sqlalchemy import select

        from app.db.models.project import Project
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            stage = await session.scalar(
                select(Project.current_stage).where(Project.id == project_id)
            )
        if stage == "completed":
            return "advance_noop:completed_terminal"
    except Exception:
        logger.debug("terminal guard stage read failed project=%s", project_id, exc_info=True)

    result = "sub_advance_blocked:unknown_position"

    # Phase 42 D1d (G01)：真人硬閘——硬格若房內有真人且本回合真人尚未完成有效參與 → 擋。
    # 置於 kind 分派**之前**＝一處覆蓋 sub/micro/stage 三種推進；``gates_pass_with_reason``
    # 只在 micro/stage 分支呼叫，單放那裡會漏掉 kind=sub 的硬格（如 2.2→2.3）。time-box
    # 逃生（skip_gate_check）在此豁免，與 2.6 forced_closure 互斥不相干（spec 20 §11.7）。
    if not skip_gate_check:
        h_blocked, h_reason = await human_gate_blocks(project_id, target.from_sub_phase)
        if h_blocked:
            return f"sub_advance_blocked:human_gate:{h_reason}"

    # Phase 42 C2：2.6 time-box 強制收口（內容層安全閥，spec 16 §4.3 / 04-06 §5.8）。
    # 跳閘推進（time-box 誠實收尾／教師強推）離開 2.6 前，先把選定區補到至少 1 張
    # 帶理由的選定問題定義，保證 2.7 配對閘永遠有合法輸入。best-effort、不擋推進。
    if target.from_sub_phase == "2.6" and skip_gate_check:
        try:
            from app.progression.forced_closure import force_close_selection

            await force_close_selection(project_id)
        except Exception:
            logger.warning("execute_advance: 2.6 forced closure failed", exc_info=True)

    if target.kind == "sub":
        result = await advance_sub_phase(
            project_id=project_id,
            agent_id=agent_id,
            from_sub_phase=target.from_sub_phase,
            to_sub_phase=target.to_sub_phase or "",
            skip_deliverable_check=skip_gate_check,
            announce=announce,
        )
    elif target.kind in ("micro", "stage"):
        if not skip_gate_check:
            passed, reason = await gates_pass_with_reason(
                project_id, target.from_sub_phase
            )
            if not passed:
                return f"sub_advance_blocked:artifact_gate:{reason}"
        if target.kind == "micro":
            result = await advance_micro_phase(
                project_id=project_id,
                agent_id=agent_id,
                from_phase=target.from_micro or "",
                to_phase=target.to_micro or "",
                announce=announce,
            )
        else:
            result = await advance_stage(
                current_stage=target.from_stage or "",
                project_id=project_id,
                agent_id=agent_id,
            )

    # Phase 42 A2：推進成功 → 清回合鎖（解凍、發 turn_state；spec 20 §11.7）。
    # 成功字串一律含 ``advanced_to_``（noop / blocked / failed 皆不含）。回合鎖另
    # 以 sub_phase 為界天生重置，故此清理為「提早解凍 UI」的盡力而為。
    if "advanced_to_" in result:
        try:
            from app.agents.round_lock import clear as clear_round_lock

            await clear_round_lock(project_id, target.from_sub_phase)
        except Exception:
            logger.debug("round_lock.clear after advance failed", exc_info=True)

    return result

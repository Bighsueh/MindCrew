"""Persona A triggers — Spec 14 §2.1 + Phase 18 LLM-judge integration.

每個 trigger 是 async 函式：(context) → trigger_id | None
回 trigger_id 表示應該 fire，回 None 表示不 fire。
所有「內容性質」判斷透過 llm_judge.judge_content，純計數用 rule。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.agents.llm_judge import is_violating, judge_content

logger = logging.getLogger(__name__)


# 推進前一輪要看的 sub_phase 集合（A1 用）。
# Phase 42 B1 (spec/28 §3.2/§6 v2.0)：加入 0.0a——組長進場有「貼標題＋示範便條＋
# 宣告團隊目標」的鷹架行為（warmup_game MC 腳本），A1 nudge 觸發之。
# Phase 42 C1：舊 1.5/1.6 隨 5+7 格重構移除；1.2（發想痛點，發現階段重頭戲、
# 進場鷹架重）補入。
_ANNOUNCE_PHASES: set[str] = {"0.0a", "1.1a", "1.2", "2.1", "2.2"}


async def detect_a_triggers(ctx: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Run all Persona A trigger checks. Return [(trigger_id, context_dict), ...]."""
    fired: list[tuple[str, dict[str, str]]] = []

    sub_phase = ctx.get("current_sub_phase") or ""
    if not sub_phase:
        return fired

    # A1: phase enter announce — 每個 sub_phase 只宣布「一次」（spec/16 §6.5.5 dedup）。
    # 用共用的 _supervisor_fired_triggers（Redis，sub_phase 變更時由 TimerService 重置）判定
    # 是否已宣布；取代舊的 sender/字串比對（sender 是 persona 名、content 不含 sub_phase 代號
    # → 幾乎永遠回 False → 每個 tick 重講進場白把聊天洗版）。標記由 router 在發話後寫入。
    fired_set: set[str] = ctx.get("_supervisor_fired_triggers", set()) or set()
    if sub_phase in _ANNOUNCE_PHASES and "A1_phase_enter_announce" not in fired_set:
        from app.stages.sub_phases import SUB_PHASES
        sp = SUB_PHASES.get(sub_phase)
        if sp:
            div = _divergence_label(sub_phase)
            fired.append(("A1_phase_enter_announce", {
                "sub_phase": sub_phase,
                "sub_phase_name": sp.name_zh,
                "divergence_or_convergence": div,
            }))

    # Phase 42 C1：A2（1.1d scope rationale missing）隨舊 1.1d 整格抽換移除——
    # 新 1.1d「排先後順序」明文不寫理由（spec 22 v2.0 §2.3），取捨理由留到定義階段。

    # A4: POV count < 3 in 2.2 / 2.3
    if sub_phase in ("2.2", "2.3"):
        pov_count = ctx.get("_pov_count", 0)
        if pov_count < 3:
            fired.append(("A4_pov_count_low", {
                "count": str(pov_count),
                "needed": str(3 - pov_count),
            }))

    # A5: POV tautology — LLM-judge 最後一張 POV
    last_pov = ctx.get("_last_pov_text", "")
    if sub_phase in ("2.2", "2.3") and last_pov:
        result = await judge_content(
            text=last_pov,
            rule_module="pov_quality",
            context={"sub_phase": sub_phase, "zone": "pov_wall"},
        )
        if is_violating(result, min_confidence=0.7):
            fired.append(("A5_pov_tautology", {"pov_text": last_pov[:80]}))

    # Phase 42 C2：A7（criteria-before-vote）／A8（too many winners）已隨投票機制移除——
    # 「挑選前先有準則」由 2.6 選定理由模板強制指準則承載；「選定 ≤3」由 selection_pairing
    # 收口閘（spec 25 §3.2）enforce 並以 reasons_zh 回饋組長。

    # A9: HMW not written for selected POVs (2.7)
    if sub_phase == "2.7":
        missing = ctx.get("_hmw_missing_count", 0)
        if missing > 0:
            fired.append(("A9_hmw_not_written", {"missing_count": str(missing)}))

    return fired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _divergence_label(sub_phase: str) -> str:
    """sub-phase 級別的「發散 / 收斂 / 過渡」中文標籤。

    具體分類規則委派給 `app.stages.phase_intent`，避免發散收斂定義
    散落多處（）。
    """
    from app.stages.phase_intent import (
        get_phase_intent_by_sub_phase,
        get_phase_intent_label_zh,
    )
    return get_phase_intent_label_zh(get_phase_intent_by_sub_phase(sub_phase))

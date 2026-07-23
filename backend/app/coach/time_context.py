"""DT 教練的時間預算摘要 builder（）。

設計原則：
  - Coach「看得到大概」當前 sub_phase 的 used_pct + 壓力等級 + 階段意圖，
    但「**不**催使用者做決定」——這條規則寫在 prompt 守則裡；本 builder
    只負責把資訊翻成 ≤120 字的文字，不做行為判斷。
  - 失敗時 swallow exception 回傳空字串（同 group_summary / canvas_summary
    的容錯策略），不阻擋 Coach 回覆主流程（spec §7.3）。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.stages.phase_intent import (
    get_phase_intent,
    get_phase_intent_label_zh,
)
from app.timer.pressure import (
    compute_pressure_level,
    get_pressure_label_zh,
    pressure_directive,
)

logger = logging.getLogger(__name__)


_SUMMARY_MAX_CHARS = 120


def _truncate(text: str, limit: int) -> str:
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)] + "…"


async def build_time_budget_summary(
    project_id: UUID,
    micro_phase: str | None,
) -> str:
    """產生時間預算摘要文字（≤ 120 字）供 DT 教練 prompt 插值。

    Args:
        project_id: 目標專案。
        micro_phase: 當前微階段（決定階段意圖）。

    Returns:
        摘要字串；若 timer 不可用或讀取失敗則回傳空字串。
    """
    try:
        from app.timer.service import TimerService

        used_pct = await TimerService.get_used_pct(project_id)
    except Exception as exc:  # noqa: BLE001 — 摘要失敗不擋 Coach 回覆。
        logger.debug(
            "build_time_budget_summary 取 used_pct 失敗 project=%s err=%s",
            project_id,
            exc,
        )
        return ""

    if used_pct is None or used_pct <= 0:
        return ""

    pressure = compute_pressure_level(used_pct)
    intent = get_phase_intent(micro_phase)
    pressure_zh = get_pressure_label_zh(pressure)
    intent_zh = get_phase_intent_label_zh(intent)
    directive = pressure_directive(pressure, intent)

    base = f"已用 {used_pct:.0f}%（壓力：{pressure_zh}）；本階段意圖：{intent_zh}。"
    if directive:
        base += f" 提醒方向：{directive}"
    return _truncate(base, _SUMMARY_MAX_CHARS)

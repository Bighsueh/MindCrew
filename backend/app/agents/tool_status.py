"""Phase 32 (spec/24-supervisor-tool-awareness.md §2): Tool status awareness.

Parse canvas sticky text for the first-diamond structured tools and surface a
status summary to supervisor prompts. The supervisor uses this to precisely cue
the right lens crew to fill in missing fields.

⚠️ **Phase 42 對齊**：原三工具含 **Persona Card（1.6）**——但 1.6 sub_phase 已隨 5＋7
重構移除、**Persona 不在 POC**（spec 22 v2.0 §12.5）。現行只感知 **問題定義（2.2）／
設計題目（2.7）** 兩工具（``TOOL_STATUS_SUB_PHASES``）。舊 DT persona 相關 helper
（``_aggregate_persona_status`` / ``_format_persona_block`` / ``PERSONA_FIELDS`` /
``FIELD_TO_RECOMMENDED_LENS`` / ``_extract_persona_name`` 等）已於 Phase 42 收尾
**整批移除**。tool_status 與 04-06 §5.8 訊號面板分工：本模組＝便條/模板**建構完成度**
感知、訊號面板＝**推進訊號**，非冗餘。

Design principle: read-only; takes a canvas snapshot (notes list) and returns
a status string for prompt injection. Never raises — failures degrade to
an empty string so prompts stay clean.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# Sub-phases that should receive tool_status injection.
# Phase 42 D4：移除已廢除的 1.6（Persona，不在 POC）；現行＝問題定義 2.2／設計題目 2.7。
TOOL_STATUS_SUB_PHASES: frozenset[str] = frozenset({"2.2", "2.7"})

# PS／HMW 的「who」抽取 regex。註：``_HMW_PERSONA_REF_RE`` 名含 PERSONA，但它抽的是
# HMW 句中的對象（who），屬現役 HMW 偵測、非舊 DT persona——KEEP。
# 舊 DT persona（PERSONA_FIELDS／FIELD_TO_RECOMMENDED_LENS／_PERSONA_NAME_RE／
# _extract_persona_name／_empty_persona_record／_aggregate_persona_status）已於
# Phase 42 收尾移除（persona 不在 POC，spec 22 v2.0 §12.5）。
_PROBLEM_STATEMENT_RE = re.compile(
    r"對於(?P<who>.+?)而言", re.DOTALL
)
_HMW_PERSONA_REF_RE = re.compile(r"我們如何.+?(?:幫助)?(?P<who>[一-鿿]+)", re.DOTALL)


def _classify_sticky(text: str) -> tuple[str | None, str | None]:
    """Return (template_id, who_or_None) if the text matches a known tool template.

    Heuristic-only — uses TextTemplate.pattern via validate_template, lazily
    imported to avoid a circular import. Phase 42 收尾：舊 DT persona 偵測迴圈已
    移除，只剩 problem_statement（2.2）／hmw（2.7）兩個現役工具。回傳 tuple
    ``(tid, who)`` 形以維持 ``_aggregate_ps_status`` / ``_aggregate_hmw_status`` 契約。
    """
    from app.canvas.text_templates import validate_template

    if validate_template(text, "problem_statement").passed:
        m = _PROBLEM_STATEMENT_RE.search(text)
        return ("problem_statement", m.group("who").strip() if m else None)
    if validate_template(text, "hmw").passed:
        m = _HMW_PERSONA_REF_RE.search(text)
        return ("hmw", m.group("who").strip() if m else None)
    return None, None


def _aggregate_ps_status(notes: list[Any]) -> int:
    """Return number of Problem Statements present."""
    count = 0
    for note in notes:
        text = getattr(note, "text", None) or getattr(note, "content", "") or ""
        tid, _ = _classify_sticky(text)
        if tid == "problem_statement":
            count += 1
    return count


def _aggregate_hmw_status(notes: list[Any]) -> int:
    """Return number of HMWs present (regex-validated)."""
    count = 0
    for note in notes:
        text = getattr(note, "text", None) or getattr(note, "content", "") or ""
        tid, _ = _classify_sticky(text)
        if tid == "hmw":
            count += 1
    return count


def _format_ps_block(count: int) -> str:
    # Phase 42 C2：無投票收斂（spec 27 §14）。收斂＝開選定區、搬問題定義進去、配選定理由。
    if count == 0:
        return (
            "問題定義狀態：尚未產出任何問題定義。\n"
            "建議：cue structure lens crew 起草第一張（需求句或五要件句）。"
        )
    if count < 3:
        return (
            f"問題定義狀態：已有 {count}/3 張候選。\n"
            f"建議：cue 不同 lens 的 crew 各補一張，目標至少 3 張供挑選。"
        )
    return (
        f"問題定義狀態：{count} 張候選。建議：開選定區（open_section），對著準則討論、"
        f"把最值得做的一到三張搬進去，每張配一張選定理由（全程無投票）。"
    )


def _format_hmw_block(count: int) -> str:
    # Phase 42 C2：設計題目張數＝選定數（無 ≥3 下限，spec 25 §3.3）。
    if count == 0:
        return (
            "設計題目狀態：尚未產出任何設計題目。\n"
            "建議：cue creativity lens crew 從選定的問題定義起草第一句「我們可以怎麼…？」。"
        )
    return (
        f"設計題目狀態：已有 {count} 句。建議：每張選定的問題定義都配一句"
        f"「我們可以怎麼…？」，寫的時候點選它對應的問題定義。"
    )


async def serialize_tool_status(
    project_id: UUID,
    sub_phase: str | None,
) -> str:
    """Build a tool_status block string for the supervisor prompt.

    Returns empty string when:
    - sub_phase is not one of {2.2, 2.7}
    - canvas analysis fails (best-effort, no exceptions)
    """
    if sub_phase not in TOOL_STATUS_SUB_PHASES:
        return ""

    try:
        from app.canvas.analyzer import get_spatial_analyzer

        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        notes = list(analysis.notes)
    except Exception as exc:
        logger.debug("tool_status canvas analyze failed: %s", exc)
        return ""

    blocks: list[str] = ["【工具狀態感知】"]
    # Phase 42 D4：1.6（Persona）dispatch 已移除（不在 POC）；只剩 2.2／2.7。
    if sub_phase == "2.2":
        blocks.append(_format_ps_block(_aggregate_ps_status(notes)))
    elif sub_phase == "2.7":
        blocks.append(_format_hmw_block(_aggregate_hmw_status(notes)))

    return "\n".join(blocks)


__all__ = [
    # Phase 42 收尾：舊 DT persona helper（PERSONA_FIELDS／FIELD_TO_RECOMMENDED_LENS
    # ／_aggregate_persona_status 等）已整批自本模組移除（persona 不在 POC）。
    "TOOL_STATUS_SUB_PHASES",
    "serialize_tool_status",
]

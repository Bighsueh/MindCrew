"""Phase intent — Double Diamond 發散 / 收斂 / 過渡單一真實來源。

依 specs/16-timer-system.md §6.5.2：

原本 `_DIVERGE_PHASES` 等定義散落在 `canvas/tools_perception.py`、
`agents/prompts/assembler.py`、`agents/supervisor/triggers_a.py` 三處，
彼此粒度（micro_phase vs sub_phase）也不一致。本模組把兩種粒度的判定
集中在這裡，並提供統一的中文標籤。

設計：
  - `get_phase_intent(micro_phase)` — coarse-grained，用於 canvas hints、
    crew assembler、AI agent context 等需要 micro-phase 等級判定的地方。
  - `get_phase_intent_by_sub_phase(sub_phase)` — fine-grained，用於
    sub-phase 等級宣告（例：1.1c 屬 micro_phase 1.1 但本身偏收斂）。
  - `get_phase_intent_label_zh(intent)` — 取得「發散 / 收斂 / 過渡」中文標籤。
"""

from __future__ import annotations

from typing import Literal


PhaseIntent = Literal["divergent", "convergent", "transitional"]


#: Double Diamond micro-phase 級別發散階段（對應 discover/develop 前半的擴張期）。
#: 與既有 `canvas/tools_perception._DIVERGE_PHASES` 對齊。
_DIVERGENT_MICRO_PHASES = frozenset(("1.1", "1.2", "3.1"))


#: Double Diamond micro-phase 級別收斂階段（discover/define 後半 + develop/deliver 後半）。
#: 與既有 `agents/prompts/assembler._CONVERGE_PHASES` 對齊。
_CONVERGENT_MICRO_PHASES = frozenset(("1.3", "2.3", "3.2", "3.3"))


#: Sub-phase 級別發散：來自既有 `triggers_a._divergence_label` 的 divergent 集合。
#: 注意：sub_phase "3.2"、"3.3"（無字母後綴）在 sub_phase 粒度視為發散，
#: 但對應 micro_phase 3.2/3.3 在 micro-phase 粒度則是收斂——
#: 兩者刻意保留差異：sub-phase 是更細的「當下動作」、micro-phase 是「整體階段意圖」。
_DIVERGENT_SUB_PHASES = frozenset((
    "1.1a", "1.1b", "1.5",
    "2.2",
    "3.2", "3.3",
))


#: Sub-phase 級別收斂：來自既有 `triggers_a._divergence_label` 的 convergent 集合。
_CONVERGENT_SUB_PHASES = frozenset((
    "1.1c", "1.1d", "1.6",
    "2.1", "2.5", "2.6", "2.7",
    "3.4",
    "4.1a", "4.1b", "4.1c", "4.1d", "4.1e",
    "4.2", "4.3",
))


_INTENT_LABEL_ZH: dict[PhaseIntent, str] = {
    "divergent": "發散",
    "convergent": "收斂",
    "transitional": "過渡",
}


def get_phase_intent(micro_phase: str | None) -> PhaseIntent:
    """Micro-phase 級別意圖判定（用於 canvas、crew prompt、AI context）。"""
    if not micro_phase:
        return "transitional"
    if micro_phase in _DIVERGENT_MICRO_PHASES:
        return "divergent"
    if micro_phase in _CONVERGENT_MICRO_PHASES:
        return "convergent"
    return "transitional"


def get_phase_intent_by_sub_phase(sub_phase: str | None) -> PhaseIntent:
    """Sub-phase 級別意圖判定（用於 trigger A1 phase-enter 宣告等細粒度場景）。"""
    if not sub_phase:
        return "transitional"
    if sub_phase in _DIVERGENT_SUB_PHASES:
        return "divergent"
    if sub_phase in _CONVERGENT_SUB_PHASES:
        return "convergent"
    return "transitional"


def get_phase_intent_label_zh(intent: PhaseIntent) -> str:
    """取得對應的中文標籤。"""
    return _INTENT_LABEL_ZH[intent]

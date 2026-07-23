"""Phase intent — Double Diamond 發散 / 收斂 / 過渡單一真實來源。
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


# phase_intent 語意（spec 27 v3.1 §3.1 釘死）：**只表達雙鑽石宏觀形狀**（把問題打開＝
# 發散／收窄＝收斂／深掘銜接＝過渡）。**不表達「該生新便條還是整理現成的」**——那是便條
# 手法，由 comm_mode＋逐格進場語（04-03 §3）承載。兩軸正交、不可混填（例：2.1 貼法是
# 整理現成便條，但宏觀意圖＝收斂）。

#: Double Diamond micro-phase 級別發散階段。
#: Phase 42 C1（spec 16 v2.0 §6.5.2）：1.x 全程 divergent；舊 1.3 桶已移除。
_DIVERGENT_MICRO_PHASES = frozenset(("1.1", "1.2"))


#: Double Diamond micro-phase 級別收斂階段。
#: Phase 42 C1：2.1（痛點歸類）/2.3（訂準則收斂）；2.2 桶（問題定義與深掘）混合屬性
#: → transitional（不入兩集合，細格判定見下方 sub-phase 表）。
_CONVERGENT_MICRO_PHASES = frozenset(("2.1", "2.3"))


#: Sub-phase 級別發散 — Phase 42 C1（spec 16 v2.0 §6.5.2 ＋ spec 27 v3.1 §3.1 已對齊一致）。
#: 發現階段全程「只打開、不收攏」（模擬 phase1-discover-redesign-DRAFT §15「發散為主」、
#: §43「別偷偷收斂」）→ 1.x 全 divergent（含 1.1c/1.1d——輕整理／排序是便條手法、不是
#: 宏觀收斂；標收斂會讓收斂護欄叫 crew 在 1.1c 禁拖動格去拖便條）；0.0a 衝量、2.2 生成候選
#: 亦發散。**2.3/2.4 不在此集合也不在收斂集合 → transitional**（接話式深掘：要貼新概念便條、
#: 2.3 禁搬動，收斂護欄「先別貼/優先搬動」對它有害；不掛任何發散/收斂護欄）。
_DIVERGENT_SUB_PHASES = frozenset((
    "0.0a",
    "1.1a", "1.1b", "1.1c", "1.1d", "1.2",
    "2.2",
))


#: Sub-phase 級別收斂 — Phase 42 C1（整理/挑選格）。
_CONVERGENT_SUB_PHASES = frozenset((
    "2.1", "2.5", "2.6", "2.7",
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

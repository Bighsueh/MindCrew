"""Timer pressure — 把 used_pct 翻成壓力等級 + 行為導向 directive。

依 specs/16-timer-system.md §6.5.1：

五階等級對應「1/2、1/3、1/4 剩餘」的直覺心理閾值：
  - `calm`        used_pct < 50
  - `halfway`     50 ≤ used_pct < 67   （一半時間了）
  - `two_thirds`  67 ≤ used_pct < 75   （剩 1/3）
  - `tight`       75 ≤ used_pct < 90   （剩 1/4）
  - `critical`    used_pct ≥ 90        （最後 sliver）

`pressure_directive(level, intent)` 回傳一句中文行為導向，給 AI agent
prompt 直接插入。為空字串時表示該組合不需特別提醒（calm 等）。
"""

from __future__ import annotations

from typing import Literal

from app.stages.phase_intent import PhaseIntent


PressureLevel = Literal["calm", "halfway", "two_thirds", "tight", "critical"]


#: (threshold, level)；由高至低排列，第一個 `used_pct >= threshold` 的回傳。
_THRESHOLDS: tuple[tuple[float, PressureLevel], ...] = (
    (90.0, "critical"),
    (75.0, "tight"),
    (67.0, "two_thirds"),
    (50.0, "halfway"),
)


_LEVEL_LABEL_ZH: dict[PressureLevel, str] = {
    "calm": "充裕",
    "halfway": "過半",
    "two_thirds": "剩 1/3",
    "tight": "剩 1/4",
    "critical": "臨界",
}


#: (壓力等級 × 階段意圖) → 給 AI agent 的行為導向中文 directive。
#: calm 不放任何條目（不需要催促時保持沉默）。
_DIRECTIVES: dict[tuple[PressureLevel, PhaseIntent], str] = {
    ("halfway", "divergent"): "一半時間了；該開始注意哪些便條紙最有潛力收斂，但仍可繼續發散。",
    ("halfway", "convergent"): "一半時間了；確認決策準則已浮現，否則先補一輪。",
    ("halfway", "transitional"): "一半時間了；確認當前任務的下一步明確。",
    ("two_thirds", "divergent"): "剩 1/3 時間；停止開新主題，把最有潛力的群挑出來。",
    ("two_thirds", "convergent"): "剩 1/3 時間；逼自己做出取捨。",
    ("two_thirds", "transitional"): "剩 1/3 時間；別再分心新議題。",
    ("tight", "divergent"): "剩 1/4 時間；本階段該收斂了——不要再寫新便條，整理現有的。",
    ("tight", "convergent"): "剩 1/4 時間；現在投票或表決，不要再辯論細節。",
    ("tight", "transitional"): "剩 1/4 時間；推進到下一步。",
    ("critical", "divergent"): "最後時間了——強制收斂，挑出 1-2 個帶走。",
    ("critical", "convergent"): "時間到——抓最有共識的選項往下走。",
    ("critical", "transitional"): "時間到——必須做出決定。",
}


def compute_pressure_level(used_pct: float) -> PressureLevel:
    """把 used_pct（0..100+）映射到五階壓力等級。"""
    if used_pct is None:
        return "calm"
    for threshold, level in _THRESHOLDS:
        if used_pct >= threshold:
            return level
    return "calm"


def pressure_directive(level: PressureLevel, intent: PhaseIntent) -> str:
    """回傳該 (壓力 × 意圖) 組合的中文行為導向；calm 或不在表內回空字串。"""
    return _DIRECTIVES.get((level, intent), "")


def get_pressure_label_zh(level: PressureLevel) -> str:
    """取得壓力等級的中文標籤。"""
    return _LEVEL_LABEL_ZH[level]

"""Supervisor A/B persona router — Spec 14.

兩支組長共用 supervisor 席位：
  - Persona A 管內容方向（POV 候選數 / criteria-before-vote / category-shift）
  - Persona B 管過程紀律（批評 / solution-language / 時間 / 同步 / 沉默）

對外只顯示「組長」，內部由 router.select_persona() 依觸發訊號決定誰發話。
仲裁原則：B 優先（程序問題 > 內容問題）。
"""

from app.agents.supervisor.router import (
    SupervisorDecision,
    SupervisorPersona,
    select_supervisor_persona,
)

__all__ = [
    "SupervisorDecision",
    "SupervisorPersona",
    "select_supervisor_persona",
]

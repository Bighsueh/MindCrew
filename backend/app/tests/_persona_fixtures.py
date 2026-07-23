"""Shared persona payloads for project-create integration tests.

Phase 21：`POST /api/projects` 接受可選 ``ai_crew_count``（預設 3，範圍 1–4），
``personas`` 數量必須等於 ``ai_crew_count``。

對既有測試保持相容：``VALID_PERSONAS_PAYLOAD`` 預設提供 ``ai_crew_count=3`` 對應的 3 位 persona。
若測試需要其他人數，可呼叫 :func:`make_personas_payload(n)`。
"""
from __future__ import annotations

_AXES = ["supportive", "balanced", "contrarian", "balanced"]


def make_personas_payload(n: int) -> list[dict]:
    """Generate ``n`` valid persona assignments covering ``crew_1..crew_n``."""
    if n < 1 or n > 4:
        raise ValueError("n must be in [1, 4]")
    return [
        {
            "seat_role": f"crew_{idx}",
            "persona": {
                "name": f"測試隊友 {idx}",
                "role": f"測試角色 {idx}",
                "expertise": "測試專長",
                "personality_axis": _AXES[idx - 1],
                "personality_desc": "務實穩健、邏輯清晰、執行力強",
                "backstory": "測試用人設",
                "lens_affinities": {
                    "empathy": 0.5,
                    "structure": 0.5,
                    "creativity": 0.5,
                    "feasibility": 0.5,
                },
            },
        }
        for idx in range(1, n + 1)
    ]


# Phase 21：預設 3 位（與 ai_crew_count 預設值一致）。
VALID_PERSONAS_PAYLOAD: list[dict] = make_personas_payload(3)


# Spec 16：建立專案時 timer_config 必填。測試共用一個 90min preset payload。
# Phase 40 (spec/16-timer-system §2.1 v1.2): 2hr/4hr preset 移除，預設改 90min。
VALID_TIMER_CONFIG: dict = {
    "total_session_minutes": 90,
    "intensity": 0.8,
    "macro_budgets": {"warmup": 4, "discover": 52, "define": 34},
    "preset_id": "timer_preset_90min",
}


__all__ = ["VALID_PERSONAS_PAYLOAD", "VALID_TIMER_CONFIG", "make_personas_payload"]

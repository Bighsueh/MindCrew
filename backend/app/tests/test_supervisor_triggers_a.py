"""#2 組長進場白重複：A1 進場宣布每個 sub_phase 只 fire 一次（dedup）+ 不漏代號。

修復前：A1 靠壞掉的 sender/字串比對判定「是否已宣布」（幾乎永遠 False），每個 tick 重講
進場白把聊天洗版。改為用共用的 _supervisor_fired_triggers（Redis，sub_phase 變更時 reset）。
另：A1 宣布改用友善階段名、不漏內部 sub_phase 代號。

純 mock（detect_a_triggers 對 1.1a 只走 A1 邏輯、不呼叫 LLM）。
"""
from __future__ import annotations

import pytest

from app.agents.supervisor.personas import TRIGGERS
from app.agents.supervisor.triggers_a import detect_a_triggers


@pytest.mark.asyncio
async def test_a1_fires_when_not_yet_announced() -> None:
    ctx = {"current_sub_phase": "1.1a", "_supervisor_fired_triggers": set()}
    ids = [tid for tid, _ in await detect_a_triggers(ctx)]
    assert "A1_phase_enter_announce" in ids


@pytest.mark.asyncio
async def test_a1_skipped_when_already_fired() -> None:
    ctx = {
        "current_sub_phase": "1.1a",
        "_supervisor_fired_triggers": {"A1_phase_enter_announce"},
    }
    ids = [tid for tid, _ in await detect_a_triggers(ctx)]
    assert "A1_phase_enter_announce" not in ids


def test_a1_announcement_uses_friendly_name_and_announce_once() -> None:
    spec = TRIGGERS["A1_phase_enter_announce"]
    # 用友善階段名宣布，不漏 raw sub_phase 代號
    assert "{sub_phase_name}" in spec.directive_template
    assert "進入 {sub_phase}" not in spec.few_shot
    assert "進入 {sub_phase}" not in spec.directive_template
    # 明確要求每階段只宣布一次
    assert "只講一次" in spec.directive_template

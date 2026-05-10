"""DEPRECATED: Replaced by the 12 Micro Phase system in v2.0.

See micro_phase_prompts.py for the replacement.
Kept for backward compatibility — assembler.py falls back to this when current_micro_phase is not set.

Original description:
Discover sub-phase logic and Supervisor-specific prompts.

Implements Kaner's Diamond of Participation model:
- EARLY: Opening / warm-up — Supervisor actively kickstarts divergence
- MID: Active discussion — Supervisor steps back, lets team diverge freely
- LATE: Approaching saturation / Groan Zone — Supervisor summarizes, checks blind spots
"""
from __future__ import annotations

from enum import Enum

# ---------------------------------------------------------------------------
# Sub-phase boundaries (constants for easy tuning)
# ---------------------------------------------------------------------------

# early → mid: notes >= _EARLY_NOTES AND chat >= _EARLY_CHAT, OR duration >= _EARLY_TIME
_EARLY_NOTES = 5
_EARLY_CHAT = 8
_EARLY_TIME_MIN = 5.0

# mid → late: notes >= _MID_NOTES AND chat >= _MID_CHAT, OR duration >= _MID_TIME
_MID_NOTES = 12
_MID_CHAT = 15
_MID_TIME_MIN = 15.0


class DiscoverSubPhase(str, Enum):
    EARLY = "early"
    MID = "mid"
    LATE = "late"


def determine_discover_subphase(
    canvas_state: dict,
    recent_chat: list[dict],
    stage_duration_minutes: float,
) -> DiscoverSubPhase:
    """Determine the current Discover sub-phase (monotonically increasing).

    Uses a hybrid approach: note count + chat count with time guards.
    Once conditions for a later phase are met, it never regresses.
    """
    total_notes = canvas_state.get("total_notes", 0)
    chat_count = len(recent_chat)

    mid_by_activity = total_notes >= _MID_NOTES and chat_count >= _MID_CHAT
    mid_by_time = stage_duration_minutes >= _MID_TIME_MIN

    if mid_by_activity or mid_by_time:
        return DiscoverSubPhase.LATE

    early_by_activity = total_notes >= _EARLY_NOTES and chat_count >= _EARLY_CHAT
    early_by_time = stage_duration_minutes >= _EARLY_TIME_MIN

    if early_by_activity or early_by_time:
        return DiscoverSubPhase.MID

    return DiscoverSubPhase.EARLY


# ---------------------------------------------------------------------------
# Supervisor-specific prompts per sub-phase
# ---------------------------------------------------------------------------

DISCOVER_SUPERVISOR_SUBPHASE_PROMPTS: dict[DiscoverSubPhase, str] = {
    DiscoverSubPhase.EARLY: (
        "目前是發散階段的前期暖身。你應該：\n"
        "- 主動提出開放性問題來啟動討論（例如：「大家想想看，使用者在什麼情境下會遇到這個問題？」）\n"
        "- 開場時為每位成員依其人設背景指派切角：\n"
        "  用 set_directive 的 respond_to 依序點名，instruction 中具體點出他/她的身分與要切的視角，例如：\n"
        "  「@{某成員}，從你照顧長輩的經驗出發，分享一個你印象最深的情境」\n"
        "  「@{某成員}，請從你業內人士的角度，談談你看到的真實限制」\n"
        "- 用「還有呢？」「其他面向呢？」追問來拓展思考方向\n"
        "- 此階段你可以更頻繁地發言來帶動氣氛\n"
        "你不應該：下結論、批評想法、歸納分群。"
    ),
    DiscoverSubPhase.MID: (
        "目前是發散階段的活躍討論期。你應該：\n"
        "- 退後一步，讓團隊自由發散，不要主導討論方向\n"
        "- 鼓勵較安靜的成員發言（「XX 你有什麼不同的想法嗎？」）\n"
        "- 當討論卡在單一面向太久時，溫和引導探索其他方向\n"
        "- 注意是否有人的觀點被忽略，適時把被忽略的觀點帶回來\n"
        "- 維護「不批評、不評價、先量後質」的規則，若有人開始評判想法要溫和制止\n"
        "你不應該：主導討論方向、過度發言、提前收斂、歸納分群。"
    ),
    DiscoverSubPhase.LATE: (
        "目前是發散階段的後期，接近飽和（Groan Zone）。你應該：\n"
        "- 摘要目前白板上的產出，讓團隊看到全貌（「目前我們討論了 X、Y、Z 幾個面向」）\n"
        "- 主動指出可能遺漏的面向（盲區挑戰）\n"
        "- 發出「最後召集」信號（「還有沒有我們沒想到的面向？」）\n"
        "- 只有在確認團隊已充分發散後，才考慮提議推進\n"
        "- 如果團隊表現出焦慮或不確定感，這是正常的 Groan Zone 現象，給予鼓勵\n"
        "你不應該：過早收斂、跳過盲區檢查、催促進度。"
    ),
}

"""Template interpolation for crew name placeholders in prompts and LLM output.

Replaces patterns like @{crew_1}, @{crew_1_name}, @{crew_name}, @{成員名稱}
with actual display names from the seats context.
"""

from __future__ import annotations

import re

from app.agents.personas.display import LEGACY_DISPLAY_NAMES as _ROLE_DISPLAY_NAMES

# Matches: @{crew_1}, @{crew_2_name}, {crew_3}, {crew_4_name}
_INDEXED_PATTERN = re.compile(r"@?\{crew_(\d+)(?:_name)?\}")

# Matches: @{crew_name}, {crew_name}
_GENERIC_CREW_PATTERN = re.compile(r"@?\{crew_name\}")

# Matches: @{crew_a}, @{crew_b}
_LETTER_PATTERN = re.compile(r"@?\{crew_([a-z])\}")

# Matches: @{成員名稱}, {成員名稱}
_CN_PATTERN = re.compile(r"@?\{成員名稱\}")

# Matches bare: crew_1, crew_2 (without braces, as standalone word)
_BARE_PATTERN = re.compile(r"\bcrew_(\d+)\b")

# Phase 42 B2（守則 6 支撐，#15）：真人顯示名插值。
# Matches: @{name}, {name}, @{顯示名}, {顯示名} —— 不含「{對方顯示名}」（守則 6 的教學佔位符）。
_HUMAN_PLACEHOLDER_PATTERN = re.compile(r"@?\{(?:name|顯示名)\}")

# Matches bare/at-prefixed seat id: human_creator, @human_creator。
# 不用 \b——Python 的 \w 含 CJK，「請human_creator回應」這種無空格中文相鄰會漏抓；
# 改用 ASCII-only lookaround。
_HUMAN_SEAT_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9_])@?human_creator(?![A-Za-z0-9_])")


def interpolate_crew_names(
    text: str,
    seats: list[dict] | None = None,
) -> str:
    """Replace crew placeholder patterns with actual display names.

    Args:
        text: The text containing placeholders.
        seats: List of seat dicts with 'role' and 'display_name' keys.
               Falls back to default display names if not provided.
    """
    if not text:
        return text

    # Build role → display_name mapping from seats.
    # Phase 19: persona.name in seat takes precedence over legacy defaults.
    name_map: dict[str, str] = dict(_ROLE_DISPLAY_NAMES)
    if seats:
        for s in seats:
            role = s.get("role") or s.get("seat_role", "")
            persona = s.get("persona")
            persona_name = ""
            if isinstance(persona, dict):
                persona_name = str(persona.get("name", "")).strip()
            dn = persona_name or s.get("display_name") or s.get("agent_name", "")
            if role and dn:
                name_map[role] = dn

    # @{crew_1} → "AI 同理心專家"
    def _replace_indexed(m: re.Match) -> str:
        idx = m.group(1)
        role_key = f"crew_{idx}"
        return name_map.get(role_key, f"crew_{idx}")

    text = _INDEXED_PATTERN.sub(_replace_indexed, text)

    # @{crew_name} → generic placeholder (use first crew name)
    first_crew = name_map.get("crew_1", "組員")
    # callable repl：persona 名含反斜線時避免 re.sub 模板跳脫解析（B2 加固）。
    _first_crew_repl = lambda _m: first_crew  # noqa: E731
    text = _GENERIC_CREW_PATTERN.sub(_first_crew_repl, text)

    # @{crew_a}, @{crew_b} → crew_1, crew_2
    _letter_to_idx = {"a": "1", "b": "2", "c": "3", "d": "4"}

    def _replace_letter(m: re.Match) -> str:
        letter = m.group(1)
        idx = _letter_to_idx.get(letter, "1")
        return name_map.get(f"crew_{idx}", f"crew_{letter}")

    text = _LETTER_PATTERN.sub(_replace_letter, text)

    # @{成員名稱} → generic
    text = _CN_PATTERN.sub(_first_crew_repl, text)

    # Bare crew_1, crew_2 etc. (without braces) → display names
    text = _BARE_PATTERN.sub(_replace_indexed, text)

    return text


def find_human_display_name(seats: list[dict] | None) -> str:
    """Return the display name of the (single) human participant, or ""。

    真人席的名字存在 ``user_name``（context_buffer 對 human 席不設 display_name），
    這裡做 display_name → user_name → agent_name 的 fallback 鏈。
    """
    if not seats:
        return ""
    for s in seats:
        role = s.get("role") or s.get("seat_role") or ""
        if s.get("type") == "human" or s.get("occupant_type") == "human" or role == "human_creator":
            dn = s.get("display_name") or s.get("user_name") or s.get("agent_name") or ""
            if dn:
                return str(dn)
    return ""


def interpolate_human_name(
    text: str,
    seats: list[dict] | None = None,
    *,
    include_bare_seat_id: bool = False,
) -> str:
    """Replace human placeholder patterns with the human's display name（守則 6，#15）。

    - ``@{name}`` / ``@{顯示名}``：邀請真人 fragment 與守則 8 的佔位符 → 真人顯示名。
    - ``include_bare_seat_id=True`` 時連 ``human_creator`` / ``@human_creator`` 也改寫——
      僅用於**出站訊息**安全網（學員不該看到 seat id）；system prompt 不可開啟，
      否則會破壞 invited_speaker=<seat_role> 的機器路由教學。

    找不到真人席（全 AI 房）時，佔位符**降級替換為「大家」**——LLM 照抄 few-shot
    時字面「@{顯示名}」不得進聊天記錄（Phase 42 補正 R2／稽核 §4.2；修復前原文
    返回＝佔位符直接外漏）。
    """
    if not text:
        return text
    human_name = find_human_display_name(seats)
    if not human_name:
        text = _HUMAN_PLACEHOLDER_PATTERN.sub("大家", text)
        if include_bare_seat_id:
            text = _HUMAN_SEAT_ID_PATTERN.sub("大家", text)
        return text

    # repl 用 callable：display name 是使用者註冊輸入，含反斜線時字串模板會
    # 觸發 re.sub 跳脫解析（\g<0> 展開／結尾 \ 直接 re.error）。
    _repl = lambda _m: f"@{human_name}"  # noqa: E731
    text = _HUMAN_PLACEHOLDER_PATTERN.sub(_repl, text)
    if include_bare_seat_id:
        text = _HUMAN_SEAT_ID_PATTERN.sub(_repl, text)
    return text

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
    text = _GENERIC_CREW_PATTERN.sub(first_crew, text)

    # @{crew_a}, @{crew_b} → crew_1, crew_2
    _letter_to_idx = {"a": "1", "b": "2", "c": "3", "d": "4"}

    def _replace_letter(m: re.Match) -> str:
        letter = m.group(1)
        idx = _letter_to_idx.get(letter, "1")
        return name_map.get(f"crew_{idx}", f"crew_{letter}")

    text = _LETTER_PATTERN.sub(_replace_letter, text)

    # @{成員名稱} → generic
    text = _CN_PATTERN.sub(first_crew, text)

    # Bare crew_1, crew_2 etc. (without braces) → display names
    text = _BARE_PATTERN.sub(_replace_indexed, text)

    return text

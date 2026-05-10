"""Unit tests for the Phase 19 dynamic persona system."""
from __future__ import annotations

import pytest

from app.agents.personas import (
    CognitiveLens,
    LensAffinities,
    Persona,
    PersonalityAxis,
    build_fallback_personas,
    persona_from_dict,
    persona_to_dict,
    resolve_protagonist_seat,
    resolve_suppressed_seats,
)


# ---------------------------------------------------------------------------
# LensAffinities clamping & dict round-trip
# ---------------------------------------------------------------------------


def test_lens_affinities_clamps_to_unit_range() -> None:
    aff = LensAffinities.from_dict(
        {"empathy": 1.5, "structure": -0.2, "creativity": 0.7, "feasibility": "0.3"}
    )
    assert aff.empathy == 1.0
    assert aff.structure == 0.0
    assert aff.creativity == 0.7
    assert aff.feasibility == 0.3


def test_lens_affinities_default_when_missing() -> None:
    aff = LensAffinities.from_dict(None)
    assert aff.empathy == aff.structure == aff.creativity == aff.feasibility == 0.5


# ---------------------------------------------------------------------------
# Persona serialization round-trip
# ---------------------------------------------------------------------------


def _sample_persona() -> Persona:
    return Persona(
        name="陳秀英",
        role="偏鄉家醫科診所護理師",
        expertise="慢性病管理、長者衛教、社區外展",
        personality_axis=PersonalityAxis.SUPPORTIVE,
        personality_desc="總是把焦點拉回病人本身",
        backstory="返鄉服務 12 年，熟悉長者真實處境",
        lens_affinities=LensAffinities(0.9, 0.4, 0.3, 0.5),
    )


def test_persona_to_dict_includes_all_fields() -> None:
    persona = _sample_persona()
    payload = persona_to_dict(persona)
    assert payload["name"] == "陳秀英"
    assert payload["personality_axis"] == "supportive"
    assert payload["lens_affinities"]["empathy"] == 0.9


def test_persona_from_dict_round_trip() -> None:
    persona = _sample_persona()
    payload = persona_to_dict(persona)
    restored = persona_from_dict(payload)
    assert restored is not None
    assert restored == persona


def test_persona_from_dict_rejects_invalid() -> None:
    assert persona_from_dict({}) is None
    assert persona_from_dict({"name": "", "role": "X"}) is None
    assert persona_from_dict(None) is None


def test_persona_dominant_lens_picks_max() -> None:
    persona = _sample_persona()
    assert persona.dominant_lens() == CognitiveLens.EMPATHY


# ---------------------------------------------------------------------------
# Fallback personas (legacy behaviour)
# ---------------------------------------------------------------------------


def test_fallback_personas_present_for_all_crew() -> None:
    fallbacks = build_fallback_personas()
    assert set(fallbacks.keys()) == {"crew_1", "crew_2", "crew_3", "crew_4"}


def test_fallback_dominant_lens_matches_legacy_mapping() -> None:
    fallbacks = build_fallback_personas()
    assert fallbacks["crew_1"].dominant_lens() == CognitiveLens.EMPATHY
    assert fallbacks["crew_2"].dominant_lens() == CognitiveLens.STRUCTURE
    assert fallbacks["crew_3"].dominant_lens() == CognitiveLens.CREATIVITY
    assert fallbacks["crew_4"].dominant_lens() == CognitiveLens.FEASIBILITY


# ---------------------------------------------------------------------------
# Resolver behaviour
# ---------------------------------------------------------------------------


def _seat(seat_role: str, persona: Persona | None, occupant: str = "ai") -> dict:
    return {
        "seat_role": seat_role,
        "occupant_type": occupant,
        "persona": persona_to_dict(persona) if persona else None,
    }


def test_resolver_picks_highest_affinity_for_lens() -> None:
    seats = [
        _seat("supervisor", None),
        _seat(
            "crew_1",
            Persona(
                name="A",
                role="A role",
                expertise="...",
                lens_affinities=LensAffinities(0.2, 0.9, 0.2, 0.2),
            ),
        ),
        _seat(
            "crew_2",
            Persona(
                name="B",
                role="B role",
                expertise="...",
                lens_affinities=LensAffinities(0.9, 0.2, 0.2, 0.2),
            ),
        ),
    ]
    assert resolve_protagonist_seat(seats, CognitiveLens.EMPATHY) == "crew_2"
    assert resolve_protagonist_seat(seats, CognitiveLens.STRUCTURE) == "crew_1"


def test_resolver_ignores_human_seats() -> None:
    seats = [
        _seat(
            "crew_1",
            Persona(
                name="A",
                role="A role",
                expertise="...",
                lens_affinities=LensAffinities(0.9, 0.0, 0.0, 0.0),
            ),
            occupant="human",
        ),
        _seat(
            "crew_2",
            Persona(
                name="B",
                role="B role",
                expertise="...",
                lens_affinities=LensAffinities(0.5, 0.0, 0.0, 0.0),
            ),
        ),
    ]
    # crew_1 is human → resolver should pick crew_2 despite lower score
    assert resolve_protagonist_seat(seats, CognitiveLens.EMPATHY) == "crew_2"


def test_resolver_returns_none_for_no_lens() -> None:
    seats = [
        _seat(
            "crew_1",
            Persona(
                name="A",
                role="A role",
                expertise="...",
                lens_affinities=LensAffinities(),
            ),
        ),
    ]
    assert resolve_protagonist_seat(seats, None) is None


def test_resolve_suppressed_excludes_protagonist() -> None:
    seats = [
        _seat(
            "crew_1",
            Persona(
                name="A",
                role="A role",
                expertise="...",
                lens_affinities=LensAffinities(0.0, 0.9, 0.0, 0.0),
            ),
        ),
        _seat(
            "crew_2",
            Persona(
                name="B",
                role="B role",
                expertise="...",
                lens_affinities=LensAffinities(0.0, 0.8, 0.0, 0.0),
            ),
        ),
    ]
    suppressed = resolve_suppressed_seats(
        seats,
        [CognitiveLens.STRUCTURE],
        protect_seat="crew_1",
    )
    assert "crew_1" not in suppressed
    assert "crew_2" in suppressed


# ---------------------------------------------------------------------------
# Phase 19 integration with micro_phases.get_role_status (with seats)
# ---------------------------------------------------------------------------


def test_get_role_status_with_custom_personas() -> None:
    """A dramatically different persona layout still produces sensible roles."""
    from app.stages.micro_phases import get_role_status

    # 4 personas all biased toward creativity except one toward empathy on seat_4
    seats = [
        _seat("supervisor", None),
        _seat(
            "crew_1",
            Persona(
                name="P1",
                role="r",
                expertise="e",
                lens_affinities=LensAffinities(0.2, 0.2, 0.9, 0.2),
            ),
        ),
        _seat(
            "crew_2",
            Persona(
                name="P2",
                role="r",
                expertise="e",
                lens_affinities=LensAffinities(0.2, 0.2, 0.85, 0.2),
            ),
        ),
        _seat(
            "crew_3",
            Persona(
                name="P3",
                role="r",
                expertise="e",
                lens_affinities=LensAffinities(0.2, 0.2, 0.95, 0.2),
            ),
        ),
        _seat(
            "crew_4",
            Persona(
                name="P4",
                role="r",
                expertise="e",
                lens_affinities=LensAffinities(0.9, 0.2, 0.2, 0.2),
            ),
        ),
    ]
    # Phase 1.1 needs empathy → crew_4 should be protagonist
    assert get_role_status("1.1", "crew_4", seats=seats) == "protagonist"
    # Phase 3.1 needs creativity → highest creativity is crew_3
    assert get_role_status("3.1", "crew_3", seats=seats) == "protagonist"


# ---------------------------------------------------------------------------
# render_persona_prompt produces non-empty output for valid input
# ---------------------------------------------------------------------------


def test_render_persona_prompt_returns_prompt() -> None:
    from app.agents.prompts.roles import render_persona_prompt

    payload = persona_to_dict(_sample_persona())
    prompt = render_persona_prompt(payload)
    assert "陳秀英" in prompt
    assert "護理師" in prompt
    assert "empathy" in prompt.lower() or "同理心" in prompt


def test_render_persona_prompt_returns_empty_for_invalid() -> None:
    from app.agents.prompts.roles import render_persona_prompt

    assert render_persona_prompt(None) == ""
    assert render_persona_prompt({}) == ""


# ---------------------------------------------------------------------------
# Display name resolution
# ---------------------------------------------------------------------------


def test_resolve_display_name_prefers_persona() -> None:
    from app.agents.personas.display import resolve_display_name

    payload = persona_to_dict(_sample_persona())
    assert resolve_display_name("crew_1", payload) == "陳秀英"


def test_resolve_display_name_falls_back_to_legacy() -> None:
    from app.agents.personas.display import resolve_display_name

    assert resolve_display_name("crew_1", None) == "AI 同理心專家"
    assert resolve_display_name("supervisor", None) == "AI 引導者"
    assert resolve_display_name("crew_9", None) == "AI crew_9"


# ---------------------------------------------------------------------------
# Persona payload validation via Pydantic schema
# ---------------------------------------------------------------------------


def test_persona_payload_clamps_lens_affinities() -> None:
    from app.projects.schemas import PersonaPayload

    payload = PersonaPayload(
        name="A",
        role="B",
        expertise="C",
        lens_affinities={  # type: ignore[arg-type]
            "empathy": 1.5,
            "structure": -0.5,
            "creativity": 0.5,
            "feasibility": 0.6,
        },
    )
    assert payload.lens_affinities.empathy == 1.0
    assert payload.lens_affinities.structure == 0.0


def test_persona_payload_normalises_personality_axis() -> None:
    from app.projects.schemas import PersonaPayload

    payload = PersonaPayload(
        name="A", role="B", expertise="C", personality_axis="invalid"
    )
    assert payload.personality_axis == "balanced"

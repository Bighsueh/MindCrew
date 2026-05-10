"""Dynamic AI Persona system (Phase 19).

Replaces the hardcoded crew_1=empathy / crew_2=structure / crew_3=creativity /
crew_4=feasibility mapping with project-specific personas tagged by
cognitive lens affinities. See ``models.py`` for data structures and
``lens.py`` for the lens taxonomy used by phase strategy.
"""

from app.agents.personas.lens import (
    CognitiveLens,
    LENS_VALUES,
    coerce_lens,
)
from app.agents.personas.models import (
    LensAffinities,
    Persona,
    PersonalityAxis,
    build_fallback_personas,
    persona_from_dict,
    persona_to_dict,
)
from app.agents.personas.resolver import (
    dominant_lens,
    resolve_protagonist_seat,
    resolve_suppressed_seats,
)

__all__ = [
    "CognitiveLens",
    "LENS_VALUES",
    "coerce_lens",
    "LensAffinities",
    "Persona",
    "PersonalityAxis",
    "build_fallback_personas",
    "persona_from_dict",
    "persona_to_dict",
    "dominant_lens",
    "resolve_protagonist_seat",
    "resolve_suppressed_seats",
]

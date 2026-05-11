"""Two-stage PersonaGenerator using the configured LLM provider.

Stage 1: stakeholder mapping → list of categories
Stage 2: persona instantiation → list of concrete personas

Both stages emit strict JSON. Outputs are run through OpenCC s2twp so
mainland-style characters never leak into UI.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.personas.lens import LENS_VALUES
from app.agents.personas.meta_prompt import (
    STAKEHOLDER_MAPPING_SYSTEM_PROMPT,
    build_persona_system_prompt,
    build_persona_user_prompt,
    build_stakeholder_user_prompt,
)
from app.agents.personas.models import (
    LensAffinities,
    Persona,
    PersonalityAxis,
    persona_from_dict,
)
from app.chinese.converter import chinese_converter
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json

logger = logging.getLogger(__name__)


class PersonaGenerationError(RuntimeError):
    """Raised when the LLM repeatedly fails to produce a valid persona list."""


class PersonaGenerator:
    """Two-stage LLM workflow for generating cross-domain DT personas."""

    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm = llm_service or LLMProviderFactory.get_service()

    async def generate(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        num_personas: int = 4,
    ) -> list[Persona]:
        """Generate ``num_personas`` cross-domain Design Thinking personas.

        Raises ``PersonaGenerationError`` if the LLM output cannot be
        parsed into at least one valid persona after both stages.
        """
        if num_personas <= 0:
            raise ValueError("num_personas must be positive")
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")

        categories_json = await self._run_stakeholder_mapping(
            title=title,
            description=description,
            constraints=constraints,
        )
        personas = await self._run_persona_instantiation(
            title=title,
            description=description,
            constraints=constraints,
            categories_json=categories_json,
            num_personas=num_personas,
        )
        if not personas:
            raise PersonaGenerationError(
                "PersonaGenerator produced zero valid personas"
            )
        return personas[:num_personas]

    # ------------------------------------------------------------------
    # Stage 1: stakeholder mapping
    # ------------------------------------------------------------------

    async def _run_stakeholder_mapping(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
    ) -> str:
        messages = [
            {"role": "system", "content": STAKEHOLDER_MAPPING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_stakeholder_user_prompt(
                    title=title,
                    description=description,
                    constraints=constraints,
                ),
            },
        ]
        try:
            response = await self._llm.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.warning("Stakeholder mapping LLM call failed: %s", exc)
            return "{\"categories\": []}"
        parsed = parse_llm_json(response.content) or {}
        categories = parsed.get("categories") if isinstance(parsed, dict) else None
        if not isinstance(categories, list) or not categories:
            logger.info(
                "Stakeholder mapping returned no usable categories; "
                "falling back to empty list."
            )
            return "{\"categories\": []}"
        # Re-serialize so stage 2 sees a clean, compact form.
        return json.dumps(
            {"categories": categories}, ensure_ascii=False, indent=2
        )

    # ------------------------------------------------------------------
    # Stage 2: persona instantiation
    # ------------------------------------------------------------------

    async def _run_persona_instantiation(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        categories_json: str,
        num_personas: int,
    ) -> list[Persona]:
        system_prompt = build_persona_system_prompt(num_personas)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": build_persona_user_prompt(
                    title=title,
                    description=description,
                    constraints=constraints,
                    categories_json=categories_json,
                    num_personas=num_personas,
                ),
            },
        ]
        response = await self._llm.chat_completion(
            messages=messages,
            temperature=0.8,
            max_tokens=2048,
        )
        parsed = parse_llm_json(response.content) or {}
        raw_personas = parsed.get("personas") if isinstance(parsed, dict) else None
        if not isinstance(raw_personas, list):
            raise PersonaGenerationError(
                "LLM response did not contain a 'personas' array"
            )
        results: list[Persona] = []
        for entry in raw_personas:
            if not isinstance(entry, dict):
                continue
            persona = self._normalize_persona_dict(entry)
            if persona is not None:
                results.append(persona)
        return results

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_persona_dict(data: dict[str, Any]) -> Persona | None:
        """Repair common LLM output drift and convert to Persona."""
        cleaned: dict[str, Any] = {}
        cleaned["name"] = chinese_converter.convert(str(data.get("name", "")).strip())
        cleaned["role"] = chinese_converter.convert(str(data.get("role", "")).strip())
        cleaned["expertise"] = chinese_converter.convert(
            str(data.get("expertise", "")).strip()
        )
        cleaned["personality_desc"] = chinese_converter.convert(
            str(data.get("personality_desc", "")).strip()
        )
        cleaned["backstory"] = chinese_converter.convert(
            str(data.get("backstory", "")).strip()
        )

        axis_raw = str(data.get("personality_axis", "balanced")).strip().lower()
        try:
            PersonalityAxis(axis_raw)
        except ValueError:
            axis_raw = PersonalityAxis.BALANCED.value
        cleaned["personality_axis"] = axis_raw

        affinities_raw = data.get("lens_affinities") or {}
        if isinstance(affinities_raw, dict):
            normalized_affinities: dict[str, float] = {}
            for lens in LENS_VALUES:
                value = affinities_raw.get(lens, 0.5)
                try:
                    normalized_affinities[lens] = max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    normalized_affinities[lens] = 0.5
            cleaned["lens_affinities"] = normalized_affinities
        else:
            cleaned["lens_affinities"] = LensAffinities().as_dict()

        return persona_from_dict(cleaned)


__all__ = ["PersonaGenerator", "PersonaGenerationError"]

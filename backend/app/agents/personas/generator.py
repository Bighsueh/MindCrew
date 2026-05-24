"""Two-stage PersonaGenerator using the configured LLM provider.

Stage 1: stakeholder mapping → list of categories
Stage 2: persona instantiation → list of concrete personas

Both stages emit strict JSON. Outputs are run through OpenCC s2twp so
mainland-style characters never leak into UI.

``generate_stream`` exposes the same two-stage pipeline as an async event
stream — see `specs/17-dynamic-persona-system.md` §3.1.2 for the wire-level
SSE protocol that wraps these events at the HTTP layer.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID
from typing import Any, AsyncIterator

from uuid import uuid4

from app.agents.personas.lens import LENS_VALUES
from app.agents.personas.meta_prompt import (
    STAKEHOLDER_MAPPING_SYSTEM_PROMPT,
    STAKEHOLDER_SUGGESTION_SYSTEM_PROMPT,
    build_persona_system_prompt,
    build_persona_user_prompt,
    build_persona_user_prompt_from_stakeholders,
    build_stakeholder_suggestion_user_prompt,
    build_stakeholder_user_prompt,
)
from app.agents.personas.models import (
    LensAffinities,
    Persona,
    PersonalityAxis,
    StakeholderSuggestion,
    persona_from_dict,
    persona_to_dict,
    stakeholder_suggestion_from_dict,
    stakeholder_suggestion_to_dict,
)
from app.chinese.converter import chinese_converter
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json
from app.llm.streaming_json import JsonArrayObjectExtractor

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
        owning_user_id: UUID,
        stakeholders: list[StakeholderSuggestion] | None = None,
    ) -> list[Persona]:
        """Generate ``num_personas`` cross-domain Design Thinking personas.

        If ``stakeholders`` is provided (Phase 27 two-stage flow), Stage 1
        is skipped and personas are instantiated directly from the
        user-picked stakeholders. Otherwise the legacy v1.x behavior runs
        Stage 1 internally.

        Raises ``PersonaGenerationError`` if the LLM output cannot be
        parsed into at least one valid persona after both stages.
        """
        if num_personas <= 0:
            raise ValueError("num_personas must be positive")
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")

        # Phase 27：semantic distinction —
        #   stakeholders=None  → Stage 1 自行 mapping（v1.x 相容）
        #   stakeholders=[...] → 跳過 Stage 1，使用 caller 預先決定的清單
        #   stakeholders=[]    → 顯式錯誤（caller 矛盾意圖）
        if stakeholders is not None and len(stakeholders) == 0:
            raise ValueError(
                "stakeholders=[] is ambiguous; pass None to auto-map or provide "
                "≥1 picked stakeholder"
            )
        if stakeholders is not None:
            personas = await self._run_persona_from_stakeholders(
                title=title,
                description=description,
                constraints=constraints,
                stakeholders=stakeholders,
                num_personas=num_personas,
                owning_user_id=owning_user_id,
            )
        else:
            categories_json = await self._run_stakeholder_mapping(
                title=title,
                description=description,
                constraints=constraints,
                owning_user_id=owning_user_id,
            )
            personas = await self._run_persona_instantiation(
                title=title,
                description=description,
                constraints=constraints,
                categories_json=categories_json,
                num_personas=num_personas,
                owning_user_id=owning_user_id,
            )
        if not personas:
            raise PersonaGenerationError(
                "PersonaGenerator produced zero valid personas"
            )
        return personas[:num_personas]

    # ------------------------------------------------------------------
    # Phase 27: Stakeholder suggestion (concrete people, user picks N)
    # ------------------------------------------------------------------

    async def suggest_stakeholders(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        owning_user_id: UUID,
        count_min: int = 6,
        count_max: int = 10,
        existing_names: list[str] | None = None,
    ) -> list[StakeholderSuggestion]:
        """Return 6–10 concrete potential stakeholders for the user to pick from.

        See ``specs/17-dynamic-persona-system.md`` §3.0.1.
        Raises ``PersonaGenerationError`` if LLM produces no usable suggestions.
        """
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")
        messages = [
            {"role": "system", "content": STAKEHOLDER_SUGGESTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_stakeholder_suggestion_user_prompt(
                    title=title,
                    description=description,
                    constraints=constraints,
                    existing_names=existing_names,
                ),
            },
        ]
        try:
            response = await self._llm.chat_completion(
                messages=messages,
                temperature=0.8,
                max_tokens=1500,
                caller="stakeholder_suggestion",
                owning_user_id=owning_user_id,
            )
        except Exception as exc:
            logger.warning("Stakeholder suggestion LLM call failed: %s", exc)
            raise PersonaGenerationError(
                f"Stakeholder suggestion failed: {exc}"
            ) from exc

        parsed = parse_llm_json(response.content) or {}
        raw = parsed.get("suggestions") if isinstance(parsed, dict) else None
        if not isinstance(raw, list) or not raw:
            raise PersonaGenerationError(
                "LLM did not return a 'suggestions' array"
            )

        results: list[StakeholderSuggestion] = []
        seen_keys: set[str] = set()
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = chinese_converter.convert(str(entry.get("name", "")).strip())
            role = chinese_converter.convert(str(entry.get("role", "")).strip())
            relevance = chinese_converter.convert(
                str(entry.get("relevance", "")).strip()
            )
            if not name or not role:
                continue
            dedupe_key = f"{name}|{role}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            results.append(
                StakeholderSuggestion(
                    id=str(uuid4()),
                    name=name,
                    role=role,
                    relevance=relevance,
                )
            )
            if len(results) >= count_max:
                break

        # Spec §3.0.1 mandates 6–10. Tolerate -1 (5) for LLM jitter; fewer is
        # a failure so caller can retry rather than silently accept a thin list.
        lower_bound = max(1, count_min - 1)
        if len(results) < lower_bound:
            raise PersonaGenerationError(
                f"Stakeholder suggestion produced too few items "
                f"({len(results)} < {lower_bound}; spec floor {count_min})"
            )
        return results

    # ------------------------------------------------------------------
    # Streaming pipeline (Phase 19, 2026-05-11)
    # ------------------------------------------------------------------

    async def generate_stream(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        num_personas: int = 4,
        owning_user_id: UUID,
        stakeholders: list[StakeholderSuggestion] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield event dicts as the two-stage pipeline progresses.

        Event types (see ``specs/17-dynamic-persona-system.md`` §3.1.2):

        - ``{"type": "stage", "stage": "stakeholder_mapping", "status": "start"}``
        - ``{"type": "stage", "stage": "stakeholder_mapping", "status": "done", "category_count": int}``
        - ``{"type": "stage", "stage": "persona_instantiation", "status": "start"}``
        - ``{"type": "persona", "index": int, "persona": dict}``
        - ``{"type": "done", "count": int}``
        - ``{"type": "error", "detail": str}`` — terminal; no further events

        The caller (HTTP SSE router) is responsible for translating each event
        into a ``text/event-stream`` frame.
        """
        if num_personas <= 0:
            yield {"type": "error", "detail": "num_personas must be positive"}
            return
        title = (title or "").strip()
        if not title:
            yield {"type": "error", "detail": "title is required"}
            return

        # Stage 1 — stakeholder mapping
        # Phase 27: when caller supplies pre-picked stakeholders, skip the LLM
        # call but still emit the stage events so the SSE protocol stays stable.
        yield {
            "type": "stage",
            "stage": "stakeholder_mapping",
            "status": "start",
        }
        stakeholders_json: str | None = None
        if stakeholders:
            stakeholders_json = json.dumps(
                {
                    "stakeholders": [
                        stakeholder_suggestion_to_dict(s) for s in stakeholders
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            category_count = len(stakeholders)
            categories_json = "{\"categories\": []}"  # unused in this branch
        else:
            try:
                categories_json = await self._run_stakeholder_mapping(
                    title=title,
                    description=description,
                    constraints=constraints,
                    owning_user_id=owning_user_id,
                )
            except Exception as exc:  # network/timeout, etc.
                logger.warning("Streaming stakeholder mapping failed: %s", exc)
                categories_json = "{\"categories\": []}"
            try:
                parsed = json.loads(categories_json)
                category_count = len(parsed.get("categories") or [])
            except (TypeError, ValueError, json.JSONDecodeError):
                category_count = 0
        yield {
            "type": "stage",
            "stage": "stakeholder_mapping",
            "status": "done",
            "category_count": category_count,
        }

        # Stage 2 — persona instantiation (streamed)
        yield {
            "type": "stage",
            "stage": "persona_instantiation",
            "status": "start",
        }
        emitted = 0
        try:
            async for persona_payload in self._stream_persona_objects(
                title=title,
                description=description,
                constraints=constraints,
                categories_json=categories_json,
                num_personas=num_personas,
                owning_user_id=owning_user_id,
                stakeholders_json=stakeholders_json,
            ):
                yield {
                    "type": "persona",
                    "index": emitted,
                    "persona": persona_payload,
                }
                emitted += 1
                if emitted >= num_personas:
                    break
        except asyncio.TimeoutError:
            yield {"type": "error", "detail": "LLM 串流超時，請稍後再試。"}
            return
        except Exception as exc:  # noqa: BLE001 — surface to client
            logger.exception("Streaming persona instantiation failed")
            yield {
                "type": "error",
                "detail": f"AI 人設生成失敗：{exc}",
            }
            return

        if emitted == 0:
            yield {"type": "error", "detail": "AI 未能生成任何人設，請稍後再試。"}
            return

        yield {"type": "done", "count": emitted}

    async def _stream_persona_objects(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        categories_json: str,
        num_personas: int,
        owning_user_id: UUID,
        stakeholders_json: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream stage-2 LLM output, yielding each persona payload as it closes."""
        system_prompt = build_persona_system_prompt(num_personas)
        if stakeholders_json is not None:
            user_msg = build_persona_user_prompt_from_stakeholders(
                title=title,
                description=description,
                constraints=constraints,
                stakeholders_json=stakeholders_json,
                num_personas=num_personas,
            )
        else:
            user_msg = build_persona_user_prompt(
                title=title,
                description=description,
                constraints=constraints,
                categories_json=categories_json,
                num_personas=num_personas,
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        extractor = JsonArrayObjectExtractor()
        any_yielded = False
        async for delta in self._llm.chat_completion_stream(
            messages=messages,
            temperature=0.8,
            max_tokens=2048,
            owning_user_id=owning_user_id,
            caller="persona_stream",
        ):
            for raw_obj in extractor.feed(delta):
                persona = self._normalize_persona_dict(raw_obj)
                if persona is None:
                    continue
                any_yielded = True
                yield persona_to_dict(persona)

        # Final pass: if streaming finished without yielding any object (e.g.
        # the model emitted a single closing chunk after our scan), fall back
        # to whole-buffer parse so callers still see something.
        if not any_yielded:
            parsed = parse_llm_json(extractor.full_buffer) or {}
            for entry in parsed.get("personas", []) or []:
                if not isinstance(entry, dict):
                    continue
                persona = self._normalize_persona_dict(entry)
                if persona is not None:
                    yield persona_to_dict(persona)

    # ------------------------------------------------------------------
    # Stage 1: stakeholder mapping
    # ------------------------------------------------------------------

    async def _run_stakeholder_mapping(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        owning_user_id: UUID,
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
                caller="persona_stakeholders",
                owning_user_id=owning_user_id,
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
        owning_user_id: UUID,
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
            caller="persona_generation",
            owning_user_id=owning_user_id,
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
    # Phase 27: Stage 2 driven by user-picked stakeholders
    # ------------------------------------------------------------------

    async def _run_persona_from_stakeholders(
        self,
        *,
        title: str,
        description: str | None,
        constraints: str | None,
        stakeholders: list[StakeholderSuggestion],
        num_personas: int,
        owning_user_id: UUID,
    ) -> list[Persona]:
        stakeholders_json = json.dumps(
            {
                "stakeholders": [
                    stakeholder_suggestion_to_dict(s) for s in stakeholders
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        system_prompt = build_persona_system_prompt(num_personas)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": build_persona_user_prompt_from_stakeholders(
                    title=title,
                    description=description,
                    constraints=constraints,
                    stakeholders_json=stakeholders_json,
                    num_personas=num_personas,
                ),
            },
        ]
        response = await self._llm.chat_completion(
            messages=messages,
            temperature=0.8,
            max_tokens=2048,
            caller="persona_from_stakeholders",
            owning_user_id=owning_user_id,
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


__all__ = ["PersonaGenerator", "PersonaGenerationError", "StakeholderSuggestion"]

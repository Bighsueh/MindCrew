"""Robust JSON parsing utilities for LLM responses.

Handles common LLM output issues:
- Markdown code fences (```json ... ```)
- Preamble text before JSON
- Truncated JSON (missing closing brackets)
- Empty responses
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> dict | None:
    """Parse JSON from an LLM response, with multiple fallback strategies.

    Returns the parsed dict, or None if all strategies fail.
    """
    if not raw or not raw.strip():
        logger.warning("LLM returned empty response")
        return None

    raw = raw.strip()

    # Strategy 1: Strip code fences (```json, ```JSON, ```)
    cleaned = _strip_code_fences(raw)
    result = _try_parse(cleaned)
    if result is not None:
        return result

    # Strategy 2: Regex extract outermost { ... }
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        result = _try_parse(match.group())
        if result is not None:
            return result

        # Strategy 3: Repair truncated JSON (matched with closing brace)
        repaired = _repair_truncated_json(match.group())
        result = _try_parse(repaired)
        if result is not None:
            logger.info("JSON recovered via truncation repair")
            return result

    # Strategy 4: No closing brace at all — find first { and try repair
    brace_idx = cleaned.find("{")
    if brace_idx >= 0:
        fragment = cleaned[brace_idx:]
        repaired = _repair_truncated_json(fragment)
        result = _try_parse(repaired)
        if result is not None:
            logger.info("JSON recovered from truncated fragment (no closing brace)")
            return result

    logger.warning("All JSON parse strategies failed | raw=%r", raw[:300])
    return None


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences, including language tags like ```json."""
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    # Skip the opening fence line (may contain language tag)
    inner = []
    for line in lines[1:]:
        if line.strip().startswith("```"):
            continue
        inner.append(line)
    return "\n".join(inner).strip()


def _try_parse(s: str) -> dict | None:
    """Attempt json.loads, return None on failure."""
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _repair_truncated_json(s: str) -> str:
    """Attempt to fix JSON truncated mid-stream by closing open brackets.

    Handles the common case where max_tokens cuts off the response.
    Strategy: find the last position where adding closing brackets yields valid JSON.
    """
    # Try progressively shorter prefixes, cutting at commas or bracket boundaries
    candidates = []
    for marker in (",", "}", "]"):
        idx = s.rfind(marker)
        while idx > 0:
            prefix = s[: idx + 1].rstrip(",")
            open_braces = prefix.count("{") - prefix.count("}")
            open_brackets = prefix.count("[") - prefix.count("]")
            attempt = prefix + "]" * max(0, open_brackets) + "}" * max(0, open_braces)
            candidates.append(attempt)
            idx = s.rfind(marker, 0, idx)
            if len(candidates) > 10:
                break

    # Also try just closing the original string as-is
    open_braces = s.count("{") - s.count("}")
    open_brackets = s.count("[") - s.count("]")
    candidates.append(s + "]" * max(0, open_brackets) + "}" * max(0, open_braces))

    # Return the first candidate that parses successfully (longest first for maximum data)
    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue

    # Nothing worked — return the naive bracket-close attempt
    return s + "]" * max(0, open_brackets) + "}" * max(0, open_braces)

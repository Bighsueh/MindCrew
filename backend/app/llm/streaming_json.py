"""Incremental JSON-array-of-objects extractor for streaming LLM output.

Phase 19 (Persona SSE, 2026-05-11) — used by ``PersonaGenerator.generate_stream``
to emit each persona as soon as its enclosing ``{...}`` object is complete,
instead of waiting for the full ``{"personas": [...]}`` payload.

Designed for the narrow case "find the first JSON array in the buffer, then
yield each top-level object inside that array". Not a general JSON parser.

Usage:

    extractor = JsonArrayObjectExtractor()
    async for chunk in llm.chat_completion_stream(...):
        for obj in extractor.feed(chunk):
            handle(obj)
    # ``extractor.tail`` retains any unparsed remainder for diagnostics.

The extractor tolerates:

- ```json``` / ``` fences before or around the array
- Whitespace, newlines, commas between objects
- Strings containing braces or escaped quotes
- Unicode escapes (delegated to ``json.loads``)

It does NOT attempt to repair malformed JSON — callers should fall back to
``parse_llm_json`` on the final buffer if no objects were emitted.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class JsonArrayObjectExtractor:
    """Stateful extractor — feed chunks, get completed objects."""

    def __init__(self) -> None:
        self._buf: str = ""
        self._cursor: int = 0
        self._in_array: bool = False
        self._depth: int = 0
        self._object_start: int = -1
        self._in_string: bool = False
        self._escape: bool = False

    @property
    def tail(self) -> str:
        """Unconsumed portion of the buffer (for diagnostics / fallback parse)."""
        return self._buf[self._cursor:]

    @property
    def full_buffer(self) -> str:
        """Everything fed so far (for fallback whole-blob parsing)."""
        return self._buf

    def feed(self, chunk: str) -> Iterator[dict[str, Any]]:
        """Append a chunk and yield any newly-completed top-level objects."""
        if not chunk:
            return
        self._buf += chunk
        yield from self._scan()

    def _scan(self) -> Iterator[dict[str, Any]]:
        buf = self._buf
        i = self._cursor
        n = len(buf)
        while i < n:
            ch = buf[i]
            if not self._in_array:
                # Searching for the opening '[' that starts the array. Track
                # string state so a stray '[' inside an outer-object key/value
                # (e.g. ``{"hint": "[1]"}``) doesn't fool us.
                if self._in_string:
                    if self._escape:
                        self._escape = False
                    elif ch == "\\":
                        self._escape = True
                    elif ch == '"':
                        self._in_string = False
                elif ch == '"':
                    self._in_string = True
                elif ch == "[":
                    self._in_array = True
                    self._cursor = i + 1
                i += 1
                continue

            if self._depth == 0:
                # Between objects (or before the first). Allow commas, ws, fences.
                if ch == "{":
                    self._depth = 1
                    self._object_start = i
                    self._in_string = False
                    self._escape = False
                    i += 1
                    continue
                if ch == "]":
                    # End of array. Stop scanning further; tail keeps remainder.
                    self._cursor = i + 1
                    return
                # whitespace, comma, junk → skip
                i += 1
                continue

            # Inside an object — track strings and braces.
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                i += 1
                continue

            if ch == '"':
                self._in_string = True
            elif ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    # Object complete — slice and parse.
                    raw = buf[self._object_start : i + 1]
                    self._object_start = -1
                    self._cursor = i + 1
                    parsed = self._safe_parse(raw)
                    if parsed is not None:
                        yield parsed
            i += 1

        # Reached end of buffer; remember how far we got.
        # If currently inside an object we keep cursor at start-of-object so the
        # next feed re-scans from there. Otherwise advance cursor to n so we
        # don't re-walk consumed whitespace.
        if self._depth > 0 and self._object_start >= 0:
            self._cursor = self._object_start
            # Reset string state — re-scanned from object_start anyway.
            self._in_string = False
            self._escape = False
            self._depth = 0
        else:
            self._cursor = n

    @staticmethod
    def _safe_parse(raw: str) -> dict[str, Any] | None:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "JsonArrayObjectExtractor: skipping unparseable object: %s "
                "(raw=%r)",
                exc,
                raw[:200],
            )
            return None
        return value if isinstance(value, dict) else None


__all__ = ["JsonArrayObjectExtractor"]

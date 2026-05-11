"""Unit tests for ``app.llm.streaming_json.JsonArrayObjectExtractor``.

Covers incremental delivery, string-escape handling, and the outer-object
wrapper case used by the persona SSE pipeline (spec §17.3.1.2).
"""
from __future__ import annotations

import json

import pytest

from app.llm.streaming_json import JsonArrayObjectExtractor


def feed_all(extractor: JsonArrayObjectExtractor, chunks: list[str]) -> list[dict]:
    out: list[dict] = []
    for ch in chunks:
        out.extend(extractor.feed(ch))
    return out


def test_full_payload_one_shot() -> None:
    raw = json.dumps(
        {"personas": [{"name": "A"}, {"name": "B"}]}, ensure_ascii=False
    )
    extractor = JsonArrayObjectExtractor()
    out = feed_all(extractor, [raw])
    assert [p["name"] for p in out] == ["A", "B"]


def test_chunked_delivery() -> None:
    raw = json.dumps(
        {"personas": [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}]},
        ensure_ascii=False,
    )
    extractor = JsonArrayObjectExtractor()
    # Feed one character at a time — the worst-case streaming pattern.
    out: list[dict] = []
    for ch in raw:
        out.extend(extractor.feed(ch))
    assert [p["name"] for p in out] == ["甲", "乙", "丙"]


def test_string_with_braces_is_not_treated_as_object() -> None:
    raw = '{"personas":[{"name":"X","note":"contains {brace} inside"},{"name":"Y"}]}'
    extractor = JsonArrayObjectExtractor()
    out = feed_all(extractor, [raw])
    assert len(out) == 2
    assert out[0]["note"] == "contains {brace} inside"


def test_escaped_quote_in_string() -> None:
    raw = '{"personas":[{"name":"He said \\"hi\\""}]}'
    extractor = JsonArrayObjectExtractor()
    out = feed_all(extractor, [raw])
    assert out[0]["name"] == 'He said "hi"'


def test_bracket_inside_outer_string_is_ignored() -> None:
    # The leading "[" inside a string before the real array should not be
    # mistaken for the array opener.
    raw = '{"hint":"[fake]","personas":[{"name":"Z"}]}'
    extractor = JsonArrayObjectExtractor()
    out = feed_all(extractor, [raw])
    assert [p["name"] for p in out] == ["Z"]


def test_chunk_splits_inside_object() -> None:
    # Object boundary appears across two chunks.
    chunks = ['{"personas":[{"name":"', 'partial', '"}]}']
    extractor = JsonArrayObjectExtractor()
    out = feed_all(extractor, chunks)
    assert out == [{"name": "partial"}]


def test_partial_object_then_completion() -> None:
    # First chunk has an opening object but not the closing brace.
    extractor = JsonArrayObjectExtractor()
    out1 = list(extractor.feed('{"personas":[{"name":"foo"'))
    assert out1 == []
    out2 = list(extractor.feed('}]}'))
    assert out2 == [{"name": "foo"}]

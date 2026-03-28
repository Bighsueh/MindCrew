"""Topic Saturation computation for the Summarizer role (§7.6).

Extracted from evaluator.py to keep files under 500 lines.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import TopicSaturation

logger = logging.getLogger(__name__)


async def compute_and_write_topic_saturation(
    blackboard: BlackboardManager,
    stage: str,
    canvas: dict,
    chat: list[dict],
    llm_service: Any,
) -> None:
    """Compute topic saturation via LLM and write to Blackboard."""
    try:
        intentions = await blackboard.read_other_intentions()
        intention_summary = ""
        if intentions:
            intention_lines = [
                f"- {i.seat_role}: {i.reasoning_summary}"
                for i in intentions
            ]
            intention_summary = (
                "\n\nAI 成員最近的思考：\n" + "\n".join(intention_lines)
            )

        notes: list[dict] = canvas.get("notes", [])
        if not notes:
            return

        notes_text = "\n".join(
            f"- [{n.get('id', '?')}] {n.get('content', '')}"
            for n in notes
        )

        prompt = (
            f"請分析以下白板上的便條紙，辨識出主要討論主題，"
            f"並評估每個主題的觀點多元性。\n\n"
            f"便條紙：\n{notes_text}\n"
            f"{intention_summary}\n\n"
            "請以 JSON 格式回應（只回應 JSON，不要包含其他文字）：\n"
            '{\n'
            '  "topics": [\n'
            '    {\n'
            '      "name": "主題名稱",\n'
            '      "note_count": 數字,\n'
            '      "contributors": ["crew_1", "crew_2"],\n'
            '      "viewpoint_diversity": "low" | "medium" | "high",\n'
            '      "existing_angles": ["已有角度1", "已有角度2"],\n'
            '      "missing_angles": ["缺少角度1", "缺少角度2"],\n'
            '      "saturation": "low" | "medium" | "high"\n'
            '    }\n'
            '  ],\n'
            '  "blind_spots": ["盲區1", "盲區2"]\n'
            '}\n\n'
            "判定規則：\n"
            "- viewpoint_diversity：看角度是否多元（只有一個角度=low，2-3個=medium，4+個=high）\n"
            "- saturation：note_count 高且 viewpoint_diversity 高才是 high；"
            "note_count 高但 viewpoint_diversity 低為 medium\n"
            "- blind_spots：列出完全沒被討論到的重要面向"
        )

        messages = [
            {"role": "system", "content": "你是一位 Design Thinking 工作坊分析專家。"},
            {"role": "user", "content": prompt},
        ]

        response = await llm_service.chat_completion(
            messages=messages, temperature=0.3, max_tokens=1024
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

        data = json.loads(raw)

        from app.chinese.converter import chinese_converter

        saturation = TopicSaturation(
            stage=stage,
            topics=[
                {
                    "name": chinese_converter.convert(t.get("name", "")),
                    "note_count": t.get("note_count", 0),
                    "contributors": t.get("contributors", []),
                    "viewpoint_diversity": t.get("viewpoint_diversity", "low"),
                    "existing_angles": [
                        chinese_converter.convert(a) for a in t.get("existing_angles", [])
                    ],
                    "missing_angles": [
                        chinese_converter.convert(a) for a in t.get("missing_angles", [])
                    ],
                    "saturation": t.get("saturation", "low"),
                }
                for t in data.get("topics", [])
            ],
            blind_spots=[
                chinese_converter.convert(b) for b in data.get("blind_spots", [])
            ],
        )

        await blackboard.write_topic_saturation(saturation)
        logger.info(
            "Wrote topic_saturation: %d topics, %d blind_spots",
            len(saturation.topics),
            len(saturation.blind_spots),
        )
    except Exception:
        logger.warning(
            "Failed to compute topic saturation",
            exc_info=True,
        )

"""Qualitative LLM evaluation helper for StageEvaluator.

Extracted from evaluator.py to keep files under 500 lines.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.json_utils import parse_llm_json

logger = logging.getLogger(__name__)

_STAGE_NAMES = {
    "discover": "Discover（發現）",
    "define": "Define（定義）",
    "develop": "Develop（發展）",
    "deliver": "Deliver（交付）",
}


async def run_qualitative(
    stage: str,
    canvas: dict,
    chat: list[dict],
    llm_service: Any,
    *,
    project_name: str = "",
    project_description: str = "",
) -> dict | None:
    """Run qualitative LLM stage evaluation. Returns a dict or None on failure."""
    stage_display = _STAGE_NAMES.get(stage, stage)

    canvas_summary = json.dumps(canvas, ensure_ascii=False, indent=2)
    chat_summary = "\n".join(
        f"[{m.get('time', '')}] {m.get('sender', '')}: {m.get('content', '')}"
        for m in chat[-20:]
    )

    project_info = ""
    if project_name:
        project_info = f"專案名稱：{project_name}\n"
        if project_description:
            project_info += f"專案說明：{project_description}\n"
        project_info += "\n"

    prompt = (
        f"{project_info}"
        f"請分析以下 Design Thinking {stage_display} 階段的團隊產出：\n\n"
        f"白板內容：{canvas_summary}\n"
        f"聊天紀錄摘要：{chat_summary}\n\n"
        "請從以下四個面向評分（0-100）：\n"
        "1. 內容多樣性：觀點是否涵蓋多個不同面向？\n"
        "2. 討論深度：每個面向是否有足夠的延伸和探討？\n"
        "3. 收斂程度：團隊是否開始形成共識或重複觀點？\n"
        "4. 盲區檢查：是否有明顯遺漏的重要面向？\n\n"
        "回應格式（只回應 JSON，不要包含其他文字）：\n"
        '{"diversity_score": 0-100, "depth_score": 0-100, '
        '"convergence_score": 0-100, "blind_spot_score": 0-100, '
        '"overall_score": 0-100, "weak_areas": ["面向1", "面向2"], '
        '"summary": "整體評估摘要"}'
    )

    messages = [
        {"role": "system", "content": "你是一位 Design Thinking 工作坊品質評估專家。"},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm_service.chat_completion(
            messages=messages, temperature=0.3, max_tokens=1024
        )
        data = parse_llm_json(response.content)
        if data is None:
            logger.warning("Qualitative evaluation JSON parse failed")
            return None
        return data
    except Exception as exc:
        logger.warning("Qualitative evaluation LLM call failed: %s", exc)
        return None

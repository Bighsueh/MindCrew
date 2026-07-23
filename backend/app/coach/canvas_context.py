"""DT 教練的 canvas 摘要 builder：產生「共享白板摘要」供 prompt 插值。

設計原則（對齊  改寫版）：
  - 教練「看得到大概」白板狀態（分群數、密度、整齊度、卡點），但
    **不**包含便條紙的逐字內容，避免 LLM 引用具體文字打破設計意圖。
  - 摘要總長度限 300 字內，超過會 truncate 並以「…」結尾。
  - 取資料**強制**透過 ``app.canvas.tools_perception.get_canvas_summary``——
    已是現成的 ~400 token 結構化摘要，本模組只把它壓成多行文字。
  - 失敗時 swallow exception 回傳空字串（同 group summary 的容錯策略），
    不阻擋 Coach 回覆主流程（spec §7.3）。
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


#: 摘要總長度上限（中文字元數）。超過會 truncate 並以「…」結尾。
_SUMMARY_MAX_CHARS = 300

#: 摘要中最多列出幾個 cluster（避免單一摘要被一堆群塞滿）。
_CLUSTER_LIST_LIMIT = 5

#: 單一 cluster 標籤（label）保留字元上限。
_LABEL_MAX_CHARS = 16


def _truncate(text: str, limit: int) -> str:
    """把 ``text`` 截至 ``limit`` 個字元，超過時補上「…」。"""
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)] + "…"


def _density_word(note_count: int, density: str) -> str:
    """把 dense / sparse 翻成中文。"""
    if density == "dense":
        return "密集"
    if note_count <= 1:
        return "單張"
    return "稀疏"


async def build_canvas_topic_summary(
    project_id: UUID,
    micro_phase: str,
) -> str:
    """產生共享白板摘要文字（≤ 300 字）供 DT 教練 prompt 插值。

    步驟：
      1. 呼叫 ``get_canvas_summary(project_id, micro_phase)`` 取結構化資料。
      2. 抽出總覽（total_notes、cluster_count、orderliness_score、overlap_count）
         與最多 _CLUSTER_LIST_LIMIT 個 cluster 的「標籤 + 數量 + 密度」。
      3. 串成多行字串再 truncate 到 ``_SUMMARY_MAX_CHARS`` 為止。

    Args:
        project_id: 目標專案。
        micro_phase: 當前微階段（影響 organization_hint）。

    Returns:
        摘要字串；若白板空或讀取失敗則回傳空字串（由 prompts 自行
        替換為「（暫無）」）。
    """
    try:
        # 惰性 import：canvas 子系統會拉 numpy / scikit-learn，避免在 app
        # startup 強制載入，與既有 organization_turn / context_buffer 慣例一致。
        from app.canvas.tools_perception import get_canvas_summary

        data = await get_canvas_summary(project_id, micro_phase)
    except Exception as exc:  # noqa: BLE001 — 摘要失敗不該擋住 Coach 回覆。
        logger.warning(
            "build_canvas_topic_summary 取 canvas 摘要失敗 project=%s err=%s",
            project_id,
            exc,
        )
        return ""

    summary = data.get("summary") or {}
    total_notes = int(summary.get("total_notes") or 0)
    if total_notes == 0:
        return ""

    cluster_count = int(summary.get("cluster_count") or 0)
    overlap_count = int(summary.get("overlap_count") or 0)
    orderliness = float(summary.get("orderliness_score") or 0.0)
    ungrouped_count = int(summary.get("ungrouped_count") or 0)

    lines: list[str] = [
        f"- 總覽：便條紙 {total_notes} 張、分群 {cluster_count} 群、"
        f"整齊度 {orderliness:.1f}、重疊 {overlap_count} 處、"
        f"未分群 {ungrouped_count} 張"
    ]

    clusters = data.get("clusters") or []
    for cluster in clusters[:_CLUSTER_LIST_LIMIT]:
        label_raw = str(cluster.get("suggested_label") or "（未命名）")
        label = _truncate(label_raw, _LABEL_MAX_CHARS)
        note_count = int(cluster.get("note_count") or 0)
        density = str(cluster.get("density") or "sparse")
        density_zh = _density_word(note_count, density)
        lines.append(f"- 群「{label}」：{note_count} 張、{density_zh}")

    if len(clusters) > _CLUSTER_LIST_LIMIT:
        lines.append(f"- …另有 {len(clusters) - _CLUSTER_LIST_LIMIT} 群未列出")

    hint = str(data.get("organization_hint") or "").strip()
    if hint:
        lines.append(f"- 觀察：{hint}")

    summary_text = "\n".join(lines)
    return _truncate(summary_text, _SUMMARY_MAX_CHARS)

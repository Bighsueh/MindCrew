"""First-diamond closing ritual（spec 26 v2.0，Phase 42 C2）.

Triggered after ``advance_stage`` moves a project to ``current_stage='completed'``.
結業鏈＝痛點清單 → 問題定義 → 設計題目（人物誌已隨 Persona/1.6 移除，§5.1）：
- 痛點摘要 ``_summarize_pain_points``（§5.2）
- 選定的問題定義＋配對選定理由 ``_collect_chosen_problem_statements``（§5.3，**直讀選定
  區**＝2.6 收口閘的同一真理來源）
- 設計題目 ``_collect_design_questions``（§5.4，from 關聯＝cites 指向選定問題定義）

寫入 ``project.first_diamond_output``（payload v2 shape，§6.2），由 LLM 生成 200-400 字
結業匯報並以組長身分發到群聊。

Phase 42 C2：v1.0 的 ``_pick_chosen_*``（投票標記優先／取最後一張）heuristic
**全部廢除**（§5.5：「最後一張」是 bug，可能朗讀沒被選上的便條；投票標記欄位隨投票
機制移除）——當選與否唯一判準＝選定區成員＋配對關聯，抽不到回空值由話術誠實反映。

Design:
- Best-effort: any single failure (canvas read, LLM call, DB write) degrades
  gracefully — the user-facing UX (banner) keeps working with whatever data
  could be collected.
- Idempotent: if called twice, the second call updates first_diamond_output
  and re-posts the closing message (rare but harmless).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _note_text(note: Any) -> str:
    return (getattr(note, "text", None) or getattr(note, "content", "") or "").strip()


async def _wall_notes(project_id: UUID, notes: list[Any], zone_id: str) -> list[Any]:
    """牆面成員（registered bounds 優先、否則 default_bounds；過渡實作同 artifact gate）。"""
    from app.canvas.zones import ZONES

    zone = ZONES.get(zone_id)
    if zone is None:
        return []
    bounds = zone.default_bounds
    try:
        from app.canvas.zone_registry import get_all_zones_for_project

        registered = await get_all_zones_for_project(project_id)
        bounds = registered.get(zone_id) or bounds
    except Exception:  # pragma: no cover - registry 不可達退 default
        pass
    if bounds is None:
        return []
    return [
        n for n in notes
        if bounds.contains(float(getattr(n, "x", 0.0)), float(getattr(n, "y", 0.0)))
    ]


async def _summarize_pain_points(
    project_id: UUID, notes: list[Any]
) -> dict[str, Any]:
    """彙整痛點清單摘要（spec 26 v2.0 §5.2；回顧鏈第一環）。

    - total＝痛點牆內 kind != label 張數（與 artifact gate 同口徑）。
    - themes＝牆內 label 便條（主題群標籤）＋同 concept_group_id 痛點張數；
      群結構抓不到 → themes=[]（best-effort）。
    - highlights＝≤5 張痛點原文截短（cites 優先排序隨 C2 選定鏈接上）。
    """
    wall = await _wall_notes(project_id, notes, "pain_wall")
    pains = [n for n in wall if getattr(n, "kind", "content") != "label"]
    labels = [n for n in wall if getattr(n, "kind", "content") == "label"]

    pain_count_by_group: dict[str, int] = {}
    for n in pains:
        gid = getattr(n, "concept_group_id", None)
        if gid:
            pain_count_by_group[str(gid)] = pain_count_by_group.get(str(gid), 0) + 1

    themes: list[dict[str, Any]] = []
    for label in labels:
        gid = getattr(label, "concept_group_id", None)
        text = _note_text(label)
        if not gid or not text:
            continue
        count = pain_count_by_group.get(str(gid), 0)
        if count > 0:
            themes.append({"label": text, "count": count})

    highlights = [_note_text(n)[:40] for n in pains[:5] if _note_text(n)]
    return {"total": len(pains), "themes": themes, "highlights": highlights}


async def _collect_chosen_problem_statements(
    project_id: UUID, notes: list[Any]
) -> list[dict[str, Any]]:
    """直讀選定區，抽出當選問題定義＋配對的選定理由（spec 26 v2.0 §5.3）。

    與 spec 25 v2.0 §3.2 ``selection_pairing`` 共用同一界定（選定區成員＝動態 section
    帶內便條；配對＝選定理由 cites 指向問題定義）。time-box 強制收口的 forced 理由
    便條（``time_box_forced``）→ ``selection_reason: None``（誠實，§3.1 缺理由句型，
    forced 兜底文字不當真實理由唸進匯報）；取不到理由 → None。

    回傳 ``[{"note_id", "text", "selection_reason"}]``；選定區無問題定義 → ``[]``。
    """
    # 與 artifact_gate 共用選定區界定與問題定義判定，避免兩處發散（spec 26 §5.3 註）。
    # selection_members 已升格至 sections（gate/closing/perception 單一真理來源）。
    from app.canvas.artifact_gate import _is_problem_statement
    from app.canvas.sections import selection_members
    from app.canvas.text_templates import validate_template

    members = await selection_members(project_id, notes)
    ps_notes = [n for n in members if _is_problem_statement(n)]
    ps_ids = {str(getattr(p, "id", "")) for p in ps_notes}
    reason_notes = [
        n for n in members
        if str(getattr(n, "id", "")) not in ps_ids
        and (
            validate_template(_note_text(n), "selection_reason").passed
            or bool(getattr(n, "time_box_forced", False))
        )
    ]

    out: list[dict[str, Any]] = []
    for p in ps_notes:
        pid = str(getattr(p, "id", ""))
        selection_reason: str | None = None
        for r in reason_notes:
            if pid in (getattr(r, "cites", None) or ()):
                # forced 兜底理由不當真實理由（§3.1）；只有合格選定理由才唸進匯報。
                # Phase 42 補正 R4：非 forced 優先——修復前取第一命中就 break，
                # forced 兜底會遮蔽學生後補的真理由、誤走「缺理由誠實句型」。
                if not getattr(r, "time_box_forced", False):
                    selection_reason = _note_text(r)
                    break
        out.append({
            "note_id": pid,
            "text": _note_text(p),
            "selection_reason": selection_reason,
        })
    return out


def _collect_design_questions(
    notes: list[Any], chosen_problem_statements: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """抽出設計題目（hmw 模板），以 from 關聯（cites）對回選定問題定義（spec 26 v2.0 §5.4）。

    與 spec 25 v2.0 §3.3 ``hmw_pairing`` 共用界定：只收錄 cites 指向選定區內問題定義者；
    指向選定區外或不存在的便條＝無效，不收錄。回傳 ``[{"note_id", "text", "from_note_id"}]``。
    """
    from app.canvas.text_templates import validate_template

    chosen_ids = {c["note_id"] for c in chosen_problem_statements}
    out: list[dict[str, Any]] = []
    for n in notes:
        if not validate_template(_note_text(n), "hmw").passed:
            continue
        from_id = next(
            (c for c in (getattr(n, "cites", None) or ()) if c in chosen_ids),
            None,
        )
        if from_id is None:
            continue
        out.append({
            "note_id": str(getattr(n, "id", "")),
            "text": _note_text(n),
            "from_note_id": from_id,
        })
    return out


async def trigger_first_diamond_closing(
    project_id: UUID,
    triggered_by: str,
) -> dict[str, Any]:
    """Run the closing ritual end-to-end.

    1. Read canvas notes (best-effort).
    2. 抽取結業鏈素材：痛點摘要＋直讀選定區的選定問題定義/設計題目（spec 26 §5）。
    3. Write project.first_diamond_output (best-effort, single transaction).
    4. Ask LLM for closing message; on failure use deterministic fallback.
    5. Post closing message to group chat as supervisor (best-effort).

    Returns the payload that was written (or attempted to be written) to
    project.first_diamond_output.
    """
    # ── Step 1: collect canvas ─────────────────────────────
    notes: list[Any] = []
    try:
        from app.canvas.analyzer import get_spatial_analyzer

        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        notes = list(analysis.notes)
    except Exception as exc:
        logger.warning(
            "closing ritual: canvas analyze failed project=%s: %s",
            project_id,
            exc,
        )

    # ── Step 2: 抽取結業鏈素材（spec 26 v2.0 §5；痛點 → 問題定義 → 設計題目）──
    pain_points_summary = await _summarize_pain_points(project_id, notes)
    chosen_problem_statements = await _collect_chosen_problem_statements(
        project_id, notes
    )
    design_questions = _collect_design_questions(notes, chosen_problem_statements)

    completed_at = datetime.now(timezone.utc).isoformat()
    # payload v2 shape（spec 26 v2.0 §6.2）：陣列化選定問題定義/設計題目，移除單數舊欄位
    # 與人物誌；version=2 供 read 端區分新舊（舊 v1 無 version 欄位）。
    output_payload: dict[str, Any] = {
        "version": 2,
        "pain_points_summary": pain_points_summary,
        "chosen_problem_statements": chosen_problem_statements,
        "design_questions": design_questions,
        "completed_at": completed_at,
    }

    # ── Step 3: persist to DB ──────────────────────────────
    project_name = ""
    try:
        from sqlalchemy import update
        from app.db.models.project import Project
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            row = await session.get(Project, project_id)
            if row:
                project_name = row.name or ""
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(
                    first_diamond_output=output_payload,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "closing ritual: DB write failed project=%s: %s", project_id, exc
        )

    # ── Step 4: build closing message (LLM, with fallback) ─
    closing_message = await _build_closing_message(
        pain_points_summary=pain_points_summary,
        chosen_problem_statements=chosen_problem_statements,
        design_questions=design_questions,
        project_name=project_name,
        project_id=project_id,
    )
    output_payload["summary"] = closing_message

    # ── Step 5: post chat (best-effort) ────────────────────
    try:
        from app.chinese.converter import chinese_converter
        from app.events.bus import event_bus
        from app.events.types import ChatMessageEvent
        from app.agents.personas.display import resolve_display_name

        await event_bus.publish(
            ChatMessageEvent(
                project_id=project_id,
                sender_id="agent_supervisor",
                sender_type="ai",
                sender_name=resolve_display_name("supervisor"),
                content=chinese_converter.convert(closing_message),
            )
        )
    except Exception as exc:
        logger.warning(
            "closing ritual: chat post failed project=%s: %s", project_id, exc
        )

    return output_payload


async def _build_closing_message(
    *,
    pain_points_summary: dict[str, Any],
    chosen_problem_statements: list[dict[str, Any]],
    design_questions: list[dict[str, Any]],
    project_name: str,
    project_id: UUID,
) -> str:
    """LLM-driven closing message with deterministic fallback（spec 26 v2.0 §3）。"""
    from app.agents.prompts.closing_prompts import (
        CLOSING_RITUAL_SYSTEM_PROMPT,
        build_closing_ritual_user_prompt,
        deterministic_fallback_closing,
    )

    # 缺選定理由句型（§3.1/§3.3）：任一選定問題定義缺理由、或僅有 time_box_forced
    # 兜底理由（_collect 已把 forced 理由記為 None）→ fallback 改誠實句型。
    selection_reason_missing = any(
        not c.get("selection_reason") for c in chosen_problem_statements
    ) if chosen_problem_statements else False

    try:
        from app.llm.factory import LLMProviderFactory

        llm = LLMProviderFactory.get_service()
        # 閉幕是自主 tick（由 stage_advancement 的 agent 觸發，非真人），
        # 計費歸屬到專案 creator——與所有 agent tick 一致、保證 NOT-NULL。
        from app.llm.owning_user import resolve_owning_user

        owning_user_id = await resolve_owning_user(project_id)

        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": CLOSING_RITUAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_closing_ritual_user_prompt(
                        pain_points_summary=pain_points_summary,
                        chosen_problem_statements=chosen_problem_statements,
                        design_questions=design_questions,
                        project_name=project_name,
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=600,
            caller="first_diamond_closing",
            owning_user_id=owning_user_id,
            project_id=project_id,
        )
        content = (response.content or "").strip()
        if content:
            return content
    except Exception as exc:
        logger.warning(
            "closing ritual: LLM call failed — using fallback: %s", exc
        )

    return deterministic_fallback_closing(
        design_questions=[d["text"] for d in design_questions if d.get("text")],
        pain_point_count=pain_points_summary.get("total", 0),
        project_name=project_name,
        selection_reason_missing=selection_reason_missing,
    )


__all__ = ["trigger_first_diamond_closing"]

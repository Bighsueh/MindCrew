"""Serialize agent context buffer into natural language for Layer 4 prompt.

Extracted from assembler.py to keep both files under 500 lines.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_context_description(context: dict) -> str:
    """Serialise the context buffer dict into a natural language description."""
    parts: list[str] = []

    # Project background
    project_name = context.get("project_name", "")
    project_desc = context.get("project_description", "")
    if project_name:
        bg = f"【專案背景】專案名稱：{project_name}"
        if project_desc:
            bg += f"\n專案說明：{project_desc}"
        parts.append(bg)

    # Phase 27 — Open Brief 流程下使用者於 Step 2 勾選的利害關係人
    # Discover 階段（micro 1.x）是主要消費者，但其他階段也讓 agent 知道
    # 設計對象範圍以保持 narrative 一致。空陣列（legacy project）graceful skip。
    stakeholders = context.get("stakeholders") or []
    if isinstance(stakeholders, list) and stakeholders:
        sh_lines: list[str] = []
        for idx, sh in enumerate(stakeholders, start=1):
            if not isinstance(sh, dict):
                continue
            name = str(sh.get("name", "")).strip()
            role = str(sh.get("role", "")).strip()
            relevance = str(sh.get("relevance", "")).strip()
            if not name or not role:
                continue
            line = f"{idx}. {name}（{role}）"
            if relevance:
                line += f" — {relevance}"
            sh_lines.append(line)
        if sh_lines:
            parts.append(
                "【已選定利害關係人】（建立時由人類勾選作為設計對象，"
                "Discover 階段的便利貼 / 問題 / 訪談請以這些人為錨點）\n"
                + "\n".join(sh_lines)
            )

    stage = context.get("current_stage", "unknown")
    duration = context.get("stage_duration_minutes", 0)
    parts.append(f"【目前狀態】當前階段：{stage}，已進行 {duration} 分鐘。")

    # specs/16-timer-system.md §6.5.4：時間預算 + 壓力等級 + 階段意圖 + directive
    used_pct = context.get("time_budget_used_pct")
    pressure = context.get("time_pressure_level")
    intent = context.get("phase_intent")
    if used_pct is not None and pressure:
        try:
            from app.stages.phase_intent import get_phase_intent_label_zh
            from app.timer.pressure import (
                get_pressure_label_zh,
                pressure_directive,
            )
            intent_zh = get_phase_intent_label_zh(intent) if intent else "過渡"
            pressure_zh = get_pressure_label_zh(pressure)
            line = (
                f"【時間預算】已用 {used_pct:.0f}%（壓力：{pressure_zh}）；"
                f"本階段意圖：{intent_zh}。"
            )
            directive = pressure_directive(pressure, intent or "transitional")
            if directive:
                line += f"\n建議策略：{directive}"
            parts.append(line)
        except Exception:
            # 失敗不擋 prompt 組裝；只在 debug log 留痕。
            logger.debug("time pressure serialization failed", exc_info=True)

    # Micro-phase info (v2.0)
    micro_phase = context.get("current_micro_phase")
    if micro_phase:
        from app.stages.micro_phases import get_micro_phase as _get_micro_phase
        try:
            mp = _get_micro_phase(micro_phase)
            parts.append(f"【微階段】{mp.name_zh}（{micro_phase}）")
        except KeyError:
            pass
        role_status = context.get("my_role_status", "normal")
        if role_status != "normal":
            parts.append(f"【角色狀態】{role_status}")
    elif stage == "discover":
        from app.agents.prompts.discover_subphase import determine_discover_subphase
        canvas_for_subphase = context.get("canvas_state", {})
        chat_for_subphase = context.get("recent_chat", [])
        subphase = determine_discover_subphase(canvas_for_subphase, chat_for_subphase, duration)
        subphase_labels = {"early": "前期（暖身）", "mid": "中期（活躍討論）", "late": "後期（接近飽和）"}
        parts.append(f"【發散子階段】{subphase_labels.get(subphase.value, subphase.value)}")

    # Phase strategy info (Phase 13)
    phase_strategy = context.get("phase_strategy")
    if phase_strategy:
        _COMM_STRATEGY_LABELS = {
            "one_by_one": "逐一發言（OO）",
            "simultaneous": "同步發言（ST）",
        }
        _COMM_GOAL_LABELS = {
            "direct_cooperation": "協作共創",
            "debate": "建設性辯論",
            "mild_competition": "多角度辯護",
        }
        _SUP_MODE_LABELS = {
            "facilitator": "主持人",
            "participant": "參與者",
            "silent": "沉默觀察",
        }
        cs = _COMM_STRATEGY_LABELS.get(phase_strategy.get("comm_strategy", ""), "")
        cg = _COMM_GOAL_LABELS.get(phase_strategy.get("comm_goal", ""), "")
        sm = _SUP_MODE_LABELS.get(phase_strategy.get("supervisor_mode", ""), "")
        parts.append(f"【溝通策略】{cs}，溝通目標：{cg}，Supervisor 模式：{sm}")

    # Canvas state — enhanced with spatial perception (Phase 14)
    _append_canvas_state(parts, context)

    # Chat
    _append_chat(parts, context)

    # Conversation thread context
    active_thread = context.get("active_thread")
    if active_thread:
        thread_topic = active_thread.get("topic_summary", "未知")
        thread_turns = active_thread.get("turn_count", 0)
        thread_participants = "、".join(active_thread.get("participants", []))
        addressed = active_thread.get("addressed_to")
        thread_desc = f"目前討論串：「{thread_topic}」（已 {thread_turns} 輪，參與者：{thread_participants}）"
        if addressed:
            thread_desc += f"\n  → {addressed} 被問了一個問題，應該回應。"
        parts.append(f"【對話脈絡】\n  {thread_desc}")

    # Conversation health (Supervisor only)
    health = context.get("conversation_health")
    if health:
        health_lines = []
        for issue in health.get("issues", []):
            health_lines.append(f"  ⚠️ {issue}")
        if health.get("suggestion"):
            health_lines.append(f"  💡 建議：{health['suggestion']}")
        if health_lines:
            parts.append("【對話健康】\n" + "\n".join(health_lines))

    # Seats
    seats: list[dict] = context.get("seats", [])
    if seats:
        seat_lines = [
            f"  - {s.get('display_name') or s.get('user_name') or s.get('agent_id') or s.get('role', '?')}"
            f"（{s.get('role', '?')}，{s.get('type', '?')}）"
            for s in seats
        ]
        parts.append("【席位狀態】\n" + "\n".join(seat_lines))

    my_seat = context.get("my_seat", "unknown")
    my_display = next(
        (s.get("display_name") or s.get("user_name") or s.get("role", "?")
         for s in seats if s.get("role") == my_seat),
        my_seat,
    )
    parts.append(f"【我的席位】{my_display}（{my_seat}）")

    my_actions: list[dict] = context.get("my_recent_actions", [])
    if my_actions:
        action_lines = [
            f"  - [{a.get('time', '?')}] {a.get('type', '?')}：{a.get('content', '')}"
            for a in my_actions
        ]
        parts.append("【我最近的行動】\n" + "\n".join(action_lines))
    else:
        parts.append("【我最近的行動】目前還沒有行動記錄。")

    # Blackboard
    blackboard: dict = context.get("blackboard", {})
    if blackboard:
        bb_parts = build_blackboard_description(blackboard)
        if bb_parts:
            parts.append(bb_parts)

    return "\n".join(parts)


def _append_canvas_state(parts: list[str], context: dict) -> None:
    """Append canvas state to prompt parts.

    Supports two formats:
    - New spatial-aware format (Phase 14): has 'summary', 'clusters', 'ungrouped_notes'
    - Legacy format: has 'total_notes', 'groups', 'ungrouped', 'notes'
    """
    canvas = context.get("canvas_state", {})

    # Phase 14: spatial-aware canvas summary
    summary = canvas.get("summary")
    if summary:
        total = summary.get("total_notes", 0)
        orderliness = summary.get("orderliness_score", "N/A")
        overlap_count = summary.get("overlap_count", 0)
        cluster_count = summary.get("cluster_count", 0)
        ungrouped_count = summary.get("ungrouped_count", 0)
        board_bounds = summary.get("board_bounds", {})
        free_regions = board_bounds.get("free_regions", [])

        overlap_warning = f" ⚠️ 有 {overlap_count} 對重疊！" if overlap_count > 0 else ""
        parts.append(
            f"【白板狀態】共 {total} 張便條紙，"
            f"{cluster_count} 個語意叢集，"
            f"{ungrouped_count} 張未分群。"
            f"有序度：{orderliness}。{overlap_warning}"
        )
        if free_regions:
            parts.append(f"空閒區域：{'、'.join(free_regions)}。")

        # Organization hint (Phase 15)
        org_hint = canvas.get("organization_hint")
        if org_hint and org_hint != "白板狀態正常，無需特別整理。":
            parts.append(f"💡 整理提示：{org_hint}")

        clusters = canvas.get("clusters", [])
        if clusters:
            cluster_lines = [
                f"  - {c.get('suggested_label', c.get('cluster_id', '?'))}"
                f"（{c.get('note_count', 0)} 張，{c.get('region', '?')}，{c.get('density', '?')}）"
                for c in clusters
            ]
            parts.append("叢集：\n" + "\n".join(cluster_lines))

        ungrouped = canvas.get("ungrouped_notes", [])
        if ungrouped:
            ug_lines = [
                f"  - [{u.get('id', '?')}] {u.get('text_preview', '?')}"
                f"（{u.get('region', '?')}，最近叢集：{u.get('nearest_cluster', 'N/A')}）"
                for u in ungrouped[:8]  # Cap at 8 to save tokens
            ]
            if len(ungrouped) > 8:
                ug_lines.append(f"  ... 還有 {len(ungrouped) - 8} 張未分群便條紙")
            parts.append("未分群便條紙：\n" + "\n".join(ug_lines))

        # Full notes list (only in snapshot mode)
        # Prefer spatial_notes (Phase 14 format) over notes (legacy format)
        full_notes = canvas.get("spatial_notes", canvas.get("notes", []))
        if full_notes:
            note_lines = [
                f"  - [{n.get('id', '?')}] {n.get('text', '')}"
                f"（{n.get('color', '?')}，{n.get('region', '?')}，"
                f"叢集：{n.get('cluster_id', 'N/A')}）"
                for n in full_notes[-15:]  # Cap at 15
            ]
            if len(full_notes) > 15:
                parts.append(f"便條紙（最近 15 張，共 {len(full_notes)} 張）：\n" + "\n".join(note_lines))
            else:
                parts.append("便條紙列表：\n" + "\n".join(note_lines))
        return

    # Legacy format fallback
    total_notes = canvas.get("total_notes", 0)
    groups: list[dict] = canvas.get("groups", [])
    ungrouped: list[str] = canvas.get("ungrouped", [])
    overlap_warning = ""
    if canvas.get("has_overlap"):
        overlap_warning = " ⚠️ 有便條紙重疊！"
    parts.append(
        f"【白板狀態】共 {total_notes} 張便條紙，"
        f"已分成 {len(groups)} 個群組，"
        f"未分群 {len(ungrouped)} 張。{overlap_warning}"
    )
    if groups:
        group_summary = "；".join(
            f"{g.get('name', '未命名')}（{len(g.get('notes', []))} 張）"
            for g in groups
        )
        parts.append(f"群組：{group_summary}。")
    notes: list[dict] = canvas.get("notes", [])
    if notes:
        recent_notes = notes[-10:]
        note_lines = [f"  - [{n.get('id', '?')}] {n.get('content', '')}" for n in recent_notes]
        if len(notes) > 10:
            parts.append(f"便條紙（最近 10 張，共 {len(notes)} 張）：\n" + "\n".join(note_lines))
        else:
            parts.append("便條紙列表：\n" + "\n".join(note_lines))


def _append_chat(parts: list[str], context: dict) -> None:
    """Append chat messages to prompt parts."""
    recent_chat: list[dict] = context.get("recent_chat", [])
    if recent_chat:
        recent_msgs = recent_chat[-16:]
        chat_lines = []
        for m in recent_msgs:
            sender = m.get("sender", "?")
            prefix = ""
            if "supervisor" in sender.lower() or "主持人" in sender:
                prefix = "⭐[主持人] "
            elif "human" in sender.lower() or "(human)" in sender:
                prefix = "👤[人類] "
            chat_lines.append(f"  {prefix}{sender}：{m.get('content', '')}")
        parts.append("【最近聊天】\n" + "\n".join(chat_lines))
    else:
        parts.append("【最近聊天】目前沒有聊天記錄。")


def build_blackboard_description(blackboard: dict) -> str:
    """Serialize Blackboard data into a natural language description."""
    parts: list[str] = []

    intentions: list[dict] = blackboard.get("other_agent_intentions", [])
    if intentions:
        intention_lines = []
        for i in intentions:
            line = f"  - {i.get('seat_role', '?')}：意圖={i.get('next_intent', '?')}"
            if i.get("focus_topic"):
                line += f"，主題=「{i['focus_topic']}」"
            if i.get("viewpoint"):
                line += f"，角度=「{i['viewpoint']}」"
            if i.get("reasoning_summary"):
                line += f"\n    思考：{i['reasoning_summary']}"
            intention_lines.append(line)
        parts.append("【其他 AI 成員的思考（Blackboard）】\n" + "\n".join(intention_lines))

    saturation: dict | None = blackboard.get("topic_saturation")
    if saturation:
        topics: list[dict] = saturation.get("topics", [])
        if topics:
            topic_lines = []
            for t in topics:
                sat_level = t.get("saturation", "?")
                diversity = t.get("viewpoint_diversity", "?")
                topic_lines.append(f"  - {t.get('name', '?')}：飽和度={sat_level}，觀點多元性={diversity}")
                if t.get("missing_angles"):
                    topic_lines.append(f"    缺少的角度：{'、'.join(t['missing_angles'])}")
            parts.append("【主題飽和度】\n" + "\n".join(topic_lines))
        blind_spots: list[str] = saturation.get("blind_spots", [])
        if blind_spots:
            parts.append(f"【盲區（尚未討論）】{'、'.join(blind_spots)}")

    directive: dict | None = blackboard.get("coordination_directive")
    if directive:
        dir_lines: list[str] = []
        rt = directive.get("round_type", "open_diverge")
        if rt == "focused_discuss":
            dir_lines.append(f"Supervisor 指示：聚焦討論「{directive.get('focus_topic', '')}」")
            dir_lines.append("你的回應必須與這個話題直接相關。")
        elif rt == "respond_to":
            speaker = directive.get("invited_speaker", "")
            dir_lines.append(f"Supervisor 指示：{speaker} 請回應")
        elif rt == "summarize":
            dir_lines.append("Supervisor 指示：摘要回合，請整理討論重點")
        instruction = directive.get("instruction", "")
        if instruction:
            dir_lines.append(f"補充說明：{instruction}")
        if dir_lines:
            parts.append("【Supervisor 指令（必須遵守）】\n" + "\n".join(dir_lines))

    return "\n".join(parts) if parts else ""

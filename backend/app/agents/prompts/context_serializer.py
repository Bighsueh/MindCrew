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
                "Discover 階段聊經驗、發想痛點與情境時請以這些人為錨點）\n"
                + "\n".join(sh_lines)
            )

    stage = context.get("current_stage", "unknown")
    duration = context.get("stage_duration_minutes", 0)
    parts.append(f"【目前狀態】當前階段：{stage}，已進行 {duration} 分鐘。")

    # Phase 32 (spec/24 §2)：supervisor 在三大工具 sub-phase 取得 tool_status，
    # 由 context_buffer 注入。已是 OpenCC 後的繁中字串。
    tool_status = context.get("tool_status")
    if tool_status and isinstance(tool_status, str):
        parts.append(tool_status)

    # Phase 42 A1 (spec 04-06 §5.8)：「本關訊號」面板（supervisor only，由
    # context_buffer 注入；crew context 無此 key）。已序列化繁中字串。
    sub_phase_signals = context.get("sub_phase_signals")
    if sub_phase_signals and isinstance(sub_phase_signals, str):
        parts.append(sub_phase_signals)

    # ：時間預算 + 壓力等級 + 階段意圖 + directive
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

    # Phase 42 C0 (spec 10 v2.0 §4.7)：白板最近的移動（move-delta 自然語句渲染）
    _append_canvas_moves(parts, context)

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
            health_lines.append(f"  注意：{issue}")
        if health.get("suggestion"):
            health_lines.append(f"  建議：{health['suggestion']}")
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
        bb_parts = build_blackboard_description(blackboard, seats=seats)
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

        overlap_warning = f" 注意：有 {overlap_count} 對重疊！" if overlap_count > 0 else ""
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
            parts.append(f"整理提示：{org_hint}")

        clusters = canvas.get("clusters", [])
        if clusters:
            cluster_lines = [
                f"  - {c.get('suggested_label', c.get('cluster_id', '?'))}"
                f"（{c.get('note_count', 0)} 張，{c.get('region', '?')}，{c.get('density', '?')}）"
                for c in clusters
            ]
            parts.append("叢集：\n" + "\n".join(cluster_lines))

        # 動態 section（如 2.6 選定區）——**必須給 LLM 真實 id**。
        # 2026-07-13 live 根因：agent context 從來沒有 `sec_…` 真 id，只有 assembler
        # few-shot 的 `section:s1`，crew 於是幻覺 id（抄 s1／拿中文標題當 id）→
        # `section:` 解析不到 → 靜默 snap 回靜態 zone → 選定理由落到問題定義牆 →
        # 收口閘看不到它 → 2.6 有機路徑必然失敗、只能 forced 兜底。
        _append_sections(parts, canvas)

        # Spec 27 §6：分類/標示便條（label note）— AI 必須讀懂並 follow 分類。
        label_notes = canvas.get("label_notes", [])
        if label_notes:
            label_lines = [
                f"  - 「{ln.get('text', '?')}」（{ln.get('region', '?')}區"
                + (f"，群 {ln['group_id']}" if ln.get("group_id") else "")
                + "）"
                for ln in label_notes[:8]
            ]
            parts.append(
                "分類標籤便條（Supervisor/人類所貼，**你必須把概念貼到對的分類底下**）：\n"
                + "\n".join(label_lines)
            )

        # Spec 27 §6/§7：明顯錯置（只在強訊號時出現）— 供 Supervisor 介入糾正。
        misplaced = canvas.get("misplaced_notes", [])
        if misplaced:
            mp_lines = [
                f"  - [{m.get('note_id', '?')}]「{m.get('text', '?')}」"
                f"（目前在 {m.get('current_group', '?')} 群，但被 {m.get('near_group', '?')} 群包圍）"
                for m in misplaced[:5]
            ]
            parts.append(
                "明顯錯置便條（若你是 Supervisor：可把它移到對的群並在聊天室用白話說明原因）：\n"
                + "\n".join(mp_lines)
            )

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

        # Phase 42 D1c-前導：選定問題定義釘住區塊——恆可見、不受最近 15 張截斷／row-21
        # 封存影響，agent 寫 HMW/設計題目的 cites 必須指向這些 id（agent-facing，
        # 不入使用者聊天，#29/#30/#34：對人類隱藏 id 與內部機制）。
        selected_ps_notes = [n for n in full_notes if n.get("selected_ps")]
        if selected_ps_notes:
            parts.append(
                "選定問題定義（設計題目／HMW 的 cites 必須指向這些 id）：\n"
                + "\n".join(
                    f"  - [{n.get('id', '?')}] {n.get('text', '')}"
                    for n in selected_ps_notes
                )
            )

        if full_notes:
            # Spec 27 §4.2：把 concept_group_id 也序列化給 LLM，否則 LLM 看不到既有便條
            # 屬於哪個主題群 → 無法「同對象併同群 / 該開新群」（接話式分群回授迴路）。
            note_lines = [
                f"  - [{n.get('id', '?')}] {n.get('text', '')}"
                f"（{n.get('color', '?')}，{n.get('region', '?')}，"
                f"叢集：{n.get('cluster_id', 'N/A')}"
                + (f"，群 {n.get('concept_group_id')}" if n.get('concept_group_id') else "")
                + (f"，{n.get('kind')}" if n.get('kind') and n.get('kind') != 'content' else "")
                + (f"，引用[{','.join(n.get('cites'))}]" if n.get('cites') else "")
                + "）"
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
        overlap_warning = " 注意：有便條紙重疊！"
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


def _append_sections(parts: list[str], canvas: dict) -> None:
    """把白板上現存的動態區（section）連同**真實 id** 餵給 LLM。

    沒有 section 時整段不出現（多數關卡無動態區，不佔 token）。
    """
    sections = canvas.get("sections") or []
    if not sections:
        return
    # R1b-re：title 是 LLM 開區時給的自由文字——夾換行會把清單行撕開（id 掉進
    # 殘句、弱模型抓錯）、無上限＝token 無界；壓成單行＋截長再渲染。
    def _clean_title(raw: object) -> str:
        flat = " ".join(str(raw or "").split())
        return flat[:40] or "（未命名）"

    lines = [
        f"  - {_clean_title(s.get('title'))}｜區 id：`{s.get('id')}`"
        for s in sections
        if s.get("id")
    ]
    if not lines:
        return
    parts.append(
        "【白板動態區】（組長開出來的新區；要把便條放進去或搬進去時**一定要用下面這串"
        "實際的區 id**，不可自己編、也不可用區的中文標題當 id）：\n"
        + "\n".join(lines)
        + "\n  用法：`create_note(..., position=\"section:<上面的區id>\")`、"
        "`move_note(note_id, to=\"section:<上面的區id>\")`"
    )


def _append_canvas_moves(parts: list[str], context: dict) -> None:
    """Spec 10 v2.0 §4.7：近期 move-delta 事件渲染為自然語句。

    事件已由 move_ingest 語意化（誰移的、從哪區/群到哪區/群、移完旁邊是誰）；
    這裡做確定性的中文句子渲染，讓 AI 能理解移動意圖並接話。
    """
    moves = context.get("canvas_moves") or []
    if not isinstance(moves, list) or not moves:
        return
    lines: list[str] = []
    for m in moves[-5:]:
        if not isinstance(m, dict):
            continue
        who = str(m.get("moved_by") or "有人")
        if m.get("is_human"):
            who += "（真人）"
        content = str(m.get("content") or "")
        from_area = str(m.get("from_area") or "未分區")
        to_area = str(m.get("to_area") or "未分區")
        line = f"  - {who} 把便條「{content}」從「{from_area}」搬到「{to_area}」"
        from_group = m.get("from_group")
        to_group = m.get("to_group")
        if to_group and to_group != from_group:
            line += f"，歸進「{to_group}」群"
        neighbors = [
            str(n.get("content") or "")
            for n in (m.get("neighbors") or [])
            if isinstance(n, dict) and n.get("content")
        ]
        if neighbors:
            line += "，現在它旁邊是「" + "」、「".join(neighbors[:3]) + "」"
        line += "。"
        lines.append(line)
    if lines:
        parts.append("【白板最近的移動】\n" + "\n".join(lines))


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
                prefix = "[主持人] "
            elif "human" in sender.lower() or "(human)" in sender:
                prefix = "[人類] "
            chat_lines.append(f"  {prefix}{sender}：{m.get('content', '')}")
        parts.append("【最近聊天】\n" + "\n".join(chat_lines))
    else:
        parts.append("【最近聊天】目前沒有聊天記錄。")


def _seat_display_name(seat_role: str, seats: list[dict] | None) -> str:
    """Map a seat_role to its display name（真人席名字在 user_name）。"""
    if not seat_role or not seats:
        return ""
    for s in seats:
        if (s.get("role") or s.get("seat_role")) == seat_role:
            return str(s.get("display_name") or s.get("user_name") or "")
    return ""


def build_blackboard_description(blackboard: dict, seats: list[dict] | None = None) -> str:
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
            # Phase 42 B2（守則 6，#15）：用顯示名回灌，避免 LLM 學會把 seat id 當稱呼。
            display = _seat_display_name(speaker, seats) or speaker
            dir_lines.append(f"Supervisor 指示：{display} 請回應")
        elif rt == "summarize":
            dir_lines.append("Supervisor 指示：摘要回合，請整理討論重點")
        instruction = directive.get("instruction", "")
        if instruction:
            dir_lines.append(f"補充說明：{instruction}")
        if dir_lines:
            parts.append("【Supervisor 指令（必須遵守）】\n" + "\n".join(dir_lines))

    return "\n".join(parts) if parts else ""

"""Sub-phase prompts — Spec 13 §3, §4, §8.

每個 sub-phase 的 Prompt 區塊強調：
  - 你現在在哪個 sub-phase
  - 本階段互動模式（silent_write / reveal_round / silent_rearrange / discussion）
  - 你只能在哪些 zone 寫便條
  - 文字模板（若有）
  - 本階段禁止語言（語言護欄摘要）

Assembler 在 Layer 3 注入這些 prompt（取代 micro_phase_prompts 的舊邏輯）。
"""

from __future__ import annotations

from app.canvas.content_gate import describe_module
from app.canvas.text_templates import get_template_prompt
from app.canvas.zones import ZONES
from app.stages.sub_phases import SUB_PHASES, get_sub_phase


COMM_MODE_DESCRIPTIONS: dict[str, str] = {
    "silent_write": (
        "🚫 沉默寫便條階段。**禁止 chat**，只能呼叫 create_note。"
        "一張便條最多一句 headline，不要彼此回應或討論。"
    ),
    "reveal_round": (
        "🔁 揭示輪。**輪到你時**才能講一句並貼便條紙。"
        "不可橫向回應其他人的便條。"
        "若不是你的回合請輸出 no_action。"
    ),
    "silent_rearrange": (
        "🚫 沉默重排。**禁止 chat、禁止 create**，只能 move_note 移動既有便條。"
        "你可以移動任何人寫的便條到你認為合適的位置。"
        "等待結構穩定（連續 30 秒無人移動）即進入下一步。"
    ),
    "discussion": "💬 自由討論階段。可正常 chat 與操作便條紙。",
}


def get_active_comm_mode_description(comm_mode: str) -> str:
    return COMM_MODE_DESCRIPTIONS.get(comm_mode, COMM_MODE_DESCRIPTIONS["discussion"])


# ---------------------------------------------------------------------------
# Sub-phase 主旨（中文）— 對應 Spec §8 每行
# ---------------------------------------------------------------------------

SUB_PHASE_OBJECTIVES: dict[str, str] = {
    # Phase 1
    "1.1a": "破冰：每人輪流分享自身對該議題的使用經驗，幫團隊建立共同認知。不要急著歸納。",
    "1.1b": "獨立列出你認為的利害關係人。**現在沒人能看到你的便條**，避免群體思維。",
    "1.1c": "揭示與歸類：先輪流唸自己的便條，再進入沉默重排，把相似的拖到一起。",
    "1.1d": "為最終的利害關係人清單寫 Scope rationale：納入誰、排除誰、為什麼。沒有 rationale 後續無法 traceback。",
    "1.2": "依據利害關係人分工：每人負責一群（特長 or 協商決定）。",
    "1.3": "規劃調查策略：訪談 / 問卷 / 觀察 / 二手資料搜尋。把訪談題目列出來。",
    "1.4": "實地調查（線下）。本階段白板暫無動作，等資料回來再開 1-5。",
    "1.5": "**原始捕捉，延緩詮釋。** 只保留 quote + 情緒 + 受訪者代號。禁止寫「真正的需求是」這種解讀。",
    "1.6": "把 1-5 的觀察整理到 Empathy Map / Persona / Customer Journey 三個結構化模板。",

    # Phase 2 — Define（第一收斂點）
    "2.1": "把 Discover 階段的需求歸類。沉默重排：把相似的拖在一起，類別會自己長出來。",
    "2.2": "**生成 ≥ 3 個候選 POV**（不是只寫一個）。格式：[USER] 需要 [NEED]，因為 [INSIGHT]。每個必須 cite ≥ 2 筆觀察。",
    "2.3": "對每個候選 POV 進行 Socratic 追問：持續追問「為什麼」找到根源；判斷是「需求」還是「解方」。",
    "2.4": "盤點既有解決方案：哪些已被解決、哪些是真正的缺口。",
    "2.5": "建立收斂準則。在投票之前先寫 Green 便條：時間可行性 / 成本 / 影響範圍 / 差異化等。沒有準則不能開投票。",
    "2.6": "依準則投票收斂：選出 1–3 個高優先級 POV 進入 Develop。",
    "2.7": "把當選 POV 改寫成 Blue HMW（How might we）。每張當選 POV 配一張 HMW。",

    # Phase 3 — Develop（純發散）
    "3.1": "從 HMW dock 選定要發想的 HMW。若有多個，可平行處理（HMW tab）。",
    "3.2": "**沉默寫點子**。獨立思考，每張便條一個點子 + 機制標籤。不評判，數量優先。",
    "3.3": "揭示輪 → 結合、延伸、激發。把類似的拖在一起、從別人便條延伸新想法。",
    "3.4": "多樣性檢查：若點子集中在同一機制，組長會喊 category-shift。",

    # Phase 4 — Deliver
    "4.1a": "對每個想法評估可行性：時間、成本、技術門檻。Green 標記「可行/不可行」+ Yellow 寫理由。",
    "4.1b": "建立 Deliver 收斂準則：能否在 4-2 debrief 內驗證、是否回應核心 HMW、最低可接受 fidelity、失敗成本上限。",
    "4.1c": "依準則投票，選擇最終要採納的解決方案。",
    "4.1d": "**口頭闡明假設**：要驗證的假設、success/fail 條件、最便宜的測試形式。Hypothesis 便條必須在動手前寫好。",
    "4.1e": "把解法轉成 Task Ticket：任務、驗收條件、fidelity 上限、對應假設 id。",
    "4.1f": "**Low-fidelity first**：v1 強制 paper/wireframe/Figma click-through，禁止 production code。多版本迭代。",
    "4.2": "內部 Debrief 三題：(1) 信念更新 (2) 回應檢查 HMW (3) 回溯反省。每題逐張填寫，不可口頭聊聊。",
    "4.3": "三選一決定：Close（產出 Spec）/ Loop to Develop（回 Phase 3）/ Loop to Define（回 Phase 2）。",
}


def build_sub_phase_prompt(sub_phase_id: str) -> str:
    """Build the full sub-phase prompt block for assembler Layer 3."""
    try:
        sp = get_sub_phase(sub_phase_id)
    except KeyError:
        return ""

    lines: list[str] = []
    lines.append(f"## 你現在處於 sub-phase {sub_phase_id}：{sp.name_zh}")
    lines.append("")

    obj = SUB_PHASE_OBJECTIVES.get(sub_phase_id)
    if obj:
        lines.append(f"### 本階段目標")
        lines.append(obj)
        lines.append("")

    # Comm mode
    active_mode = sp.comm_modes[0] if sp.comm_modes else "discussion"
    lines.append("### 互動模式")
    lines.append(get_active_comm_mode_description(active_mode))
    if len(sp.comm_modes) > 1:
        lines.append(
            f"（本 sub-phase 會依序經過：{' → '.join(sp.comm_modes)}）"
        )
    lines.append("")

    # Zones
    if sp.zones:
        lines.append("### 你可以寫便條的區域（zone）")
        for zone_id in sp.zones:
            zone = ZONES.get(zone_id)
            if zone:
                colors = ", ".join(zone.allowed_colors)
                title = zone.visual.title_sticky if zone.visual else zone_id
                lines.append(f"- `{zone_id}` — {title}（可用顏色：{colors}）")
        lines.append("- `park` — 孤兒區（任何顏色，跨 phase 共用）")
        lines.append("")

    # Templates
    if sp.templates:
        lines.append("### 便條紙文字格式")
        for tpl_id in sp.templates:
            prompt = get_template_prompt(tpl_id)
            if prompt:
                lines.append(f"**{tpl_id}**：")
                lines.append(prompt)
                lines.append("")

    # Gates
    if sp.gate_modules:
        lines.append("### 本階段禁止語言（語言護欄）")
        for module_id in sp.gate_modules:
            lines.append(f"- {describe_module(module_id)}")
        lines.append("")
        lines.append("違反規則的便條會被系統 reject 並要求改寫。")
        lines.append("")

    # Tools available
    lines.append("### 可用工具")
    lines.append(
        "- `create_note(text, color, position)` — 顏色 yellow/pink/blue/green"
    )
    lines.append("- `move_note(note_id, to)`")
    lines.append("- `edit_note(note_id, text)` — 不能改顏色")
    lines.append("- `delete_note(note_id)`")
    if "supervisor" in sub_phase_id or True:
        lines.append("- 若你是 Supervisor：`draw_zone` / `draw_template` 可建立新區域")
    lines.append("- `chat_message(text)` — **僅在 discussion 模式可用**")
    lines.append("")

    return "\n".join(lines)


def list_zones_for_sub_phase(sub_phase_id: str) -> list[str]:
    """List zone ids active for the given sub-phase (含 park always-on)."""
    try:
        sp = get_sub_phase(sub_phase_id)
    except KeyError:
        return ["park"]
    return list(sp.zones) + ["park"]

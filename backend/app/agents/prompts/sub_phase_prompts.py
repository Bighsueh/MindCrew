"""Sub-phase prompts — Spec 04-03 v4.25 §3（Phase 42 B2：分角色注入＋13 關進場語）。

每個 sub-phase 的 Prompt 區塊強調：
  - 你現在在哪個 sub-phase
  - 本階段互動模式（Phase 41 後：reveal_round / discussion / threaded_reveal）
  - 發散/收斂軟性護欄（反echo / 收斂專注，取代原沉默模式）
  - 你只能在哪些 zone 寫便條
  - 文字模板（若有）
  - 本階段禁止語言（語言護欄摘要）
  - 分角色內容（Phase 42 B2）：組長＝共用守則＋進場語；crew＝行為要點
    （資料在 sub_phase_entry.py；0.0a 由 warmup_game.py 承載、此處不重複）

Assembler 在 Layer 3 注入這些 prompt（取代 micro_phase_prompts 的舊邏輯）。
"""

from __future__ import annotations

from app.canvas.content_gate import describe_module
from app.canvas.text_templates import get_template_name, get_template_prompt
from app.canvas.zones import ZONE_NAMES_ZH
from app.stages.labels import student_facing_label
from app.stages.sub_phases import SUB_PHASES, get_sub_phase

from app.agents.prompts.sub_phase_entry import (
    SUB_PHASE_CREW_POINTS,
    SUB_PHASE_ENTRY,
    SUPERVISOR_COMMON_RULES,
    TEACHING_GUIDE,
)


# Phase 41：移除 silent_write / silent_rearrange（沉默模式）。所有模式皆可 chat + 操作便條；
# 避免定錨 / 不重貼 / 收斂專注改由發散/收斂軟性護欄承載（見 build_sub_phase_prompt）。
COMM_MODE_DESCRIPTIONS: dict[str, str] = {
    "reveal_round": (
        "揭示輪。**輪到你時**才講一句並貼便條紙。"
        "不可橫向搶在別人前面回應；若不是你的回合請輸出 no_action。"
    ),
    "discussion": "自由討論階段。可正常 chat 與操作便條紙。",
    "threaded_reveal": (
        "接話式（概念銜接）。對話照常在聊天室進行；**便條只放沉澱後的概念／洞見，不是逐字對白、不是問句**。\n"
        "規則：\n"
        "1. **不是每講一句就貼一張**——先把一段對話萃取成一個概念，成形了才 create_note。\n"
        "2. 同一個對象的概念帶同一個 `group_id`（例：顧客一群、店員一群），系統會把同群的便條擺在一起。\n"
        "3. **不要重複貼同一個概念**（包含換句話說重述一次）。\n"
        "4. 錯（變聊天記錄）：『價格太貴』→『跟哪家比？』→『隔壁便宜兩成』；"
        "對（只留概念）：在顧客群下留『價格太貴』『其實在意划不划算（不是單純嫌貴）』『願為品質多付一點』。\n"
        "5. 便條須過 must_be_concept 護欄（不可是逐字對白或純問句）。"
    ),
}


def get_active_comm_mode_description(comm_mode: str) -> str:
    return COMM_MODE_DESCRIPTIONS.get(comm_mode, COMM_MODE_DESCRIPTIONS["discussion"])


# Phase 41：發散/收斂軟性護欄文字（取代 silent_write / silent_rearrange 沉默 enforcement）。
_DIVERGENT_GUARDRAIL = (
    "**發散階段——求多、求廣、避免定錨。**\n"
    "- 先想你自己的角度，**提出跟牆上已有的不一樣的想法，不要重述或換句話說重貼別人說過的**。\n"
    "- 貼之前先掃一眼牆上既有便條：已經有的概念就不要再貼一張（系統也會擋重複）。\n"
    "- 可以邊聊邊貼，但別為了附和而把同一件事再講一遍——把空間留給新角度。"
)
_CONVERGENT_GUARDRAIL = (
    "**收斂階段——專注整理，先別冒新點子。**\n"
    "- **優先把相似的便條歸群、搬動到一起**（move_note / swap_notes），讓類別自己浮現。\n"
    "- 除非有真正全新的洞見，否則**先別急著貼新便條**；要新增前先確認牆上沒有。\n"
    "- 每次搬動 / 歸群，在聊天室用一句白話說明為什麼這幾張是同一類（教學透明）。"
)


def _phase_intent_guardrail(sub_phase_id: str) -> str:
    """依 phase_intent 回傳發散/收斂軟性護欄文字（transitional 回空字串）。"""
    try:
        from app.stages.phase_intent import get_phase_intent_by_sub_phase

        intent = get_phase_intent_by_sub_phase(sub_phase_id)
    except Exception:
        return ""
    if intent == "divergent":
        return _DIVERGENT_GUARDRAIL
    if intent == "convergent":
        return _CONVERGENT_GUARDRAIL
    return ""


def _tool_affordance_hints(sub_phase_id: str) -> list[str]:
    """Phase 42 D1a：逐關工具用法 affordance（教 LLM 真的去用 cites / group_id）。

    對應 `_discussion/docs/phase42-define-orchestration-diagnosis.md` §4 與 90 分單房
    clean run 證實的唯一真落差：2.7 設計題目沒被有機生出（只剩字面占位、cites 空）＋
    2.2 問題定義不帶 cites／2.1 歸群不帶 group_id。仿既有 2.6 open_section 範本：
    affordance 行＋工具簽名明示＋接續動作。角色無關（誰做誰用，沒用到也無害）。
    """
    hints: list[str] = []
    if sub_phase_id == "2.1":
        hints.append(
            "- 把同一件事的痛點歸到一起時，用 `move_note(note_id, to=\"group:群名\", "
            "group_id=\"群名\")` 帶上 group_id（語意分群、不是搬到特定區）；"
            "**群名沿用牆上已有的、別亂開新群**（系統據此分群，也避免去重誤併）。"
        )
    if sub_phase_id == "2.2":
        hints.append(
            "- 寫問題定義用 `create_note(text=\"某使用者 需要 …，因為 …\", cites=[痛點id])`"
            "——cites 帶你參考的痛點便條 id（從上面白板狀態的「[n..]」複製）；"
            "系統在背後記引用關聯（指準則、過關門檻也算數量）。"
        )
    if sub_phase_id == "2.7":
        hints.append(
            "- 白板上「設計題目｜我們可以怎麼…？」那張是**組長貼的標題 label、不是你的交付**——別複製它。"
            "你的交付是 **content 便條（不要帶 kind=\"label\"）**：把每句選定的問題定義改寫成設計題目，用 "
            "`create_note(text=\"我們可以怎麼〔針對那句問題定義量身的具體題目〕？\", cites=[原問題定義id])`"
            "——寫**真題目**（不是套「我們可以怎麼…？」的空殼），cites 指向它對應的問題定義；一句配一張。"
        )
    return hints


def _move_grid_human_scaffold(sub_phase_id: str) -> str | None:
    """Phase 42 D1d（#26 demo-before-ask ＋ #27 真人「拖＋說」雙要求）——移動格帶人鷹架。

    2.1（痛點歸類）與 2.6（搬進選定區）以「移動／歸類便條」為主，真人要**親自動手**。
    G01 真人硬閘會擋到真人「拖＋說」都做到才放行（round_lock 2.1/2.6＝move+chat、mode=all）。
    組長要：①先讓 crew 示範一次，使用者才知道怎麼做（#26）；②請使用者自己拖一張並在
    聊天說明（#27）；③**監督、提醒，不代勞**（不替他拖、不說「我幫你」）。組長限定。
    """
    if sub_phase_id == "2.1":
        return (
            "這一關請使用者**親自動手**歸類。**先請一位組員示範拖一張**到對的群當範例"
            "（讓使用者看怎麼操作），接著請使用者自己拖一張、並在聊天說一句「為什麼這幾張"
            "是同一類」——**兩件都做到才往下**。你在旁邊看著、缺了溫和提醒就好，"
            "**不要替他拖、也不要說「我幫你」**。"
        )
    if sub_phase_id == "2.6":
        return (
            "搬問題定義進選定區是要請使用者**親自拍板**的：**先請一位組員示範搬一張**當範例，"
            "再請使用者自己把要留的搬進選定區、並在聊天說一句為什麼選它——**搬好＋說明兩件"
            "都做到才往下**。你監督、提醒，不代他搬。"
        )
    return None


# ---------------------------------------------------------------------------
# Sub-phase 主旨（中文）— Spec 04-03 v4.25 §3（新 13 關語意；舊 1.3–1.6 已隨
# Phase 42 C1 自 registry 移除）
# ---------------------------------------------------------------------------

SUB_PHASE_OBJECTIVES: dict[str, str] = {
    # 暖場 macro
    "0.0a": "破冰時間（額外用途發想）：目標導向的暖場小遊戲——大家圍繞暖場題目衝便條張數、邊貼邊聊，把腦袋打開。不分群、不分析、不套模板；目標張數看【本關訊號】。",

    # 發現階段
    "1.1a": "經驗分享：用聊天為主，每個人講自己真實遇過、跟主題有關的具體經驗；聽到有共鳴的順手貼一兩張就好——先把問題打開，不分析、不做決定。",
    "1.1b": "發想利害關係人：列出「這件事會影響到誰」。一張便條只寫名字、理由用聊天講；**先寫你自己想到的、不要抄別人或重述牆上已有的**，盡量想得廣。",
    "1.1c": "一起歸類：輪流唸自己貼的名字、口頭講「這幾張一群」，把相似的歸在一起——不動手拖，牆面會自動排好。",
    "1.1d": "排先後順序：快速幫每群標「高」「中」「低」，決定先挖誰、後挖誰。排序不是刪除——所有群都留著，也先不用寫理由。",
    "1.2": "發想痛點與情境：照排好的順序，想像每群利害關係人在什麼情況下會卡住、麻煩、受不了；在聊天聊出具體情境、站得住了再貼成便條、掛在那一群底下。",

    # 定義階段
    "2.1": "痛點歸類：把痛點從「按人掛」改成「按同一件事放」——不同人但卡在同一件事的，拖到一起。以搬動為主，先別急著貼新便條。",
    "2.2": "問題定義：把痛點寫成一句完整的話——「某使用者 需要 某需求，因為 某洞察」。輪流各寫各的、不互抄；寫前點選參考的痛點或講清楚根據；湊滿三句以上候選。",
    "2.3": "追問根源：對每句問題定義多問幾次「為什麼會這樣」，找到根源；聊定才沉澱成便條，同鏈自動排在一起。分辨講出來的是「需求」還是「解方」。",
    "2.4": "盤點現有解法：市面上已經有什麼？哪些痛點已被接住、哪些才是真正的缺口。引述既有做法可以，先不要自己冒新方案。",
    "2.5": "訂收斂準則：挑問題之前先講好「用什麼尺來量」。格式「準則：名稱｜衡量方式：怎麼量」；先湊出兩三條，等下挑選的理由要指向它們。",
    "2.6": "依準則挑問題定義：對著準則討論，把最值得做的一到三句搬進選定區，每搬一張配一張選定理由便條（寫清楚符合哪條準則）；最終由使用者拍板。",
    "2.7": "改寫設計題目：把選定的每句問題定義改寫成一句「我們可以怎麼…？」（設計題目）。一句配一張、張數＝選定數；完成後由使用者確認。",
}


def build_sub_phase_prompt(sub_phase_id: str, role: str = "crew") -> str:
    """Build the full sub-phase prompt block for assembler Layer 3.

    Phase 42 B2（spec 04-03 §3）：依 role 分流——
      - ``supervisor``：前置共用引導守則（§3.0.1）＋共通段＋該關進場語（§3.x）
      - ``crew``：共通段＋該關 crew 行為要點
    0.0a 的組長 MC／crew 樂隊 prompt 由 warmup_game.py 承載，此處不重複注入。
    """
    try:
        sp = get_sub_phase(sub_phase_id)
    except KeyError:
        return ""

    is_supervisor = role == "supervisor"

    lines: list[str] = []
    if is_supervisor:
        lines.append(SUPERVISOR_COMMON_RULES)
        lines.append("")
        # 04-03 §3.0.3：【卡住就教】所引用的教學三段式模板（懸空引用會讓 LLM 瞎掰）。
        lines.append(TEACHING_GUIDE)
        lines.append("")

    lines.append(f"## 你現在的階段：{student_facing_label(sp.name_zh)}")
    lines.append(
        "（**對參與者發言一律用白話：不要提任何內部步驟編號、英文欄位代號，"
        "也不要提「sub-phase」「講義第幾步」這些詞，更不要自稱「Supervisor」——"
        "你若是引導者請自稱「AI 引導者」或你的人設名。**）"
    )
    lines.append("")

    obj = SUB_PHASE_OBJECTIVES.get(sub_phase_id)
    if obj:
        lines.append("### 本階段目標")
        lines.append(obj)
        lines.append("")

    # 分角色內容（Phase 42 B2；0.0a 不在 ENTRY/CREW_POINTS——warmup_game 承載）
    if is_supervisor:
        entry = SUB_PHASE_ENTRY.get(sub_phase_id)
        if entry:
            lines.append(entry)
            lines.append("")
    else:
        crew_points = SUB_PHASE_CREW_POINTS.get(sub_phase_id)
        if crew_points:
            lines.append(crew_points)
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

    # Phase 41：發散/收斂軟性護欄（取代沉默模式）。依 phase_intent 注入。
    guardrail = _phase_intent_guardrail(sub_phase_id)
    if guardrail:
        lines.append("### 這個階段怎麼貼便條")
        lines.append(guardrail)
        lines.append("")

    # Phase 42 D1d（#26/#27）：移動格（2.1/2.6）帶真人「拖＋說」的鷹架（組長限定）——
    # 配合 G01 真人硬閘（硬格真人未動手不放行），教組長「crew 先示範→請真人做→監督非代勞」。
    if is_supervisor:
        scaffold = _move_grid_human_scaffold(sub_phase_id)
        if scaffold:
            lines.append("### 帶使用者動手（這一關要請他親自做）")
            lines.append(scaffold)
            lines.append("")

    # Zones — Phase 42 補正 R3（P1-5）：C1 清空框標題後 title_sticky 恆空、
    # allowed_colors 是 #34 後的失效欄位——舊寫法每關注入「- （可用顏色：…）」
    # 無名死條目。改讀 ZONE_NAMES_ZH（牆面 in-scene 短名單一來源），不再展示顏色。
    if sp.zones:
        zone_names = [
            ZONE_NAMES_ZH.get(zone_id)
            for zone_id in sp.zones
            if ZONE_NAMES_ZH.get(zone_id)
        ]
        if zone_names:
            lines.append("### 你可以寫便條的牆面")
            for name in zone_names:
                lines.append(f"- {name}")
            lines.append("")

    # Templates
    if sp.templates:
        lines.append("### 便條紙文字格式")
        lines.append("（下面的標題只是分類名，**不要把標題或代號抄進便條內容**，便條只寫實際內容）")
        for tpl_id in sp.templates:
            prompt = get_template_prompt(tpl_id)
            if prompt:
                # 用學生友善名，不漏 raw template id（如 scope_rationale）到便條/聊天。
                lines.append(f"**{get_template_name(tpl_id)}**：")
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
        "- `create_note(text, position?, group_id?)` — 顏色由系統依作者決定，不用指定"
    )
    lines.append("- `move_note(note_id, to)`")
    lines.append("- `edit_note(note_id, text)` — 不能改顏色")
    lines.append("- `delete_note(note_id)`")
    if is_supervisor:
        lines.append("- `draw_zone` — 可建立新區域（引導者限定）")
        # Phase 42 C2（C0 裁定⑤）：2.6 開選定區的工具 affordance——沒講清楚這個工具，
        # 組長只會卡在 time-box 兜底（spec 25 §3.2 / 27 §14）。
        if sub_phase_id == "2.6":
            lines.append(
                "- `open_section(title)` — 在白板最下面開一條新的「選定區」帶"
                "（引導者限定；位置由系統決定，你只給標題）。開完要在聊天講清楚："
                "把談定要做的一到三句問題定義用 `move_note(note_id, to=\"section:<新區id>\")` "
                "**親自搬進去（別只在聊天說選這個）**，每搬一張配一張"
                "`create_note(text=\"選定｜符合準則：〔準則名稱〕——〔為什麼選它〕\", "
                "position=\"section:<新區id>\", cites=[\"準則id\",\"問題定義id\"])` 選定理由便條"
                "——準則名稱要寫準則區**真的有的那一條**（開頭的「選定｜」不能省），"
                "先請一位組員示範搬一張。"
            )
    # Phase 42 D1a：逐關工具 affordance（cites / group_id 用法；診斷 §4 唯一真落差）。
    for hint in _tool_affordance_hints(sub_phase_id):
        lines.append(hint)
    lines.append("- `chat_message(text)` — 可正常使用（reveal_round 揭示輪需輪到你才講）")
    lines.append("")

    return "\n".join(lines)


def list_zones_for_sub_phase(sub_phase_id: str) -> list[str]:
    """List zone ids active for the given sub-phase."""
    try:
        sp = get_sub_phase(sub_phase_id)
    except KeyError:
        return []
    return list(sp.zones)

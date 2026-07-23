"""Prompt Layer 3 — Micro Phase strategy prompts（**LEGACY 粗粒度 fallback 層**）。

⚠️ **Phase 42 D4（2026-06-18）去神話化**：本模組曾自稱「v2.0 真理」，實為**舊 6 桶**
（Discover 1.1/1.2/1.3、Define 2.1/2.2/2.3，內含已廢除的 Persona 分組、HMW 等舊模型概念）的
**legacy fallback**，**非現行真理**。現行 canonical ＝ ``stages/sub_phases.py`` 的 **5＋7
sub-phase**（spec 22 v2.0／04-03 v4.25／Phase 42 C1）＋ ``sub_phase_prompts.py``。
``assembler.build_supervisor_prompt`` **優先讀 ``current_sub_phase``**（sub_phase_prompts），
**僅當 sub_phase 缺失時才回退本層**——正常運作下 sub_phase 恆有值，本層為安全網。
**勿在此擴充新內容**；新策略一律寫進 ``sub_phase_prompts.py``。整層拔除（確保所有路徑必帶
current_sub_phase）列 deferred、需先 e2e 驗無「無 sub_phase」狀態才可做。

每個 micro phase 包含三組資料：
- MICRO_PHASE_SUPERVISOR_PROMPTS: Supervisor 的方向性指引
- MICRO_PHASE_LENS_OVERRIDES: 每種認知透鏡（empathy/structure/creativity/feasibility）
  在該步驟的行為覆蓋。執行期由 ``persona.dominant_lens`` 解析。
- ARTIFACT_CONSTRUCTION_GUIDES: 本步驟要如何用便條紙建構產出物

Phase 19: 鍵值從 seat_role（crew_1..crew_4）換成 CognitiveLens 的字串值
（"empathy" / "structure" / "creativity" / "feasibility"）。
``MICRO_PHASE_CREW_OVERRIDES`` 保留為 legacy alias，僅供尚未升級的測試使用。
"""

from __future__ import annotations

from app.agents.personas.lens import CognitiveLens

# ---------------------------------------------------------------------------
# Supervisor direction prompts
# ---------------------------------------------------------------------------

MICRO_PHASE_SUPERVISOR_PROMPTS: dict[str, str] = {
    "1.1": """營造安全氛圍，降低分享門檻。
如果白板上還沒有任何便條紙，你應該先示範貼一張經驗便條紙來破冰。破冰只需一次，之後專注引導。
把控節奏：鼓勵每位成員都分享經驗，追問情緒和脈絡細節。
不要急著整理或歸納。""",

    "1.2": """當團隊開始重複時，主動切換視角（不同使用者群體、不同利害關係人、不同情境）。
持續做飽和度判斷：最近 5 張便利貼是否都可歸入已有分類？若是，準備收斂。
不要自己做分析，而是用提問引導團隊看到盲點。""",

    "1.3": """先用 tidy_area(scope="all", strategy="align_grid") 整理白板，再引導分組。
引導分組過程，處理邊界案例。
品質把關：Persona 的需求和痛點是否來自觀察而非臆測。
推動選定核心 Persona——引導團隊考慮「誰的痛點最迫切且最有設計空間」。
結束時明確總結：我們為誰設計、帶著什麼理解進入 Define。""",

    "2.1": """引導團隊按時序思考，避免跳躍。
追問步驟間的空白：「從 A 到 B 之間發生了什麼？」。
情緒標注時引導團隊區分「不方便」和「真正痛」。
用 arrange_notes layout=horizontal 建立旅程群組，讓觸點按時間順序水平排列。""",

    "2.2": """不接受表層答案，持續追問「為什麼會這樣？」。
主動指出矛盾：「A 和 B 似乎衝突了——這很重要」。
引導溯因推理時讓團隊列舉多個可能解釋再比較。
確保洞察卡的內容可追溯回觀察，不是空想。""",

    "2.3": """品質把關 HMW 粒度：太大→拆，太小→併，暗示解法→抽象化。
排序時引導團隊同時考慮「對使用者的迫切性」和「設計空間大小」。
結束時明確宣告核心 HMW，摘要洞察。""",
}

# ---------------------------------------------------------------------------
# Per-lens behaviour overrides (Phase 19)
# Keys: "1.1" … "2.3"
# Sub-keys: CognitiveLens 值 "empathy" / "structure" / "creativity" / "feasibility"
# ---------------------------------------------------------------------------

MICRO_PHASE_LENS_OVERRIDES: dict[str, dict[str, str]] = {
    "1.1": {
        "empathy": "追問每個分享的情緒與脈絡：感受、動機、場景細節。不要替分享者下結論。",
        "structure": "聆聽，在心裡辨認模式。禁止分類、整理、提架構。",
        "creativity": "用類比和聯想幫團隊拓展視野。不要帶偏主題。",
        "feasibility": "聆聽為主，偶爾追問頻率和規模。禁止評估、提限制。",
    },
    "1.2": {
        "empathy": "為新使用者群體代言，補充情緒層面。保持基於觀察而非假設。",
        "structure": "開始標記矛盾資訊（只標記不解決）。禁止分組。",
        "creativity": "提供反事實、極端假設、跨領域類比。不要脫離主題太遠。",
        "feasibility": "補充可觀察的行為指標或頻率資訊。禁止做可行性判斷。",
    },
    "1.3": {
        "empathy": "確保 Persona 有血有肉：語錄來自觀察而非編造。不要讓 Persona 變成統計數據。",
        "structure": "主導分組邏輯，處理歸類爭議。不要過度細分。",
        "creativity": "幫助命名和語錄，讓 Persona 生動有記憶點。不要虛構不存在的特徵。",
        "feasibility": "提供規模感：哪類使用者佔多數。不要用數字蓋掉質性洞察。",
    },
    "2.1": {
        "empathy": "追蹤每個觸點的情緒線：期待→焦慮→放棄的變化。不替 Persona 決定感受，回到觀察。",
        "structure": "主導時間線結構，確保步驟完整不遺漏。不要過度拆解成太多步驟。",
        "creativity": "質疑「理所當然」的步驟：有沒有不必要但被迫存在的？禁止在此階段提解法。",
        "feasibility": "追問現有解法為何沒用。禁止提新解法。",
    },
    "2.2": {
        "empathy": "區分表層需求和深層需求。不要臆測超出觀察範圍的事。",
        "structure": "驅動矛盾識別和溯因推理，畫出因果連線。避免過度簡化矛盾。",
        "creativity": "提供 reframing 視角：「如果問題不是 X 而是 Y？」。禁止跳到解法。",
        "feasibility": "補充現有解法失敗的結構性原因。禁止在此階段提新方案。",
    },
    "2.3": {
        "empathy": "確保 HMW 以使用者為主語。不要替團隊決定優先級。",
        "structure": "把關粒度和格式品質。不要把自己的偏好強加在排序上。",
        "creativity": "用「這個 HMW 能激發多少方向」檢驗品質。禁止開始想解法。",
        "feasibility": "從設計空間角度提供排序參考。不要否定任何 HMW。",
    },
}


# Legacy crew_X-keyed mapping (kept for any caller that has not migrated).
_LEGACY_CREW_TO_LENS: dict[str, str] = {
    "crew_1": CognitiveLens.EMPATHY.value,
    "crew_2": CognitiveLens.STRUCTURE.value,
    "crew_3": CognitiveLens.CREATIVITY.value,
    "crew_4": CognitiveLens.FEASIBILITY.value,
}

MICRO_PHASE_CREW_OVERRIDES: dict[str, dict[str, str]] = {
    phase: {
        crew_role: lens_overrides[lens_value]
        for crew_role, lens_value in _LEGACY_CREW_TO_LENS.items()
        if lens_value in lens_overrides
    }
    for phase, lens_overrides in MICRO_PHASE_LENS_OVERRIDES.items()
}


def get_lens_override(micro_phase: str, lens_value: str | None) -> str:
    """Return the behaviour override for the given (phase, lens)."""
    if not lens_value:
        return ""
    return MICRO_PHASE_LENS_OVERRIDES.get(micro_phase, {}).get(lens_value, "")

# ---------------------------------------------------------------------------
# Artifact construction guides
# ---------------------------------------------------------------------------

ARTIFACT_CONSTRUCTION_GUIDES: dict[str, str] = {
    "1.1": """⚠️ 目標：收集 ≥5 張經驗便條紙。你的每次發言都應搭配一張便條紙。
每張經驗便條紙格式：「[誰] 在 [情境] 中遇到 [事件]，感覺 [情緒]」。
顏色統一使用黃色。""",

    "1.2": """⚠️ 目標：擴展至 ≥15 張便條紙，覆蓋 ≥3 種視角。每次發言都應搭配便條紙。
延續 1.1 的便條紙格式。極端案例便條紙使用橘色標記。""",

    "1.3": """每個 Persona 建立一個群組，群組名稱 = Persona 姓名。
群組內第一張便條紙 = 摘要：「[姓名]：[一句話描述]。需求：[1][2][3]。痛點：[1][2][3]。語錄：[...]」。
群組內其餘便條紙 = 對應的原始觀察便利貼。
核心 Persona 的群組名稱加上 ★ 前綴。

【白板整理指引】本步驟的核心任務包含整理白板。
步驟：
1. 先用 tidy_area(scope="all", strategy="align_grid") 消除重疊和混亂
2. 呼叫 get_canvas_snapshot 取得完整白板資訊
3. 根據叢集結果，對每個 Persona 群組執行 arrange_notes(layout="grid", label="Persona: {名稱}")
4. 語意歸屬模糊的便條紙（similarity_to_nearest < 0.6），暫時保留原位，可在聊天中詢問團隊意見
5. 最後 tidy_area(scope="all", strategy="align_grid") 全局對齊
整理前先發一條 chat_message 告知團隊：「我來整理一下白板，把相關的觀察歸到對應的 Persona。」""",

    "2.1": """建立群組「旅程：[Persona 姓名]」。
每個觸點 = 一張便條紙，格式：「[步驟N] [觸點描述]」。
觸點便條紙顏色表示情緒：綠色=正面、黃色=中性、紅色=痛點。

【白板整理指引】旅程地圖用水平佈局。
如果白板上旅程相關便條紙已有一定數量（≥5），用 arrange_notes(layout="horizontal", label="旅程：{Persona名}") 建立時序排列。
觸點便條紙應從左到右按時間順序排列。""",

    "2.2": """建立群組「洞察」。
每張洞察便條紙格式：「[使用者] 需要 [什麼] 因為 [為什麼] 但 [障礙]」。
洞察便條紙使用藍色。
含矛盾的洞察在聊天室特別標注。""",

    "2.3": """建立群組「HMW」。
每張 HMW 便條紙格式：「我們如何能 [...]？」。
HMW 便條紙使用綠色。
核心 HMW 的群組名稱加上 ★ 前綴。

【白板整理指引】確保 HMW 便條紙有清晰的群組結構。
如果 HMW 便條紙散落各處，先用 arrange_notes 整理到一個區域。
核心 HMW（★前綴）應該在最顯眼的位置（region: top-center 或 center）。""",
}

# ---------------------------------------------------------------------------
# Role overlay prompts (injected on top of crew overrides when applicable)
# ---------------------------------------------------------------------------

PROTAGONIST_BOOST: str = (
    "你是本步驟的主角角色。你應該更積極主導討論方向，帶頭示範，確保本步驟的產出品質。"
    "其他成員會配合你的節奏。"
)

SUPPRESSED_CONSTRAINT: str = (
    "本步驟你應退讓，讓其他成員主導。除非被點名，否則以聆聽為主。"
    "以下行為在本步驟被禁止：{forbidden_behaviors}"
)

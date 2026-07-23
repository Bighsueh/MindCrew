"""Text templates — spec 23 v2.0 便條紙文字模板（Phase 42 C2）。

每個模板：
  - regex            驗證便條文字是否符合
  - prompt_zh        AI prompt 用的中文描述
  - example          合法範例
  - forbidden_terms  禁字列表（v2.0 新增，大小寫不敏感）：命中即不通過，
                     用於擋英文縮寫／機制行漏上白板（#25/#29）

現役第一鑽石模板（spec 23 v2.0）：
  stakeholder（只寫名字）/ problem_statement（問題定義，需求句 OR 五要件句）/
  problem_candidate（主題群標籤）/ criteria（收斂準則）/ selection_reason（選定理由）/
  hmw（設計題目「我們可以怎麼…？」）

Phase 42 C2 移除死模板：scope_rationale / raw_observation / pov（併入 problem_statement）
／task_question（0.2 整格移除，spec 22 v2.0 §2.2）。persona_*（Persona 工具）隨 1.6
整格移除標記廢除，清理併入 D4（tool_status 1.6 死分支同批）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextTemplate:
    """Sticky-note text template definition."""

    id: str
    name_zh: str
    pattern: re.Pattern[str]
    prompt_zh: str
    example: str
    required_refs: tuple[str, ...] = ()  # 例：("obs",) 表示需要 cites: #obs-X
    # spec 23 v2.0：禁字列表（大小寫不敏感）。命中即不通過——防英文縮寫與機制行
    # 漏上白板（#25/#29）；reason_zh 用大白話引導、不得把禁字規則本身講出來。
    forbidden_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateResult:
    passed: bool
    template_id: str | None = None
    reason_zh: str | None = None


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, TextTemplate] = {
    "stakeholder": TextTemplate(
        id="stakeholder",
        name_zh="利害關係人",
        # Phase 42 C1（spec 23 v2.0 §8.1）：簡化為**只寫名字**——便條只寫這個人
        # （或這群人）的名字，「為什麼相關」在聊天講（保住發想廣度、便條不被理由
        # 拖慢）。單行短文字 1–30 字、禁「｜」欄位分隔；去重在貼上時 enforce
        # （spec 27），與本模板無關。舊「｜為什麼相關：…」格式（2026-06-08 盲測
        # 修正版）作廢。
        pattern=re.compile(r"^[^\n｜]{1,30}$"),
        prompt_zh=(
            "格式：只寫這個人（或這群人）的名字就好，為什麼跟這件事有關用聊天講。\n"
            "範例：超市收銀員"
        ),
        example="超市收銀員",
    ),
    "criteria": TextTemplate(
        id="criteria",
        name_zh="收斂準則",
        pattern=re.compile(r"準則[:：].+｜衡量方式[:：].+", re.DOTALL),
        prompt_zh="格式：準則：[名稱]｜衡量方式：[如何量]",
        example="準則：時間可行性｜衡量方式：能否在 2 小時內完成原型",
    ),
    # spec 23 v2.0 §2.4：設計題目＝「我們可以怎麼…？」一句話。in-scene 一律稱
    # 「設計題目」（#25）。from 關聯改系統層（cites→選定問題定義），不寫機制行；
    # forbidden_terms 擋英文縮寫與「from:」機制行漏上白板。
    "hmw": TextTemplate(
        id="hmw",
        name_zh="設計題目",
        pattern=re.compile(r"我們可以怎麼.+[?？]", re.DOTALL),
        forbidden_terms=("HMW", "POV", "from:", "from："),
        prompt_zh=(
            "格式：把選好的問題定義，改寫成一句「我們可以怎麼…？」的問句。\n"
            "寫的時候，點選它對應的那張問題定義便條。"
        ),
        example="我們可以怎麼讓袋子在出門那一刻自己出現在手邊？",
    ),
    # spec 23 v2.0 §2.5：選定理由＝「選定＋符合準則：…」，必指 ≥1 條 2.5 準則。
    # 2.6 收口閘要件（spec 25 v2.0 §3.2 selection_pairing）：選定區每張問題定義配一張。
    "selection_reason": TextTemplate(
        id="selection_reason",
        name_zh="選定理由",
        pattern=re.compile(r"選定.*符合準則[:：].+", re.DOTALL),
        prompt_zh=(
            "格式：選定｜符合準則：〔準則名稱〕——〔一句話說明為什麼這張最符合〕\n"
            "理由一定要對上我們在前一關訂好的準則，不能憑感覺。\n"
            "貼的時候，點選它對應的那張問題定義便條。\n"
            "（AI 請注意：這張要**貼進選定區**——`position=\"section:<選定區的實際id>\"`；"
            "`cites` 要**同時**帶「那張問題定義的 id」和「你依據的準則便條 id」，"
            "少了問題定義的 id 就配不成對、閘門不會過。）"
        ),
        example="選定｜符合準則：影響範圍——出門前就忘了帶是最多人卡住的地方，解決它能幫到最多人",
    ),
    # Phase 29 (spec/04-06 §4.10): idea / hypothesis / task_ticket / direction

    # ── Phase 31 三大工具：Persona Card 四欄位（舊 DT user persona）——
    # Phase 42 收尾整批移除（persona 不在 POC，spec 22 v2.0 §12.5 / spec 23 §5.1）。
    # validate_template 對未知 template_id 回 passed=True，移除後無 KeyError。

    # ── Phase 31 三大工具：Problem Statement 五要件 (spec/23 §2.2) ─
    # 對應講義「對於X而言，在Y中，他/她常遇到Z，因為W，因此需要V。」句型。
    # 2.2 sub_phase 啟用。一張便條 = 一個 PS（不像 persona 四欄位）。
    # spec 23 v2.0 §2.2：問題定義（工具②）。v2.0 合併 pov＋problem_statement 為單一
    # 模板（兩種句型擇一）。in-scene 一律稱「問題定義」，不講「Problem Statement」「POV」
    # （#25）。來源關聯改 cites（≥2 筆痛點，2.2 計入條件由 artifact_gate enforce），
    # 便條文字不寫引用行。
    "problem_statement": TextTemplate(
        id="problem_statement",
        name_zh="問題定義",
        # 兩種句型擇一匹配；五要件句沿用 v1.0 容錯（全/半形逗號句號、
        # 「在 X 中/時/上」可省、他/她/他她、常遇到/常會/會/遇到）。
        pattern=re.compile(
            r"(?:.+?\s*需要\s*.+?[，,]\s*因為\s*.+"
            r"|對於.+?而言[，,]\s*在.+?[中時上]?[，,]\s*"
            r"(?:他[/／]?她|她|他)\s*常?\s*(?:會|遇到)\s*.+?[，,]\s*"
            r"因為.+?[，,]\s*因此需要.+?[。\.])",
            re.DOTALL,
        ),
        prompt_zh=(
            "格式（兩種寫法選一種）：\n"
            "  某使用者 需要 某需求，因為 某洞察\n"
            "或完整版：\n"
            "  對於〔誰〕而言，在〔情境〕中，他常遇到〔困難〕，因為〔原因〕，因此需要〔真正需要〕。\n"
            "寫的時候，點選你參考的那幾張痛點便條（至少兩張），讓大家知道這句是從哪些痛點來的。"
        ),
        example=(
            "常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，"
            "因為 他們不是不想帶，是想到的時候人已經在店裡了"
        ),
    ),

    # spec 23 v2.0 §2.3：主題群標籤（2.1 啟用）。v1.0「痛點候選」語意作廢——2.1 不再
    # 產新痛點，而是把痛點按主題橫切歸類、幫每群下一個主題名稱的標籤便條（kind=label）。
    "problem_candidate": TextTemplate(
        id="problem_candidate",
        name_zh="主題群標籤",
        pattern=re.compile(r"^[^\n｜]{2,15}$"),
        prompt_zh="格式：幫這一群痛點取一個大家看得懂的主題名稱（一句短語）。",
        example="出門前就忘了帶",
    ),
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def validate_template(text: str, template_id: str) -> TemplateResult:
    """Validate text against the named template (regex only, no DB lookup)."""
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        return TemplateResult(passed=True, template_id=template_id)

    if not text or not text.strip():
        return TemplateResult(
            passed=False,
            template_id=template_id,
            # 用具體 example、不 dump prompt_zh（含 [原話]/[受訪者代號] 等內部佔位符），
            # 否則格式校驗訊息會把內部格式規則漏到學生聊天室（盲測 2026-06-09）。
            reason_zh=f"這張便條是空的，可以參考這樣寫：{tpl.example}",
        )

    if not tpl.pattern.search(text):
        return TemplateResult(
            passed=False,
            template_id=template_id,
            reason_zh=f"這張「{tpl.name_zh}」便條的寫法再調整一下，可以參考：{tpl.example}",
        )

    # spec 23 v2.0：禁字檢查（大小寫不敏感）。reason_zh 用大白話引導＋example，
    # 不得把禁字規則本身講出來（#29，例：不講「不能寫 HMW」）。
    if tpl.forbidden_terms:
        upper = text.upper()
        if any(term.upper() in upper for term in tpl.forbidden_terms):
            return TemplateResult(
                passed=False,
                template_id=template_id,
                reason_zh=f"這張「{tpl.name_zh}」便條直接用大白話寫就好，可以參考：{tpl.example}",
            )

    return TemplateResult(passed=True, template_id=template_id)


# Spec 14 A6 / N4: cite-id 存在性驗證
_REF_PATTERNS: dict[str, re.Pattern[str]] = {
    "obs": re.compile(r"cites?[:：]\s*((?:#?obs[-_]\S+\s*[,，]?\s*)+)", re.IGNORECASE),
    "pov": re.compile(r"from[:：]\s*(#?pov[-_]\S+)", re.IGNORECASE),
    "hmw": re.compile(r"for[:：]\s*(#?hmw[-_]\S+)", re.IGNORECASE),
    # Phase 29: hyp ref removed alongside hypothesis template.
}


def _extract_ref_ids(text: str, ref_type: str) -> list[str]:
    """從文字中抽出 ref id（去 # 前綴，trim 空白）。"""
    pat = _REF_PATTERNS.get(ref_type)
    if not pat:
        return []
    m = pat.search(text)
    if not m:
        return []
    blob = m.group(1)
    raw_ids = re.split(r"[,，\s]+", blob)
    out: list[str] = []
    for raw in raw_ids:
        rid = raw.strip().lstrip("#").strip()
        if rid:
            out.append(rid)
    return out


async def validate_template_with_canvas(
    text: str,
    template_id: str,
    project_id,
) -> TemplateResult:
    """完整驗證：regex + canvas 查 cite id 存在性。

    Phase 17 audit G2 修補：spec 規定 cite 必須能 traceback 到真實便條。
    """
    base = validate_template(text, template_id)
    if not base.passed:
        return base

    tpl = TEMPLATES.get(template_id)
    if tpl is None or not tpl.required_refs:
        return base

    # 抽出所有 ref，去 canvas 查存在性
    all_ids: list[tuple[str, str]] = []  # (ref_type, id)
    for ref_type in tpl.required_refs:
        for rid in _extract_ref_ids(text, ref_type):
            all_ids.append((ref_type, rid))

    if not all_ids:
        return TemplateResult(
            passed=False,
            template_id=template_id,
            reason_zh=f"{tpl.name_zh} 缺引用 id（required_refs={tpl.required_refs}）",
        )

    # 查 canvas 便條 id
    try:
        from app.canvas.analyzer import get_spatial_analyzer
        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        existing_ids: set[str] = {n.id for n in analysis.notes}
    except Exception:
        # 無法查時保守 pass（避免擋住流程）
        return base

    missing = [rid for _, rid in all_ids if rid not in existing_ids]
    if missing:
        return TemplateResult(
            passed=False,
            template_id=template_id,
            reason_zh=f"{tpl.name_zh} 引用的 id 不存在於 canvas：{', '.join(missing)}",
        )

    return TemplateResult(passed=True, template_id=template_id)


def get_template_prompt(template_id: str) -> str | None:
    tpl = TEMPLATES.get(template_id)
    return tpl.prompt_zh if tpl else None


def get_template_name(template_id: str) -> str:
    """便條模板的學生友善名（避免把 raw template id 如 `scope_rationale` 漏給學生看）。"""
    tpl = TEMPLATES.get(template_id)
    return tpl.name_zh if tpl else template_id


def list_templates() -> list[str]:
    return list(TEMPLATES.keys())

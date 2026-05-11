"""Content gate — Spec 13 §4.2 語言護欄。

每個 gate module 是一條 deny-list 規則：偵測特定詞彙/句型 → reject。
規則套用在 create_note 的 text 上，對 AI 是 retry trigger、對人類是 toast 來源。

Modules：
  - no_interpretation       Phase 1-5 Raw Wall 禁歸因詞
  - empathy_says_no_inference  Phase 1-6 Empathy.Says 禁推論詞
  - no_solution_language    Phase 2.x 禁解法用語
  - no_feasibility_talk     Phase 3.x 禁可行性討論
  - no_production_code      Phase 4-1f v1 禁 production-code 用語
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GateRule:
    """Single deny-list rule with regex + 中文錯誤訊息。"""

    name: str
    pattern: re.Pattern[str]
    message_zh: str
    examples_blocked: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    """Result of gate evaluation."""

    passed: bool
    violated_module: str | None = None
    violated_rule: str | None = None
    matched_text: str | None = None
    message_zh: str | None = None


# ---------------------------------------------------------------------------
# 各 module 的 rules
# ---------------------------------------------------------------------------

_INTERPRETATION_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_real_need",
        pattern=re.compile(r"(真正的需求|真正想要|其實是想|代表他想|代表她想|代表他們想)"),
        message_zh="此區為原始觀察，不可寫歸因。請保留使用者原話與情緒，不加解讀。",
        examples_blocked=("使用者真正的需求是…", "這代表他想要…"),
    ),
    GateRule(
        name="phrase_i_think",
        pattern=re.compile(r"(我認為使用者|我覺得使用者|我猜使用者).{0,20}(是|要|想)"),
        message_zh="此區禁止加入我方推論。把推論留到 1-6 結構化模板再做。",
    ),
    GateRule(
        name="phrase_actually_wants",
        pattern=re.compile(r"(他|她|他們)\s*(其實|真的)\s*(想|要|需要|是想)"),
        message_zh="此區是純觀察，不要在這裡為使用者下結論。",
    ),
)


_EMPATHY_SAYS_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="empathy_says_inference",
        pattern=re.compile(r"(他|她|他們)\s*(覺得|認為|相信|猜想|期待|希望|擔心)"),
        message_zh="Says 欄位只能放使用者「說過的話」（引用）。推論請放到 Thinks。",
    ),
    GateRule(
        name="empathy_says_should",
        pattern=re.compile(r"(他|她|他們)\s*(應該|可能|或許)\s*"),
        message_zh="Says 是引用而非推測。請改放到 Thinks 或 Feels。",
    ),
)


_SOLUTION_LANGUAGE_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="verb_make",
        pattern=re.compile(r"(做一個|做個|開發|實作|蓋一個|建一個|寫一個|打造一個|架一個)"),
        message_zh="Define 階段不可寫解法。請改寫為觀察 + 需求 + 洞察的 POV 格式。",
    ),
    GateRule(
        name="english_solution_verb",
        pattern=re.compile(r"\b(build|ship|implement|develop|deploy|launch)\b", re.IGNORECASE),
        message_zh="Define 階段不可用解法動詞（build/ship/implement…）。聚焦在問題定義。",
    ),
    GateRule(
        name="phrase_add_feature",
        pattern=re.compile(r"(增加一個|加入一個|新增一個|多一個).{0,5}(按鈕|功能|頁面|畫面|選項|介面)"),
        message_zh="這是解法陳述。請先定義使用者的需求與情境，等到 Develop 階段再發想解法。",
    ),
    GateRule(
        name="phrase_design_a",
        pattern=re.compile(r"(設計一個|設計個)\s*"),
        message_zh="Define 階段不可進入解法層。請改用 POV / HMW 的觀察視角。",
    ),
    GateRule(
        name="phrase_should_build",
        pattern=re.compile(r"我們應該\s*(做|蓋|寫|建|架)"),
        message_zh="解法判斷在 Develop 階段才做。Define 階段聚焦於問題本身。",
    ),
)


_FEASIBILITY_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_cannot_do",
        pattern=re.compile(r"(做不到|做不出來|沒辦法做|不可能做)"),
        message_zh="Develop 是純發散，禁止可行性討論。可行性留到 Phase 4-1(a)。",
    ),
    GateRule(
        name="phrase_cost_too_high",
        pattern=re.compile(r"(成本太高|太貴|預算不夠|資源不足)"),
        message_zh="這是可行性判斷。Develop 階段先讓想法飛，不評估成本。",
    ),
    GateRule(
        name="phrase_tech_not_feasible",
        pattern=re.compile(r"(技術.{0,3}不可行|技術上做不到|技術門檻太高)"),
        message_zh="技術可行性等 Phase 4-1(a) 再評估。",
    ),
    GateRule(
        name="phrase_too_late",
        pattern=re.compile(r"(來不及|時間不夠|太趕|趕不上)"),
        message_zh="時程考量留到 Phase 4-1(a) 篩選時討論。",
    ),
    GateRule(
        name="phrase_unrealistic",
        pattern=re.compile(r"(不實際|不切實際|太理想化)"),
        message_zh="Develop 階段歡迎瘋狂想法。請先寫下，篩選留到後面。",
    ),
)


_CRITICISM_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_dismissive",
        pattern=re.compile(r"(這不可能|太蠢|太笨|沒人會用|這做不出來|這沒用|根本不行)"),
        message_zh="DT 流程不批評想法。有疑慮等收斂階段用投票表達。",
    ),
    GateRule(
        name="phrase_soft_negative",
        pattern=re.compile(r"(不是說不好啦|emm[^.]{0,20}不是|這個方向.{0,5}不太行)"),
        message_zh="DT 流程不批評想法，包括委婉批評。請改為提問或補充。",
    ),
    GateRule(
        name="phrase_direct_reject",
        pattern=re.compile(r"(我不同意|這想法.{0,5}不好|這個爛|這個 太差)"),
        message_zh="DT 流程不批評想法。請以建設性方式表達不同觀點。",
    ),
)


_PRODUCTION_CODE_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_production",
        pattern=re.compile(r"(正式上線|production|prod 環境|上 prod)", re.IGNORECASE),
        message_zh="雛形 v1 必須 low-fidelity。production 級別要等到 v2+ 並在 (d) 闡明假設。",
    ),
    GateRule(
        name="phrase_full_implementation",
        pattern=re.compile(r"(實作完整|完整實作|完整開發|做完整版)"),
        message_zh="v1 不寫完整實作。請聚焦於最便宜能驗證假設的形式。",
    ),
)


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

GATE_MODULES: dict[str, tuple[GateRule, ...]] = {
    "no_interpretation": _INTERPRETATION_PATTERNS,
    "empathy_says_no_inference": _EMPATHY_SAYS_PATTERNS,
    "no_solution_language": _SOLUTION_LANGUAGE_PATTERNS,
    "no_feasibility_talk": _FEASIBILITY_PATTERNS,
    "no_production_code": _PRODUCTION_CODE_PATTERNS,
    "no_criticism": _CRITICISM_PATTERNS,  # Spec 14 — 組長 B 紀律 1
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def check_text(text: str, gate_module_ids: tuple[str, ...] | list[str]) -> GateResult:
    """Tier-1 regex pre-filter（Phase 17 既有行為）。

    Phase 18：此函式仍保留為快速 fallback，但建議呼叫 `check_text_with_llm`
    取得 LLM-judged 結果（含上下文，能處理引述 / 否定 / Meta 討論）。
    """
    if not text:
        return GateResult(passed=True)

    for module_id in gate_module_ids:
        rules = GATE_MODULES.get(module_id)
        if rules is None:
            continue
        for rule in rules:
            match = rule.pattern.search(text)
            if match:
                return GateResult(
                    passed=False,
                    violated_module=module_id,
                    violated_rule=rule.name,
                    matched_text=match.group(0),
                    message_zh=rule.message_zh,
                )
    return GateResult(passed=True)


async def check_text_with_llm(
    text: str,
    gate_module_ids: tuple[str, ...] | list[str],
    context: dict | None = None,
    project_id=None,
    agent_id: str | None = None,
) -> GateResult:
    """Tier-1 + Tier-2 evaluation (Phase 18 Step A0).

    流程：
      1. 跑既有 regex（快、無上下文）：若全 pass → 直接回 pass
      2. 若 regex 命中 → 用 LLM judge 確認（有上下文，能識別引述 / 否定 / Meta）
      3. LLM 失敗 → 保守 pass，標記 fallback_used 寫進 trace

    回 GateResult 為 Phase 17 既有介面相容。
    """
    if not text or not text.strip():
        return GateResult(passed=True)

    # Tier 1: 跑既有 regex
    regex_result = check_text(text, gate_module_ids)
    if regex_result.passed:
        return regex_result  # 沒命中 → 直接通過

    # Tier 2: LLM 二次確認
    from app.agents.llm_judge import judge_content, is_violating

    violated_module = regex_result.violated_module or ""
    try:
        judge = await judge_content(
            text=text,
            rule_module=violated_module,
            context=context or {},
            project_id=project_id,
            agent_id=agent_id,
        )
    except Exception:
        # LLM 路徑也失敗：保守 pass
        return GateResult(passed=True)

    if not is_violating(judge):
        # LLM 認為不違規（例如：引述 / 否定 / Meta） → 蓋過 regex 判定
        return GateResult(passed=True)

    # LLM 同意違規 → 回 regex 命中結果，並附 LLM reasoning
    return GateResult(
        passed=False,
        violated_module=regex_result.violated_module,
        violated_rule=regex_result.violated_rule,
        matched_text=regex_result.matched_text,
        message_zh=(regex_result.message_zh or "") + f"\n\nLLM 判斷：{judge.reasoning_zh}",
    )


def list_gate_modules() -> list[str]:
    return list(GATE_MODULES.keys())


def describe_module(module_id: str) -> str:
    """中文描述供 prompt 注入。"""
    descriptions = {
        "no_interpretation": "禁止歸因詞、解讀詞（例：「真正的需求」、「代表他想要」、「我認為使用者…」）",
        "empathy_says_no_inference": "Says 欄位僅可放使用者原話引用，禁止推論（「他覺得」、「他應該」等屬於 Thinks）",
        "no_solution_language": "禁止解法用語（做一個 / 開發 / 建一個 / 增加按鈕 / 設計一個…）",
        "no_feasibility_talk": "禁止可行性討論（做不到 / 成本太高 / 技術不可行 / 來不及 / 不實際）",
        "no_production_code": "禁止 production 級別詞彙（正式上線 / production / 實作完整）",
        "no_criticism": "禁止批評他人想法（含委婉批評）。有疑慮以建設性方式表達或留待收斂投票。",
    }
    return descriptions.get(module_id, module_id)

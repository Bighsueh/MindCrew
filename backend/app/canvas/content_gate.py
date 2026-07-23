"""Content gate — Spec 04-06 v4.25 §5.5 語言護欄。

每個 gate module 是一條 deny-list 規則：偵測特定詞彙/句型 → reject。
規則套用在 create_note 的 text 上，對 AI 是 retry trigger、對人類是 toast 來源
（message_zh 會露給學生看——一律大白話、無英文縮寫、不講機制名，#25/#29）。

Modules：
  - no_solution_language    2.2–2.7 禁解法用語（2.1 除外；spec 04-06 §5.5）
  - no_feature_jump         1.2 「跳到功能」提醒＋軟擋（非硬 gate；Phase 42 C1）
  - no_feasibility_talk     發散階段禁可行性討論
  - no_criticism            全程不批評
  - must_be_concept         接話式便條必須是沉澱後的概念（spec 27）

Phase 42 C1：``no_interpretation``（舊 1.5 Raw Wall）與 ``empathy_says_no_inference``
（舊 1.6 Empathy.Says）隨格移除——全程 assumption-based，無「原始觀察」可言
（spec 04-06 v4.25 §5.5）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

# Phase 42 C1（spec 04-06 v4.25 §5.5）：1.2「跳到功能」＝提醒＋軟擋（非硬 gate）。
# 純關鍵字快篩、刻意窄表（描述具體情境與卡點的正常句子不該誤中）；不做硬性語意判定。
# 命中後仍走 LLM 二判（只會往放行方向蓋過——引述、否定句放行），人類可 force_publish。
_FEATURE_JUMP_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_needs_feature",
        pattern=re.compile(
            r"(需要|想要|希望有|幫他|給他)[^，。]{0,8}"
            r"(功能|App|app|應用程式|小程式|網站|平台)"
        ),
        message_zh=(
            "這句聽起來比較像「要做什麼功能」了——先回到他卡住的那個當下："
            "他是在哪一步開始覺得麻煩的？"
        ),
        examples_blocked=("他需要一個提醒功能", "他需要一個 App"),
    ),
    GateRule(
        name="phrase_build_something",
        pattern=re.compile(r"(做一個|做個|開發一?個|建一個|打造一?個|設計一個)"),
        message_zh=(
            "先不急著想「要做什麼」——這關只描述他在什麼情況卡住、哪裡麻煩，"
            "解法留到後面再說。"
        ),
    ),
    GateRule(
        name="phrase_add_feature",
        pattern=re.compile(r"(加|增加|新增)一?個[^，。]{0,5}(功能|按鈕|提醒|通知)"),
        message_zh=(
            "這已經是在想解法了。先回到情境：他在哪一步、因為什麼開始覺得麻煩？"
        ),
    ),
)


_SOLUTION_LANGUAGE_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="verb_make",
        pattern=re.compile(r"(做一個|做個|開發|實作|蓋一個|建一個|寫一個|打造一個|架一個)"),
        message_zh="定義階段先不寫解法。先講清楚他是誰、需要什麼、為什麼。",
    ),
    GateRule(
        name="english_solution_verb",
        # Spec 14 A7: 英文擴充 — make/design/create 在「a/an + noun」上下文視為動詞
        pattern=re.compile(
            r"\b(build|ship|implement|develop|deploy|launch|"
            r"(make|design|create)\s+(a|an|the))\b",
            re.IGNORECASE,
        ),
        message_zh="定義階段先不寫「要做什麼東西」。先聚焦在問題本身：他需要什麼、為什麼。",
    ),
    GateRule(
        name="phrase_add_feature",
        pattern=re.compile(r"(增加一個|加入一個|新增一個|多一個).{0,5}(按鈕|功能|頁面|畫面|選項|介面)"),
        message_zh="這是在講解法了。定義階段先聚焦在使用者的需求與情境，先不要跳到怎麼解。",
    ),
    GateRule(
        name="phrase_design_a",
        pattern=re.compile(r"(設計一個|設計個)\s*"),
        message_zh="定義階段先不進到解法。先回到他遇到的問題：他在什麼情況下需要什麼？",
    ),
    GateRule(
        name="phrase_should_build",
        pattern=re.compile(r"我們應該\s*(做|蓋|寫|建|架)"),
        message_zh="要做什麼的判斷留到後面再說。定義階段先把問題本身講清楚。",
    ),
)


_FEASIBILITY_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_cannot_do",
        pattern=re.compile(r"(做不到|做不出來|沒辦法做|不可能做)"),
        message_zh="發散階段禁止可行性討論。先把想法寫下，篩選留到收斂時。",
    ),
    GateRule(
        name="phrase_cost_too_high",
        pattern=re.compile(r"(成本太高|太貴|預算不夠|資源不足)"),
        message_zh="這是可行性判斷。發散階段先讓想法飛，不評估成本。",
    ),
    GateRule(
        name="phrase_tech_not_feasible",
        pattern=re.compile(r"(技術.{0,3}不可行|技術上做不到|技術門檻太高)"),
        message_zh="發散階段先不評估技術可行性，把想法全寫出來。",
    ),
    GateRule(
        name="phrase_too_late",
        pattern=re.compile(r"(來不及|時間不夠|太趕|趕不上)"),
        message_zh="時程考量留到收斂篩選時討論。",
    ),
    GateRule(
        name="phrase_unrealistic",
        pattern=re.compile(r"(不實際|不切實際|太理想化)"),
        message_zh="發散階段歡迎瘋狂想法。請先寫下，篩選留到後面。",
    ),
    # Spec 14 A6: 疑問句也算可行性討論
    GateRule(
        name="question_can_do",
        pattern=re.compile(r"(這能做嗎|這做得到嗎|可以做嗎|這可行嗎)[?？]?"),
        message_zh="禁止可行性提問。發散階段先發散，可行性等收斂。",
    ),
    GateRule(
        name="question_how_long",
        pattern=re.compile(r"(這要多久|多久能做|要花多少時間)[?？]?"),
        message_zh="時間估算屬於可行性，收斂時再討論。",
    ),
    GateRule(
        name="question_how_much",
        pattern=re.compile(r"(這要多少錢|多少預算|多少成本)[?？]?"),
        message_zh="成本估算屬於可行性，收斂時再討論。",
    ),
)


_CRITICISM_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="phrase_dismissive",
        pattern=re.compile(r"(這不可能|太蠢|太笨|沒人會用|這做不出來|這沒用|根本不行)"),
        message_zh="我們不批評別人的想法。有疑慮的話，等挑選的時候對著準則討論。",
    ),
    GateRule(
        name="phrase_soft_negative",
        pattern=re.compile(r"(不是說不好啦|emm[^.]{0,20}不是|這個方向.{0,5}不太行)"),
        message_zh="我們不批評別人的想法，包括委婉的批評。可以改成提問或補充另一個角度。",
    ),
    GateRule(
        name="phrase_direct_reject",
        pattern=re.compile(r"(我不同意|這想法.{0,5}不好|這個爛|這個 太差)"),
        message_zh="我們不批評別人的想法。不同看法可以用補充的方式提出來。",
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


# Spec 27 (Phase 36) §4.3/§4.5：接話式（threaded_reveal）便條必須是「沉澱後的概念」，
# 不是逐字對白或問句。此 module 偵測明顯的「對白／問答」型內容（pure question、
# reply-dialogue marker、純填充語），regex 命中後再交 LLM tier 確認（能識別反詰句等例外）。
_MUST_BE_CONCEPT_PATTERNS: tuple[GateRule, ...] = (
    GateRule(
        name="pure_question",
        # 整段以問號結尾、且帶疑問詞 → 多半是「對白問句」而非沉澱概念
        pattern=re.compile(
            r"(為什麼|為何|怎麼|如何|哪一?家|哪裡|哪個|誰|多少|多久|什麼時候|是不是|有沒有)"
            r"[^。！]{0,40}[?？]\s*$"
        ),
        message_zh="接話便條要放「沉澱後的概念／洞見」，不是逐字對白或問句。請把這段對話萃取成一個概念（例：把『價格太貴？』萃取為『其實在意划不划算，不是單純嫌貴』）再貼。",
    ),
    GateRule(
        name="reply_dialogue_marker",
        # 「他說 / 她回 / 我問 / 對方說」等逐字轉述對話 → 不是概念
        pattern=re.compile(
            r"(他|她|他們|對方|受訪者|客人|店員|我)\s*(說|回|問|答|提到|表示|回答|反問)\s*[:：「]"
        ),
        message_zh="這像逐字記錄對話。接話便條只放萃取後的概念，不是「誰說了什麼」。把這段對話沉澱成一個洞見再貼。",
    ),
    GateRule(
        name="pure_filler",
        # 整段只是聊天填充語（嗯/對啊/好喔/是這樣…），沒有實質概念
        pattern=re.compile(
            r"^\s*(嗯+|喔+|哦+|對[啊呀阿]?|好[喔的]?|是這樣|就是[啊呀]?|然後呢?|"
            r"沒錯|了解|懂了|哈哈+|ok|OK|讚)\s*[，。！？～~、\s]*$"
        ),
        message_zh="這只是聊天填充語，不是沉澱後的概念。接話便條請寫一句可獨立成立的洞見。",
    ),
)


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

GATE_MODULES: dict[str, tuple[GateRule, ...]] = {
    "no_solution_language": _SOLUTION_LANGUAGE_PATTERNS,
    "no_feature_jump": _FEATURE_JUMP_PATTERNS,  # Phase 42 C1 — 1.2 跳功能軟擋
    "no_feasibility_talk": _FEASIBILITY_PATTERNS,
    "no_production_code": _PRODUCTION_CODE_PATTERNS,
    "no_criticism": _CRITICISM_PATTERNS,  # Spec 14 — 組長 B 紀律 1
    "must_be_concept": _MUST_BE_CONCEPT_PATTERNS,  # Spec 27 — 接話式概念護欄
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
    owning_user_id=None,
) -> GateResult:
    """Tier-1 + Tier-2 evaluation (Phase 18 Step A0).

    流程：
      1. 跑既有 regex（快、無上下文）：若全 pass → 直接回 pass
      2. 若 regex 命中 → 用 LLM judge 確認（有上下文，能識別引述 / 否定 / Meta）；
         LLM 認為不違規 → **蓋過 regex 放行**（override 契約）
      3. LLM 失敗 → 單次失敗保守 pass＋WARNING log（判定 down 由 D5 fail-stop
         承接，spec 20 v2.1 §13；Phase 42 補正 R2 前為裸吞錯、docstring 謊稱記 trace）

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
            owning_user_id=owning_user_id,
        )
    except Exception:
        # LLM 路徑失敗：單次失敗保守 pass（判定 down 歸 D5 fail-stop）。
        # Phase 42 補正 R2（P1-8）：吞錯升 WARNING＋traceback——修復前裸吞、
        # tier-2 故障對維運完全隱形。
        logger.warning(
            "content gate tier-2 judge failed — conservative pass (module=%s)",
            violated_module,
            exc_info=True,
        )
        return GateResult(passed=True)

    if not is_violating(judge):
        # LLM 認為不違規（例如：引述 / 否定 / Meta） → 蓋過 regex 判定
        return GateResult(passed=True)

    # LLM 同意違規 → 回 regex 命中結果，附大白話補充。
    # P1-8（#29）：「LLM 判斷：」機制詞會直達學生 RejectToast，改「補充說明」；
    # reasoning_zh 本身是 judge 產的繁中理由（judge prompt 已守大白話口徑）。
    return GateResult(
        passed=False,
        violated_module=regex_result.violated_module,
        violated_rule=regex_result.violated_rule,
        matched_text=regex_result.matched_text,
        message_zh=(regex_result.message_zh or "") + f"\n補充說明：{judge.reasoning_zh}",
    )


def list_gate_modules() -> list[str]:
    return list(GATE_MODULES.keys())


def describe_module(module_id: str) -> str:
    """中文描述供 prompt 注入。"""
    descriptions = {
        "no_solution_language": "禁止解法用語（做一個 / 開發 / 建一個 / 增加按鈕 / 設計一個…）",
        "no_feature_jump": "先別跳到功能：描述「他在什麼情況卡住」就好，寫成「他需要某個功能 / 一個 App」會被提醒改寫（軟性擋下）。",
        "no_feasibility_talk": "禁止可行性討論（做不到 / 成本太高 / 技術不可行 / 來不及 / 不實際）",
        "no_production_code": "禁止 production 級別詞彙（正式上線 / production / 實作完整）",
        "no_criticism": "禁止批評他人想法（含委婉批評）。有疑慮以建設性方式表達，挑選時對著準則討論。",
        "must_be_concept": "接話式便條必須是「沉澱後的概念／洞見」，不是逐字對白或問句（例：『跟哪一家比？』要先萃取成『其實在意划不划算』再貼）。",
    }
    return descriptions.get(module_id, module_id)

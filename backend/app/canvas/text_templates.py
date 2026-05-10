"""Text templates — Spec 13 §4.1 便條紙文字模板。

每個模板：
  - regex     驗證便條文字是否符合
  - prompt_zh AI prompt 用的中文描述
  - example   合法範例

11 種模板（spec §4.1）：
  stakeholder / scope_rationale / raw_observation / pov / criteria /
  hmw / idea / hypothesis / task_ticket / direction

Debrief 答案無模板（自由文字，落在指定子區即可）。
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
        pattern=re.compile(r".+｜佐證[:：].+", re.DOTALL),
        prompt_zh="格式：[利害關係人名稱]｜佐證：[來源]\n範例：高齡使用者｜佐證：訪談筆記-3",
        example="高齡使用者｜佐證：訪談筆記-3",
    ),
    "scope_rationale": TextTemplate(
        id="scope_rationale",
        name_zh="Scope rationale",
        pattern=re.compile(
            r"納入[:：].+｜排除[:：].+｜理由[:：].+",
            re.DOTALL,
        ),
        prompt_zh="格式：納入：[X]｜排除：[Y]｜理由：[Z]",
        example="納入：高齡長者｜排除：照顧者｜理由：本次設計焦點為使用者本人經驗",
    ),
    "raw_observation": TextTemplate(
        id="raw_observation",
        name_zh="原始觀察",
        pattern=re.compile(
            r'["「""].+["」""]｜情緒[:：].+｜來源[:：].+',
            re.DOTALL,
        ),
        prompt_zh="格式：\"[原話]\"｜情緒：[詞]｜來源：[受訪者代號]｜時間：[t]\n範例：\"我都搞不清楚要按哪裡\"｜情緒：焦躁｜來源：U2｜時間：3:25",
        example='"我都搞不清楚要按哪裡"｜情緒：焦躁｜來源：U2｜時間：3:25',
    ),
    "pov": TextTemplate(
        id="pov",
        name_zh="POV",
        pattern=re.compile(
            r".+\s*需要\s*.+[，,]\s*因為\s*.+\n\s*cites?[:：]\s*#?obs[-_]\S+",
            re.DOTALL | re.IGNORECASE,
        ),
        prompt_zh=(
            "格式（兩行）：\n"
            "  [USER] 需要 [NEED]，因為 [INSIGHT]\n"
            "  cites: #obs-X, #obs-Y\n"
            "範例：\n"
            "  電商新手使用者 需要 在不點開商品頁就看到運費，因為 運費高低決定他是否繼續\n"
            "  cites: #obs-12, #obs-23"
        ),
        example=(
            "電商新手使用者 需要 在不點開商品頁就看到運費，因為 運費高低決定他是否繼續\n"
            "cites: #obs-12, #obs-23"
        ),
        required_refs=("obs",),
    ),
    "criteria": TextTemplate(
        id="criteria",
        name_zh="收斂準則",
        pattern=re.compile(r"準則[:：].+｜衡量方式[:：].+", re.DOTALL),
        prompt_zh="格式：準則：[名稱]｜衡量方式：[如何量]",
        example="準則：時間可行性｜衡量方式：能否在 2 小時內完成原型",
    ),
    "hmw": TextTemplate(
        id="hmw",
        name_zh="HMW",
        pattern=re.compile(
            r"(How might we|我們如何).+[?？]\n?\s*from[:：]\s*#?pov[-_]\S+",
            re.DOTALL | re.IGNORECASE,
        ),
        prompt_zh=(
            "格式（兩行）：\n"
            "  How might we [動詞] [使用者] [所欲狀態]?\n"
            "  from: #pov-X\n"
            "或繁中：\n"
            "  我們如何 [動詞] [使用者] [所欲狀態]?\n"
            "  from: #pov-X"
        ),
        example="我們如何讓使用者在商品列表頁就感知到運費資訊?\nfrom: #pov-5",
        required_refs=("pov",),
    ),
    "idea": TextTemplate(
        id="idea",
        name_zh="點子",
        pattern=re.compile(
            r".+｜機制[:：].+\n?\s*for[:：]\s*#?hmw[-_]\S+",
            re.DOTALL | re.IGNORECASE,
        ),
        prompt_zh=(
            "格式（兩行）：\n"
            "  [一句 headline]｜機制：[類別]\n"
            "  for: #hmw-X"
        ),
        example="商品縮圖上直接疊運費標籤｜機制：減少步驟\nfor: #hmw-A",
        required_refs=("hmw",),
    ),
    "hypothesis": TextTemplate(
        id="hypothesis",
        name_zh="假設",
        pattern=re.compile(
            r"假設[:：].+｜成功[:：].+｜失敗[:：].+｜min_fidelity[:：].+",
            re.DOTALL,
        ),
        prompt_zh="格式：假設：[X]｜成功：[Y]｜失敗：[Z]｜min_fidelity：[paper/wireframe/code]",
        example="假設：在商品列表顯示運費會提高加購率｜成功：A/B 測試提升 15%｜失敗：無顯著差異｜min_fidelity：wireframe",
    ),
    "task_ticket": TextTemplate(
        id="task_ticket",
        name_zh="任務工單",
        pattern=re.compile(
            r"任務[:：].+｜驗收[:：].+｜fidelity 上限[:：].+\n?\s*hypothesis[:：]\s*#?hyp[-_]\S+",
            re.DOTALL | re.IGNORECASE,
        ),
        prompt_zh=(
            "格式：\n"
            "  任務：[名]｜驗收：[條件]｜fidelity 上限：[paper/wireframe/figma/code]\n"
            "  hypothesis: #hyp-X"
        ),
        example="任務：商品列表 wireframe｜驗收：3 個情境可演示｜fidelity 上限：wireframe\nhypothesis: #hyp-1",
        required_refs=("hyp",),
    ),
    "direction": TextTemplate(
        id="direction",
        name_zh="決定去向",
        pattern=re.compile(
            r"決定[:：]\s*(close|loop_define|loop_develop)\s*\n\s*理由[:：]\s*.+",
            re.DOTALL | re.IGNORECASE,
        ),
        prompt_zh=(
            "格式：\n"
            "  決定：close | loop_define | loop_develop\n"
            "  理由：..."
        ),
        example="決定：close\n理由：假設驗證成立，可進入 Spec 文檔產出",
    ),
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def validate_template(text: str, template_id: str) -> TemplateResult:
    """Validate text against the named template."""
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        # No template constraint
        return TemplateResult(passed=True, template_id=template_id)

    if not text or not text.strip():
        return TemplateResult(
            passed=False,
            template_id=template_id,
            reason_zh=f"便條為空。{tpl.name_zh} 需符合格式：{tpl.prompt_zh}",
        )

    if not tpl.pattern.search(text):
        return TemplateResult(
            passed=False,
            template_id=template_id,
            reason_zh=f"格式不符。{tpl.name_zh} 應符合：\n{tpl.prompt_zh}",
        )

    return TemplateResult(passed=True, template_id=template_id)


def get_template_prompt(template_id: str) -> str | None:
    tpl = TEMPLATES.get(template_id)
    return tpl.prompt_zh if tpl else None


def list_templates() -> list[str]:
    return list(TEMPLATES.keys())

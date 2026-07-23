"""Phase 31 (spec/23 §3): Template-specific LLM prompts for AI Suggest helper.

Each template gets a custom prompt that asks the LLM to draft a sticky-note
content matching that template's regex. The system prompt is shared; the
user prompt branches by template_id.
"""

from __future__ import annotations

from typing import Any

TEMPLATE_SUGGEST_SYSTEM_PROMPT = (
    "你是 Design Thinking 工作坊的便條紙起稿助手。\n"
    "依使用者指定的模板與情境，產出一張符合格式的便條內容。\n\n"
    "規則：\n"
    "1. 嚴格遵守指定的格式（regex 會驗證）。\n"
    "2. 內容必須具體、避免空泛；引用情境中提供的細節。\n"
    "3. 一律繁體中文。\n"
    "4. 不要加任何說明文字、不要使用 Markdown，只回傳純便條內容。\n"
)


def _format_pain_points(pp: list[str] | None) -> str:
    if not pp:
        return "（無）"
    return "\n".join(f"  - {p}" for p in pp[:8])


def _problem_statement_prompt(context: dict[str, Any]) -> str:
    persona_name = (context.get("persona_name") or "目標使用者").strip()
    persona_context = context.get("persona_context") or ""
    pain_points = context.get("pain_points") or []

    return (
        f"請為 Persona「{persona_name}」起稿一張 Problem Statement 便條。\n\n"
        f"Persona 上下文：{persona_context or '（無）'}\n"
        f"已知痛點：\n{_format_pain_points(pain_points)}\n\n"
        f"句型（必須完整填空，含句末句號）：\n"
        f"對於〔誰〕而言，在〔情境〕中，他/她常遇到〔困難〕，因為〔原因〕，因此需要〔真正需要〕。\n"
    )


def _hmw_prompt(context: dict[str, Any]) -> str:
    pov_ref = (context.get("pov_ref") or "pov-1").strip()
    persona_name = (context.get("persona_name") or "目標使用者").strip()
    chosen_ps = context.get("chosen_problem_statement") or ""

    return (
        f"請為 POV「#{pov_ref}」起稿一張 HMW 便條。\n\n"
        f"對應 Persona：{persona_name}\n"
        f"當選 Problem Statement：{chosen_ps or '（無）'}\n\n"
        f"句型（兩行）：\n"
        f"  我們如何 [動詞] [使用者] [所欲狀態]?\n"
        f"  from: #{pov_ref}\n"
    )


def _problem_candidate_prompt(context: dict[str, Any]) -> str:
    persona_name = (context.get("persona_name") or "").strip()
    pain_points = context.get("pain_points") or []
    return (
        f"請起稿一張「痛點候選」便條（簡短，≥4 字）。\n\n"
        + (f"Persona 上下文：{persona_name}\n" if persona_name else "")
        + f"已知痛點線索：\n{_format_pain_points(pain_points)}\n\n"
        f"格式：用一句話描述一個未被滿足的需求 / 矛盾。"
    )


def _task_question_prompt(context: dict[str, Any]) -> str:
    brief = (context.get("brief") or "").strip()
    return (
        f"請起稿一張「任務疑問」便條（必須含問號）。\n\n"
        f"任務 brief：{brief or '（無）'}\n\n"
        f"格式：對任務 brief 中模糊或可能需要釐清的地方，提出具體疑問句。"
    )


def _stakeholder_prompt(context: dict[str, Any]) -> str:
    title = (context.get("title") or "").strip()
    return (
        f"請起稿一張「利害關係人」便條。\n\n"
        f"任務：{title or '（無）'}\n\n"
        f"格式：[利害關係人名稱]｜佐證：[來源]\n"
        f"範例：高齡使用者｜佐證：訪談筆記-3"
    )


# Mapping from template_id to per-template user-prompt builder.
# Phase 42 收尾：persona_*（舊 DT Persona Card）builder 已移除（persona 不在 POC）。
# 實際路徑：`suggester.suggest()` 先因 `template_id not in TEMPLATES` 拋 TemplateSuggestError
# （第一道、對齊 spec 23 §3.6「移除的 template_id 回 400」）；若繞過 suggester 直呼本函式，
# persona_* → builder=None → ValueError（第二道防線）。
PROMPT_BUILDERS = {
    "problem_statement": lambda ctx: _problem_statement_prompt(ctx),
    "problem_candidate": lambda ctx: _problem_candidate_prompt(ctx),
    "hmw": lambda ctx: _hmw_prompt(ctx),
    "task_question": lambda ctx: _task_question_prompt(ctx),
    "stakeholder": lambda ctx: _stakeholder_prompt(ctx),
}


def build_user_prompt(template_id: str, context: dict[str, Any]) -> str:
    """Build the user-side prompt for the given template_id + context.

    Each supported template has a dedicated builder. Unknown / removed template_id
    (含舊 persona_*) → ValueError。
    """
    builder = PROMPT_BUILDERS.get(template_id)
    if builder is None:
        raise ValueError(
            f"template_id {template_id!r} is not supported by AI Suggest"
        )
    return builder(context)

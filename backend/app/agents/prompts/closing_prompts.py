"""Closing ritual LLM prompts（spec 26 v2.0 §3，Phase 42 C2）.

組長在第一鑽石終局時，由 LLM 生成 200-400 字結業匯報，
回顧「痛點清單 → 問題定義 → 設計題目」的產出鏈（人物誌已隨 Persona 移除）。

C2：選定問題定義／設計題目**直讀選定區**（§5.3/§5.4），builder 收陣列（每張問題定義
帶配對的選定理由全文、每張設計題目帶對應問題定義）；缺理由（含 time_box_forced 兜底）
走誠實句型「這是我們時間內選定要做的問題」（§3.1）。
"""

from __future__ import annotations

from typing import Any


# spec 26 v2.0 §3.1（System prompt 重寫）。
CLOSING_RITUAL_SYSTEM_PROMPT = (
    "你是設計思考工作坊的組長（引導者）。\n"
    "團隊剛走完整段旅程（暖場 → 發現階段 → 定義階段），準備收尾。\n\n"
    "你的任務：用 200-400 字繁體中文，發一段「結業匯報」訊息：\n"
    "1. 開頭一句話宣告完成（例：恭喜大家，我們從一堆痛點，走到了自己的設計題目）\n"
    "2. 回顧大家整理出來的痛點（一兩句帶過有哪幾類主題、印象最深的是哪件事）\n"
    "3. 點出選定的問題定義（為誰、什麼需求，以及當初為什麼選它——帶到選定理由）\n"
    "4. 朗讀最後改寫出來的設計題目（「我們可以怎麼…？」）；一張就唸一張，多張就逐一唸\n"
    "5. 誠實提醒一句：這些是根據大家自己的經驗和推想整理出來的，還沒實地驗證過，"
    "之後可以拿去找真實的使用者確認\n"
    "6. 給予肯定＋開放結尾（例：這就是大家一起聚焦出來的題目，接下來就從這裡出發）\n\n"
    "規則：\n"
    "- 不要 bullet list，用連貫敘事段落\n"
    "- 不要重複完整設計題目兩次\n"
    "- 不要評價對錯，只回顧與肯定\n"
    "- 完全繁體中文（不使用「这」「么」等簡中字）\n"
    "- 不使用 emoji\n"
    "- 不使用英文縮寫：不能出現「HMW」「POV」「Persona」，一律講「設計題目」「問題定義」\n"
    "- 不要提到任何系統內部運作（閘門、規則名稱、模板名稱、推進機制都不能出現）\n"
    "- 如果某張選定的問題定義沒有留下選它的理由（時間到了先選下去的情況也算），"
    "就照實說「這是我們時間內選定要做的問題」，不要替它編一個選定的理由\n"
    "- 如果資料顯示設計題目還沒定下來（時間到先收尾的情況），就誠實說"
    "「這次還沒把設計題目定下來」，肯定已有的進展，不假裝完成\n"
)


def build_closing_ritual_user_prompt(
    *,
    pain_points_summary: dict[str, Any],
    chosen_problem_statements: list[dict[str, Any]],
    design_questions: list[dict[str, Any]],
    project_name: str = "",
) -> str:
    """Build the user-side prompt for the closing ritual LLM call（spec 26 v2.0 §3.2）.

    注入：專案名稱 → 痛點摘要（總張數＋主題群＋代表原文 ≤5）→ 選定問題定義（≤3，每張
    全文＋配對選定理由全文；缺理由標「（時間內先選定，沒有寫理由）」）→ 設計題目（張數＝
    選定數，每張全文＋對應問題定義截短）。對便條只給內容、不給 id 編號（#30）。空值帶「（暫無）」。
    """
    total = pain_points_summary.get("total", 0)
    theme_lines = [
        f"- {t.get('label', '')}（{t.get('count', 0)} 張）"
        for t in pain_points_summary.get("themes", [])
        if t.get("label")
    ]
    highlight_lines = [
        f"- {h}" for h in pain_points_summary.get("highlights", []) if h
    ]
    pain_block = f"總共 {total} 張"
    if theme_lines:
        pain_block += "\n主題：\n" + "\n".join(theme_lines)
    if highlight_lines:
        pain_block += "\n印象比較深的幾張：\n" + "\n".join(highlight_lines)

    # 選定問題定義（id→text 供設計題目對應截短）
    ps_by_id = {c.get("note_id"): (c.get("text") or "") for c in chosen_problem_statements}
    if chosen_problem_statements:
        ps_lines = []
        for c in chosen_problem_statements:
            text = c.get("text") or "（暫無）"
            reason = c.get("selection_reason")
            reason_line = reason if reason else "（時間內先選定，沒有寫理由）"
            ps_lines.append(f"- 問題定義：{text}\n  選定理由：{reason_line}")
        ps_block = "\n".join(ps_lines)
    else:
        ps_block = "（暫無）"

    if design_questions:
        dq_lines = []
        for d in design_questions:
            text = d.get("text") or "（暫無）"
            src = ps_by_id.get(d.get("from_note_id"), "")
            src_short = (src[:30] + "…") if len(src) > 30 else src
            suffix = f"（對應問題定義：{src_short}）" if src_short else ""
            dq_lines.append(f"- {text}{suffix}")
        dq_block = "\n".join(dq_lines)
    else:
        dq_block = "（這次還沒把設計題目定下來）"

    return (
        f"專案：{project_name or '（未命名）'}\n\n"
        f"【整理出來的痛點】\n{pain_block}\n\n"
        f"【選定的問題定義（含為什麼選它）】\n{ps_block}\n\n"
        f"【最後的設計題目】\n{dq_block}\n\n"
        f"請依系統指示生成 200-400 字結業匯報。"
    )


def deterministic_fallback_closing(
    *,
    design_questions: list[str],
    pain_point_count: int,
    project_name: str = "",
    selection_reason_missing: bool = False,
) -> str:
    """Fallback closing message when LLM is unavailable（spec 26 v2.0 §3.3）。

    - ``design_questions`` 空 → 誠實反映「還沒把設計題目定下來」，不假裝達標。
    - ``selection_reason_missing``＝任一選定問題定義缺理由（或僅有 time_box_forced
      兜底理由）→ 改說「這是我們時間內選定要做的問題」，不瞎編理由
      （C1 過渡：選定理由資料隨 C2 接上，本旗標先由呼叫端決定）。
    - 全文無 emoji、無英文縮寫（v1.0 的 persona 計數已廢除）。
    """
    if pain_point_count > 0:
        pain_line = f"大家一起整理出 {pain_point_count} 張痛點，"
    else:
        pain_line = "大家一起走過了發想和討論，"

    if selection_reason_missing:
        pick_line = "這是我們時間內選定要做的問題，"
    else:
        pick_line = "從裡面選出最值得解的問題，"

    if design_questions:
        questions_block = (
            "大家聚焦的設計題目是：\n" + "\n".join(design_questions)
        )
    else:
        questions_block = (
            "（這次還沒把設計題目定下來，已經整理好的痛點和問題都還在白板上，"
            "之後可以從選問題這一步接著走。）"
        )

    return (
        f"恭喜大家走到這裡！\n\n"
        f"在「{project_name or '本次設計專案'}」中，"
        f"{pain_line}{pick_line}最後改寫成設計題目。\n\n"
        f"{questions_block}\n\n"
        f"提醒一下，這些都是根據大家自己的經驗和推想整理出來的，"
        f"之後可以再找真實的使用者確認看看。\n"
        f"這就是這段旅程的成果，接下來就從這個題目出發，想想可以怎麼解。"
    )

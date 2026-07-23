"""學生友善 label — 把內部 micro/sub-phase 的 ``name_zh`` 轉成給參與者看的白話。

盲測 2026-06-08：聊天室 / 計時器 / 白板把「講義第N步」「1.1b」「sub-phase」「私區」這類
只有開發者與教學設計看得懂的內部代號漏給學生看。內部 ``name_zh`` 與代號保留作 log / spec /
agent 內部參照用；**只在「對學生顯示」的邊界**（watcher 聊天交代、timer 序列化、zone 標題、
agent 對外發言護欄）套用本模組，移除這些註記。
"""
from __future__ import annotations

import re

# 移除含「講義」的括號註記（全形/半形皆可），例：「（講義第 1 步）」「（講義第 2-3 步：…）」。
_LECTURE_PAREN = re.compile(r"[（(][^（）()]*講義[^（）()]*[）)]")


def student_facing_label(name: str | None) -> str:
    """回傳學生友善 label：移除「（講義第N步…）」這類內部教學註記，其餘保留。

    例：
      「獨立列利害關係人（講義第 1 步）」 → 「獨立列利害關係人」
      「視角擴展（講義第 2-3 步：增進領域同理 / 設計訪談）」 → 「視角擴展」
      「破冰｜經驗分享」 → 「破冰｜經驗分享」（無變化）
    """
    if not name:
        return name or ""
    return _LECTURE_PAREN.sub("", name).strip()


__all__ = ["student_facing_label"]

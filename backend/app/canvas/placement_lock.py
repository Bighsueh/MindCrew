"""Per-project 放置序列化鎖（RC3 修正）。

背景（rootcause 2026-06-21 RC3）：便條落點是「讀白板快照 → 算不碰撞座標 → 寫入」
三段、無鎖；兩個 agent 併發貼便條時各讀同一份（可能過期的）快照，各自算出
「不碰撞」的同一個空位而互疊。

本模組提供 per-project 的 asyncio 鎖：放置臨界區（fresh 讀 → 算落點 → 寫入
sidecar）全程持鎖，保證同專案的落點計算彼此可見。

範圍註記：後端為單一 uvicorn 行程（start.sh 無 --workers），in-process
asyncio.Lock 即完整覆蓋；若未來改多 worker 部署，需升級為 Redis 分散式鎖
（SET NX EX + 續租），屆時只需替換本模組實作。
"""

from __future__ import annotations

import asyncio
from uuid import UUID

_LOCKS: dict[str, asyncio.Lock] = {}


def placement_lock(project_id: UUID) -> asyncio.Lock:
    """取得（或建立）該專案的放置鎖。用法：``async with placement_lock(pid): …``"""
    key = str(project_id)
    lock = _LOCKS.get(key)
    if lock is None:
        lock = _LOCKS.setdefault(key, asyncio.Lock())
    return lock

"""經驗分享參與彙整（Phase 42，1.1a「發現階段隊友沉默」修復；spec 22 1.1a / 04-03 §3.2）。

單一真相來源：B13 邀請 trigger（triggers_b）、signal_panel「全員分享」面板、
`_cued_should_open_floor` 安全網（經 context_buffer 注入）共用同一份 ``share_status``，
不各算各的。設計仿 ``warmup_exit.py`` 的 ``_participation`` / ``warmup_status``。

口徑（對齊 spec 22 1.1a「每位 crew 接過 ≥1 自身經驗 ＋ 真人 ≥1」、04-03 §3.2「組長判讀」）：
- AI crew 參與：round_lock 累積 ``participated_crews``（每席 ≥1 則實質輸出，不做字數檢核）。
- 真人參與：round_lock ``round`` ≥2 或本回合已有過檢核的輸入（≥1 次實質輸出即算）。
- 全 AI 房：round_lock 不追蹤（``mark_crew_output`` 對無真人房直接 return）→ ``all_shared``
  恆 True（B13 不 fire、安全網不開、面板顯示全 AI 房），與既有行為一致、不改全 AI 房。

防呆（spec 22 1.1a）：某 crew 被邀請 ≥``_INVITE_CAP`` 次仍沉默（失能/不回應）→ 把該席從
``missing`` 扣除（``bump_invite`` 由 B13 trigger 每次 fire 累計、達上限視為跳過），避免一個
失能 crew 卡死整個邀請迴圈、讓 crew_3/4 永遠輪不到。以「B13 fire」為計數信號＝每個 supervisor
決策週期至多一次、且同時涵蓋 set_directive 與 @-mention 兩種執行路徑（alive crew 被邀後本週期
內即回應、離開 missing，不會被誤跳）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)

SHARE_SUB_PHASE = "1.1a"

# 邀 _INVITE_CAP 次仍沒分享 → 視為跳過（防失能 crew 卡死迴圈）。
_INVITE_CAP = 2
_TTL_SECONDS = 3600


@asynccontextmanager
async def _redis():
    """與 round_lock / turn_controller 同模式（每次 from_url、try/finally aclose）。"""
    import redis.asyncio as aioredis

    from app.config import settings

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


def _invite_key(project_id: UUID) -> str:
    """本關各 crew 被組長點名分享的累計次數（hash：seat_role → count）。"""
    return f"project:{project_id}:share_invite:{SHARE_SUB_PHASE}"


@dataclass(frozen=True)
class ShareStatus:
    """1.1a 經驗分享參與快照（B13 / 面板 / 安全網共用）。"""

    has_human: bool
    human_shared: bool                   # 真人至少分享過一次（全 AI 房恆 True）
    missing_crews: tuple[str, ...]       # 還沒分享過、且未被跳過的 crew 顯示名
    missing_crew_seats: tuple[str, ...]  # 對應 raw seat_role（給 trigger 設 invited_speaker）
    all_shared: bool                     # 全員 crew + 真人都分享過（全 AI 房恆 True）


async def bump_invite(project_id: UUID, seat_role: str) -> None:
    """1.1a 對某 crew 累計一次邀請嘗試（達 ``_INVITE_CAP`` 仍沒分享即跳過）。

    由 B13 trigger（triggers_b）每次 fire 對其目標席位呼叫——每個 supervisor 決策週期至多
    一次，且涵蓋 set_directive 與 @-mention 兩種執行路徑。Best-effort：Redis 失敗只 log
    （跳過機制失效＝最多多邀幾次，不致命）。
    """
    try:
        async with _redis() as r:
            await r.hincrby(_invite_key(project_id), seat_role, 1)
            await r.expire(_invite_key(project_id), _TTL_SECONDS)
    except Exception:
        logger.debug("bump_invite failed project=%s seat=%s", project_id, seat_role, exc_info=True)


async def _skipped_seats(project_id: UUID) -> set[str]:
    """被點名 ≥ ``_INVITE_CAP`` 次仍沒分享的席位（從 missing 扣除）。"""
    try:
        async with _redis() as r:
            counts = await r.hgetall(_invite_key(project_id))
        return {seat for seat, c in counts.items() if _safe_int(c) >= _INVITE_CAP}
    except Exception:
        logger.debug("share invite-count read failed project=%s", project_id, exc_info=True)
        return set()


def _safe_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


async def share_status(project_id: UUID) -> ShareStatus:
    """彙整 1.1a 經驗分享參與訊號（B13 / 面板 / 安全網共用）。"""
    from app.agents import round_lock

    try:
        state = await round_lock.get_state(project_id, SHARE_SUB_PHASE)
    except Exception:
        logger.debug("share_status get_state failed project=%s", project_id, exc_info=True)
        # 保守：讀不到狀態 → 當全員已分享（不驅動邀請、不開安全網），交由時間兜底。
        return ShareStatus(
            has_human=False, human_shared=True,
            missing_crews=(), missing_crew_seats=(), all_shared=True,
        )

    if not state.get("has_human"):
        # 全 AI 房：round_lock 不追蹤；不驅動邀請迴圈（行為與既有一致）。
        return ShareStatus(
            has_human=False, human_shared=True,
            missing_crews=(), missing_crew_seats=(), all_shared=True,
        )

    human_shared = (
        int(state.get("round") or 1) >= 2 or bool(state.get("human_inputs"))
    )
    ai_crew = set(state.get("ai_crew") or [])
    participated = set(state.get("participated_crews") or [])
    skipped = await _skipped_seats(project_id)
    missing_seats = sorted((ai_crew - participated) - skipped)

    names: list[str] = []
    for seat_role in missing_seats:
        try:
            from app.agents.personas.display import resolve_display_name

            names.append(resolve_display_name(seat_role))
        except Exception:
            names.append(seat_role)

    # all_shared：沒有「還能邀」的 crew（已分享 or 已跳過）＋ 真人已分享。
    all_shared = (not missing_seats) and human_shared
    return ShareStatus(
        has_human=True,
        human_shared=human_shared,
        missing_crews=tuple(names),
        missing_crew_seats=tuple(missing_seats),
        all_shared=all_shared,
    )

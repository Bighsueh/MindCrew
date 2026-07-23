"""Auto reflow — 依狀態自動觸發的確定性版面保底（RC4 修正）。

背景（`_discussion/docs/sticky-spatial-layout-rootcause-2026-06-21.md` RC4）：
整理原本只綁在 LLM 動作上——think 輸出 1024 token 上限＋截斷修復會默默丟掉尾端
geometry 動作 →「嘴上說整理、白板沒變」，且系統沒有任何依狀態自動重排的路徑。

本模組在每個 agent 回合結束後（base_agent 持 coordinator 鎖時）best-effort 執行：

1. **重疊讓位**（任何階段；spec 10 v2.0 §5.8「白板上不留重疊、工具必須自動處理」）
   — 每輪最多搬 ``_MAX_YIELD_PER_RUN`` 張（spec 27 §7 逐撮）、只搬 AI 便條、
   pin 在動態 section 的成員不動、落點限原 band 內、歸因「系統讓位」。
2. **低有序度單群收攏**（僅收斂階段；spec 27 §7「收斂才整理」＋ §12.8 交代）
   — orderliness 低於門檻且過 cooldown 時，挑一個最散的群就地收攏
   （``tidy_area scope="group"``），並在聊天室以組長口吻交代一句。

守則：永不整面重排、每次只動少數便條、任何失敗不得阻斷 agent 回合。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.analyzer import get_spatial_analyzer
from app.canvas.layout_engine import (
    SPACING_VALUES,
    CoordinateUpdate,
    get_layout_engine,
)
from app.canvas.placement_lock import placement_lock
from app.canvas.sections import get_section_bounds_map
from app.canvas.spatial import _rects_overlap
from app.canvas.tools_manipulation import _section_pinned_ids, tool_tidy_area
from app.canvas.zone_registry import get_all_zones_for_project
from app.stages.phase_intent import get_phase_intent_by_sub_phase

logger = logging.getLogger(__name__)

# 一輪最多讓位張數（spec 27 §7：一小撮一小撮，不是批次掃除）。
_MAX_YIELD_PER_RUN = 3
# 收斂期自動收攏門檻與節流。
_ORDERLINESS_TIDY_THRESHOLD = 0.35
_TIDY_COOLDOWN_S = 120.0
# 整體最短執行間隔（每個 agent 回合都會呼叫，用 Redis 時戳節流）。
_MIN_RUN_INTERVAL_S = 30.0

_RUN_TS_KEY = "project:{project_id}:auto_reflow_ts"
_TIDY_TS_KEY = "project:{project_id}:last_tidy_ts"  # 與 act_canvas / Rule X 共用

_YIELD_ATTRIBUTION = "系統讓位"   # spec 10 §5.8：讓位連帶移動的歸因
_TIDY_ATTRIBUTION = "系統整理"


@dataclass(frozen=True)
class ReflowResult:
    yielded: int = 0
    tidied_group: str | None = None
    skipped: str | None = None


def _now() -> float:
    return time.time()


async def _get_ts(key: str) -> float | None:
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await r.get(key)
            return float(raw) if raw else None
        finally:
            await r.aclose()
    except Exception:
        return None


async def _set_ts(key: str, value: float) -> None:
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.set(key, str(value))
        finally:
            await r.aclose()
    except Exception:
        pass


async def _publish_narration(project_id: UUID, content: str) -> None:
    """整理交代（spec 27 §12.8）：以組長席位名義發一句白話說明。"""
    from app.agents.cue_chat_messages import _publish_chat_message

    await _publish_chat_message(
        project_id=project_id, sender_seat_role="supervisor", content=content,
    )


# ---------------------------------------------------------------------------
# 重疊讓位（純函式核心，可獨立測試）
# ---------------------------------------------------------------------------


def _pick_yield_victim(a: Any, b: Any, pinned_ids: set[str]) -> Any | None:
    """重疊對中挑「誰讓位」：不動 pin／不動人類／不動分類標籤；都可動時後貼的讓位。"""

    def _movable(n: Any) -> bool:
        return (
            n.id not in pinned_ids
            and getattr(n, "author_type", "ai") != "human"
            and getattr(n, "kind", "content") != "label"  # 標籤是群的視覺錨點
        )

    movable = [n for n in (a, b) if _movable(n)]
    if not movable:
        return None
    if len(movable) == 1:
        return movable[0]
    return max(movable, key=lambda n: (getattr(n, "created_at", "") or "", n.id))


def _band_for(x: float, y: float, bands: list[Any]) -> Any | None:
    for band in bands:
        if band.contains(x, y):
            return band
    return None


def plan_overlap_yields(
    notes: list[Any],
    overlap_pairs: list[tuple[str, str]],
    pinned_ids: set[str],
    bands: list[Any],
    engine: Any,
    forbidden: tuple[Any, ...] = (),
) -> list[CoordinateUpdate]:
    """把重疊對化成「最少張數」的讓位座標更新（確定性、每輪封頂）。

    - victim 在某 band 內 → 帶內掃空位（讓位限本帶，spec 10 §5.8）；
      不在任何 band → 就地螺旋避讓（保守 fallback）。
    - 後續碰撞檢查看的是「已讓位後」的工作狀態，避免搬回別人剛空出的位置。
    """
    gap = SPACING_VALUES["default"]
    working: dict[str, Any] = {n.id: n for n in notes}
    moved_ids: set[str] = set()
    updates: list[CoordinateUpdate] = []

    for a_id, b_id in overlap_pairs:
        if len(updates) >= _MAX_YIELD_PER_RUN:
            break
        if a_id in moved_ids or b_id in moved_ids:
            continue
        a = working.get(a_id)
        b = working.get(b_id)
        if a is None or b is None or not _rects_overlap(a, b):
            continue
        victim = _pick_yield_victim(a, b, pinned_ids)
        if victim is None:
            continue

        others = [n for n in working.values() if n.id != victim.id]
        band = _band_for(victim.x, victim.y, bands)
        if band is not None:
            nx, ny = engine._place_in_section(band, others, gap, forbidden=forbidden)
        else:
            nx, ny = engine._find_non_colliding(victim.x, victim.y, others, gap)

        updates.append(CoordinateUpdate(id=victim.id, x=nx, y=ny))
        working[victim.id] = replace(victim, x=nx, y=ny)
        moved_ids.add(victim.id)

    return updates


def _pick_messiest_group(
    notes: list[Any], overlap_pairs: list[tuple[str, str]]
) -> str | None:
    """挑一個最需要收攏的群（≥2 張內容便條）：先看重疊涉入、再看攤開程度。"""
    overlap_ids = {nid for pair in overlap_pairs for nid in pair}
    groups: dict[str, list[Any]] = {}
    for n in notes:
        gid = getattr(n, "concept_group_id", None)
        if not gid or getattr(n, "kind", "content") == "label":
            continue
        groups.setdefault(gid, []).append(n)

    candidates = {gid: ms for gid, ms in groups.items() if len(ms) >= 2}
    if not candidates:
        return None

    def _score(item: tuple[str, list[Any]]) -> tuple[float, float, str]:
        gid, ms = item
        overlapped = sum(1 for m in ms if m.id in overlap_ids)
        spread_w = max(m.x for m in ms) - min(m.x for m in ms)
        spread_h = max(m.y for m in ms) - min(m.y for m in ms)
        return (overlapped, (spread_w + spread_h) / len(ms), gid)

    return max(candidates.items(), key=_score)[0]


# ---------------------------------------------------------------------------
# 編排入口
# ---------------------------------------------------------------------------


async def maybe_auto_reflow(
    project_id: UUID, sub_phase_id: str | None
) -> ReflowResult:
    """agent 回合結束後的版面保底。best-effort：呼叫端須以 try/except 包覆。"""
    now = _now()
    run_key = _RUN_TS_KEY.format(project_id=project_id)
    last_run = await _get_ts(run_key)
    if last_run is not None and now - last_run < _MIN_RUN_INTERVAL_S:
        return ReflowResult(skipped="throttled")
    await _set_ts(run_key, now)

    analyzer = get_spatial_analyzer()

    # RC3：讓位的「讀-算-寫」與 create/move 共用 per-project 放置鎖，
    # 保證與併發的貼便條彼此可見。
    yields: list[CoordinateUpdate] = []
    async with placement_lock(project_id):
        analysis = await analyzer.analyze(project_id, fresh=True)
        if not analysis.notes:
            return ReflowResult(skipped="empty")

        # spec 27 §7「發散＝貼了就不動別人／只貼不搬」：發散階段不做事後讓位
        # （placement-time 避讓＋放置鎖已防新重疊；殘餘重疊留待收斂期修）。
        if get_phase_intent_by_sub_phase(sub_phase_id) != "divergent":
            pinned = await _section_pinned_ids(project_id, analysis.notes)
            zone_bounds = await get_all_zones_for_project(project_id)
            section_bounds = await get_section_bounds_map(project_id)
            bands = list(zone_bounds.values()) + list(section_bounds.values())

            engine = get_layout_engine()
            yields = plan_overlap_yields(
                analysis.notes, analysis.overlap_pairs, pinned, bands, engine,
                forbidden=tuple(section_bounds.values()),
            )
            if yields:
                await canvas_ops.batch_update_coordinates(
                    project_id,
                    [{"id": u.id, "x": u.x, "y": u.y} for u in yields],
                    moved_by=_YIELD_ATTRIBUTION,
                )
                await analyzer.invalidate_full_state_cache(project_id)
                logger.info(
                    "auto_reflow: yielded %d overlapping note(s) project=%s",
                    len(yields), project_id,
                )

    tidied = await _maybe_group_tidy(project_id, sub_phase_id, now)
    return ReflowResult(yielded=len(yields), tidied_group=tidied)


# 自動群收攏的單群成員上限（spec 27 §7「一小撮一小撮」：大群留給 LLM/組長刻意處理）。
_TIDY_MAX_GROUP_SIZE = 8


async def _maybe_group_tidy(
    project_id: UUID,
    sub_phase_id: str | None,
    now: float,
) -> str | None:
    """收斂期低有序度 → 挑一個群就地收攏＋聊天交代（受 cooldown 節流）。

    先說再做（spec 27 §7）：narration 先發、再動白板。
    """
    if get_phase_intent_by_sub_phase(sub_phase_id) != "convergent":
        return None

    # 讓位剛跑完 → 重讀新鮮狀態做整理決策（不吃讓位前的舊快照）。
    analysis = await get_spatial_analyzer().analyze(project_id, fresh=True)
    if not analysis.notes:
        return None
    if analysis.orderliness_score >= _ORDERLINESS_TIDY_THRESHOLD:
        return None

    tidy_key = _TIDY_TS_KEY.format(project_id=project_id)
    last_tidy = await _get_ts(tidy_key)
    if last_tidy is not None and now - last_tidy < _TIDY_COOLDOWN_S:
        return None

    gid = _pick_messiest_group(analysis.notes, analysis.overlap_pairs)
    if gid is None:
        return None
    group_size = sum(
        1 for n in analysis.notes
        if getattr(n, "concept_group_id", None) == gid
        and getattr(n, "kind", "content") != "label"
    )
    if group_size > _TIDY_MAX_GROUP_SIZE:
        return None  # 一小撮原則：大群不自動收攏

    await _publish_narration(
        project_id,
        f"「{gid}」這一群的便條有點散，我把它們收攏對齊一下，看起來會比較清楚。",
    )
    result = await tool_tidy_area(
        project_id=project_id,
        scope="group",
        target=gid,
        strategy="align_grid",
        moved_by=_TIDY_ATTRIBUTION,
    )
    if not result.get("success") or not result.get("tidied_count"):
        return None

    await _set_ts(tidy_key, now)
    logger.info(
        "auto_reflow: group tidy applied project=%s group=%s", project_id, gid,
    )
    return gid

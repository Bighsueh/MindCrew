"""回合鎖狀態機（Phase 42 A2，spec 20 v2.0 §11）。

一回合 = 當前 sub-phase 內、每個在席 AI crew 至多 1 次實質輸出；全部輪過（或組長
宣布本輪結束）且真人本回合尚無有效輸入 → 凍結（`waiting_for_human`）→ 真人有效
輸入（過 §12 實質檢核＋符合該關 gate 型態）→ 完成本回合、round +1、解凍。

設計重點（含 A2 code review 修正）：
- **狀態以 sub_phase 為界分鍵**（`…:{sub_phase}:meta/crews/human`）——推進到新
  sub_phase 自然使用全新鍵，**不需 reset、無 reset race**（CRITICAL 修正）；舊鍵
  TTL 自然過期。
- **`is_crew_blocked` 純讀**（不寫、不查 seats）——ASSESS hot path 安全（HIGH 修正）。
- **凍結 publish 以 `SET NX` 標記去重**——並發「最後一位 crew」不會重複發
  `waiting_for_human`（CRITICAL 修正）。
- **全 AI 房不凍結**：無真人在席 → 完全不追蹤、不凍結。
- 防死鎖：只凍結 AI 內容輸出，**不碰 time-box**；time-box 到推進 → sub_phase 一變
  即自動解凍（spec 20 §11.7）。真人 `pass` 不呼叫 `register_human_input` → 不解鎖。

逐關解鎖型態表（§11.4）為**獨立常數**、以 sub_phase id 為鍵，未知 / 尚未啟用的格
降級「聊天・擇一」；故 A2 可先於 C1（5+7 格重構）落地。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select

from app.db.models.seat import SEAT_ROLE_SUPERVISOR
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600

# 有效輸入型態（chat / note / move / confirm）。
VALID_INPUT_TYPES = frozenset({"chat", "note", "move", "confirm"})

# 逐關解鎖型態表（spec 20 §11.4）。value = (required_types, mode)。
# 0.0a 為特例（教學回合雙工具 mode=all、之後 mode=any），於 gate_types_for 處理。
# 未列出的格（0.1/0.2/1.3–1.6 與未知）降級為「聊天・擇一」。
_GATE_TYPES: dict[str, tuple[tuple[str, ...], str]] = {
    "1.1a": (("chat",), "any"),       # 經驗分享：講
    "1.1b": (("note",), "any"),       # 發想利害關係人：貼
    "1.1c": (("chat",), "any"),       # 一起歸類：講（confirm 白名單於 human_input_check 處理）
    "1.1d": (("chat", "note"), "any"),  # 排先後順序：講 OR 貼
    "1.2": (("note",), "any"),        # 發想痛點：貼
    "2.1": (("move", "chat"), "all"),  # 痛點歸類：拖 AND 說（#27）
    "2.2": (("note", "chat"), "any"),  # 問題定義：貼 OR 講
    "2.3": (("chat",), "any"),        # 追問根源：講
    "2.4": (("chat",), "any"),        # 盤點現有解法：講
    "2.5": (("chat",), "any"),        # 訂收斂準則：講
    "2.6": (("move", "chat"), "all"),  # 依準則挑問題定義：拖 AND 說
    "2.7": (("confirm",), "any"),     # 改寫設計題目：確認
}
_DEFAULT_GATE: tuple[tuple[str, ...], str] = (("chat",), "any")


def gate_types_for(sub_phase: str, round_no: int) -> tuple[tuple[str, ...], str]:
    """回傳該關（含回合）的 (required_types, mode)。"""
    if sub_phase == "0.0a":
        mode = "all" if round_no <= 1 else "any"
        return (("note", "chat"), mode)
    return _GATE_TYPES.get(sub_phase, _DEFAULT_GATE)


def required_for(sub_phase: str, round_no: int) -> dict:
    """waiting_for_human.required payload（型態旗標＋組合語意 mode）。"""
    types, mode = gate_types_for(sub_phase, round_no)
    return {
        "note": "note" in types,
        "chat": "chat" in types,
        "move": "move" in types,
        "confirm": "confirm" in types,
        "mode": mode,
    }


def _type_met(req_type: str, human_types: set[str]) -> bool:
    """單一所需型態是否被真人已做的輸入型態滿足。

    chat / confirm 互通：A2 的確認多半以聊天承載；A3 的確認按鈕亦可滿足 chat 關。
    """
    if req_type == "chat":
        return "chat" in human_types or "confirm" in human_types
    if req_type == "confirm":
        return "confirm" in human_types or "chat" in human_types
    return req_type in human_types  # note / move 必須真的貼 / 拖


def _satisfies(human_types: set[str], sub_phase: str, round_no: int) -> bool:
    types, mode = gate_types_for(sub_phase, round_no)
    checks = [_type_met(t, human_types) for t in types]
    return all(checks) if mode == "all" else any(checks)


# ---------------------------------------------------------------------------
# Redis / seat helpers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _redis():
    # 與 A1 的 boundary_signal / supervisor_activity 同模式（每次開 from_url、try/finally
    # aclose）；共享連線池屬跨模組優化，另案處理，不在 A2 範圍。
    import redis.asyncio as aioredis

    from app.config import settings

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


def _meta_key(project_id: UUID, sub_phase: str) -> str:
    return f"project:{project_id}:round_lock:{sub_phase}:meta"


def _crews_key(project_id: UUID, sub_phase: str) -> str:
    return f"project:{project_id}:round_lock:{sub_phase}:crews"


def _human_key(project_id: UUID, sub_phase: str) -> str:
    return f"project:{project_id}:round_lock:{sub_phase}:human"


def _waitpub_key(project_id: UUID, sub_phase: str, round_no: int) -> str:
    return f"project:{project_id}:round_lock:{sub_phase}:waitpub:{round_no}"


def _participated_key(project_id: UUID, sub_phase: str) -> str:
    """跨回合累積的「本關有出過聲的 crew」集合（Phase 42 B1，spec/28 §5.1 全員參與）。

    與 per-round 的 crews set 不同：回合完成不清、只隨 sub_phase 換鍵 / TTL / clear 消失。
    """
    return f"project:{project_id}:round_lock:{sub_phase}:participated"


async def _seat_facts(project_id: UUID) -> tuple[set[str], str | None]:
    """(在席 AI crew seat_role 集合, 真人席 user_id)。真人席空置 → user_id None。"""
    from app.db.models.seat import Seat

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Seat.seat_role, Seat.occupant_type, Seat.user_id).where(
                Seat.project_id == project_id
            )
        )
        ai_crew: set[str] = set()
        human_uid: str | None = None
        for seat_role, occ, uid in rows.all():
            if occ == "ai" and seat_role and seat_role != SEAT_ROLE_SUPERVISOR:
                ai_crew.add(seat_role)
            elif occ == "human" and uid is not None:
                human_uid = str(uid)
        return ai_crew, human_uid


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------

async def _publish_waiting(
    project_id: UUID, sub_phase: str, round_no: int, human_user_id: str
) -> None:
    try:
        from app.events.bus import event_bus
        from app.events.types import WaitingForHumanEvent

        await event_bus.publish(
            WaitingForHumanEvent(
                project_id=project_id,
                sub_phase=sub_phase,
                round=round_no,
                required=required_for(sub_phase, round_no),
                target_user_id=human_user_id,
            )
        )
    except Exception:
        logger.debug("publish waiting_for_human failed project=%s", project_id, exc_info=True)


async def _publish_turn_state(project_id: UUID) -> None:
    """解鎖 / 推進後以 turn_state_event 通知前端回復正常（spec 20 §5.6）。"""
    try:
        from app.db.models.project import Project

        async with async_session_factory() as session:
            policy = await session.scalar(
                select(Project.turn_policy).where(Project.id == project_id)
            )
        from app.events.bus import event_bus
        from app.events.types import TurnStateEvent

        await event_bus.publish(
            TurnStateEvent(
                project_id=project_id,
                policy=str(policy or "cued"),
                next_speaker=None,
                allowed_actions=(),
                # A-P2（補正 R4）：標記來源——前端只認 round_lock 來源清等待列。
                source="round_lock",
            )
        )
    except Exception:
        logger.debug("publish turn_state failed project=%s", project_id, exc_info=True)


# ---------------------------------------------------------------------------
# Core transition
# ---------------------------------------------------------------------------

async def _maybe_complete_or_freeze(
    r, project_id: UUID, sub_phase: str, ai_crew: set[str], human_user_id: str
) -> bool:
    """本回合是否完成（round +1）。否則視情況凍結（publish waiting_for_human）。

    `declared`（組長宣布本輪結束）視同全員輪過，使真人之後的有效輸入仍能解鎖。
    """
    meta = await r.hgetall(_meta_key(project_id, sub_phase))
    round_no = int(meta.get("round") or "1")
    waiting = meta.get("waiting") == "1"
    declared = meta.get("declared") == "1"
    crews = set(await r.smembers(_crews_key(project_id, sub_phase)))
    human = set(await r.smembers(_human_key(project_id, sub_phase)))

    all_ai_acted = declared or (bool(ai_crew) and ai_crew <= crews)
    satisfied = _satisfies(human, sub_phase, round_no)

    if all_ai_acted and satisfied:
        pipe = r.pipeline()
        pipe.hset(
            _meta_key(project_id, sub_phase),
            mapping={"round": str(round_no + 1), "waiting": "0", "declared": "0"},
        )
        pipe.expire(_meta_key(project_id, sub_phase), _TTL_SECONDS)
        pipe.delete(_crews_key(project_id, sub_phase), _human_key(project_id, sub_phase))
        await pipe.execute()
        await _publish_turn_state(project_id)
        return True

    if all_ai_acted and not satisfied and not waiting:
        # 以 SET NX 標記保證本 (sub_phase, round) 只發一次 waiting_for_human（去並發重發）。
        first = await r.set(
            _waitpub_key(project_id, sub_phase, round_no), "1", nx=True, ex=_TTL_SECONDS
        )
        pipe = r.pipeline()
        pipe.hset(_meta_key(project_id, sub_phase), "waiting", "1")
        pipe.expire(_meta_key(project_id, sub_phase), _TTL_SECONDS)
        await pipe.execute()
        if first:
            await _publish_waiting(project_id, sub_phase, round_no, human_user_id)
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def mark_crew_output(project_id: UUID, sub_phase: str, seat_role: str) -> None:
    """某 AI crew 完成一次實質輸出（chat / 便條 / 搬動）。

    全 AI 房（無真人在席）→ 不追蹤、永不凍結。組長不佔 crew 配額（呼叫端已過濾）。
    """
    if not sub_phase:
        return
    try:
        ai_crew, human_uid = await _seat_facts(project_id)
        if human_uid is None:
            return  # 全 AI 房：不凍結
        async with _redis() as r:
            pipe = r.pipeline()
            pipe.hsetnx(_meta_key(project_id, sub_phase), "round", "1")
            pipe.hsetnx(_meta_key(project_id, sub_phase), "waiting", "0")
            pipe.sadd(_crews_key(project_id, sub_phase), seat_role)
            pipe.sadd(_participated_key(project_id, sub_phase), seat_role)
            pipe.expire(_meta_key(project_id, sub_phase), _TTL_SECONDS)
            pipe.expire(_crews_key(project_id, sub_phase), _TTL_SECONDS)
            pipe.expire(_participated_key(project_id, sub_phase), _TTL_SECONDS)
            await pipe.execute()
            await _maybe_complete_or_freeze(r, project_id, sub_phase, ai_crew, human_uid)
    except Exception:
        logger.debug("mark_crew_output failed project=%s", project_id, exc_info=True)


async def is_crew_blocked(
    project_id: UUID, sub_phase: str, seat_role: str
) -> tuple[bool, str]:
    """ASSESS Rule 0.8：此 crew 本 tick 是否被回合鎖擋下。回 (blocked, 內部原因)。

    **純讀**（不寫、不查 seats，hot path）：waiting → 全擋；本回合已輸出過 → 擋。
    全 AI 房不會進入 waiting、crews 也不累積（mark_crew_output 已過濾），故恆不擋。
    Redis 失敗 → 不擋（保守：不因基礎設施故障鎖死 AI）。
    """
    if not sub_phase:
        return False, ""
    try:
        async with _redis() as r:
            waiting = await r.hget(_meta_key(project_id, sub_phase), "waiting")
            if waiting == "1":
                return True, "正在等使用者回應，先把空間留給他"
            crews = await r.smembers(_crews_key(project_id, sub_phase))
            if seat_role in crews:
                return True, "這一回合你已經發過言了，先等使用者"
            return False, ""
    except Exception:
        logger.debug("is_crew_blocked failed project=%s", project_id, exc_info=True)
        return False, ""


async def register_human_input(
    project_id: UUID, sub_phase: str, input_type: str
) -> bool:
    """真人**已通過實質檢核**的有效輸入。回傳本回合是否因此完成（解鎖）。

    型態須符合該關 gate（§11.4）才解鎖；不符（如 note 關收到 chat）僅記錄、不解鎖。
    真人 pass 不應呼叫本函式（pass 不是有效輸入，spec 20 §11.4）。
    """
    if not sub_phase:
        return False
    if input_type not in VALID_INPUT_TYPES:
        input_type = "chat"
    try:
        ai_crew, human_uid = await _seat_facts(project_id)
        if human_uid is None:
            return False
        async with _redis() as r:
            pipe = r.pipeline()
            pipe.hsetnx(_meta_key(project_id, sub_phase), "round", "1")
            pipe.hsetnx(_meta_key(project_id, sub_phase), "waiting", "0")
            pipe.sadd(_human_key(project_id, sub_phase), input_type)
            pipe.expire(_meta_key(project_id, sub_phase), _TTL_SECONDS)
            pipe.expire(_human_key(project_id, sub_phase), _TTL_SECONDS)
            await pipe.execute()
            return await _maybe_complete_or_freeze(
                r, project_id, sub_phase, ai_crew, human_uid
            )
    except Exception:
        logger.debug("register_human_input failed project=%s", project_id, exc_info=True)
        return False


async def declare_round_end(project_id: UUID, sub_phase: str) -> None:
    """組長宣布本輪結束（提前把話語權交給真人）——即使 crew 未全輪過也凍結。

    設 `declared` 旗標：之後真人有效輸入仍能解鎖（不卡在「crew 未全輪過」）。目前由
    「組長 cue 真人」路徑觸發，與 cued 人類分支疊加（spec 20 §2.2/§11.3）。
    """
    if not sub_phase:
        return
    try:
        ai_crew, human_uid = await _seat_facts(project_id)
        if human_uid is None:
            return
        async with _redis() as r:
            pipe = r.pipeline()
            pipe.hsetnx(_meta_key(project_id, sub_phase), "round", "1")
            pipe.hset(_meta_key(project_id, sub_phase), "declared", "1")
            pipe.expire(_meta_key(project_id, sub_phase), _TTL_SECONDS)
            await pipe.execute()
            await _maybe_complete_or_freeze(r, project_id, sub_phase, ai_crew, human_uid)
    except Exception:
        logger.debug("declare_round_end failed project=%s", project_id, exc_info=True)


async def refresh_ttl(project_id: UUID, sub_phase: str) -> None:
    """休眠喚醒續期（Phase 42 補正 R4／裁定⑤：round_lock TTL × Phase 43 休眠）。

    休眠可無限期；超過 1 小時喚醒後本關 meta/crews/human/participated 鍵已過期
    → round 歸 1、參與累積歸零。resume_room 喚醒時呼叫本函式把鍵續回
    ``_TTL_SECONDS``；鍵不存在時 EXPIRE 為 no-op，安全。best-effort 不拋。
    """
    try:
        async with _redis() as r:
            pipe = r.pipeline()
            for key in (
                _meta_key(project_id, sub_phase),
                _crews_key(project_id, sub_phase),
                _human_key(project_id, sub_phase),
                _participated_key(project_id, sub_phase),
            ):
                pipe.expire(key, _TTL_SECONDS)
            await pipe.execute()
    except Exception:
        logger.debug("round_lock.refresh_ttl failed project=%s", project_id, exc_info=True)


async def get_state(project_id: UUID, sub_phase: str) -> dict:
    """權威回合狀態（signal_panel / warmup_exit 用）。

    失敗語意（Phase 42 B1 review 修正）：DB 讀不到席位 → 回保守空狀態（has_human
    False）；**席位讀到了但 Redis 失敗 → has_human 保留 DB 真值**、其餘欄位回保守
    預設——否則有真人的房會被誤判成全 AI 房，暖場「全員參與」gate 形同被繞過。
    """
    try:
        ai_crew, human_uid = await _seat_facts(project_id)
    except Exception:
        logger.debug("round_lock.get_state seat facts failed project=%s", project_id, exc_info=True)
        return {"has_human": False, "round": 1, "waiting": False}
    try:
        async with _redis() as r:
            meta = await r.hgetall(_meta_key(project_id, sub_phase))
            crews = set(await r.smembers(_crews_key(project_id, sub_phase)))
            human = set(await r.smembers(_human_key(project_id, sub_phase)))
            participated = set(
                await r.smembers(_participated_key(project_id, sub_phase))
            )
        round_no = int(meta.get("round") or "1")
        return {
            "has_human": human_uid is not None,
            "round": round_no,
            "waiting": meta.get("waiting") == "1",
            "ai_crew_total": len(ai_crew),
            "crews_acted": sorted(crews & ai_crew),
            "human_satisfied": _satisfies(human, sub_phase, round_no),
            "required": required_for(sub_phase, round_no),
            # Phase 42 B1（spec/28 §5.1 全員參與）：本回合真人已過檢核的輸入型態、
            # 與跨回合累積出過聲的 crew。round ≥2 或 human_inputs 非空＝真人至少參與過一次。
            "human_inputs": sorted(human),
            "participated_crews": sorted(participated & ai_crew),
            "ai_crew": sorted(ai_crew),
        }
    except Exception:
        # Redis 失敗：has_human 用 DB 真值（保守——有真人就不放行真人 gate），
        # 其餘欄位回保守預設（沒人參與過、不在等待）。
        logger.debug("round_lock.get_state redis failed project=%s", project_id, exc_info=True)
        return {
            "has_human": human_uid is not None,
            "round": 1,
            "waiting": False,
            "ai_crew_total": len(ai_crew),
            "crews_acted": [],
            "human_satisfied": False,
            "required": required_for(sub_phase, 1),
            "human_inputs": [],
            "participated_crews": [],
            "ai_crew": sorted(ai_crew),
        }


async def clear(project_id: UUID, sub_phase: str | None = None) -> None:
    """推進成功後主動解凍（發 turn_state）；給 sub_phase 時順手刪該關殘留狀態。

    回合鎖另以 sub_phase 為界天生重置，故刪除為盡力而為（不給 sub_phase 也安全）。
    """
    try:
        async with _redis() as r:
            if sub_phase:
                await r.delete(
                    _meta_key(project_id, sub_phase),
                    _crews_key(project_id, sub_phase),
                    _human_key(project_id, sub_phase),
                    _participated_key(project_id, sub_phase),
                )
        await _publish_turn_state(project_id)
    except Exception:
        logger.debug("round_lock.clear failed project=%s", project_id, exc_info=True)

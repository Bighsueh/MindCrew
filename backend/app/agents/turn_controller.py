"""Phase 28 — Turn-Taking Controller。

把「誰可以講」這件事從散落的 prompt / cooldown / assess rules 抽成單一抽象。
persona 決定「講什麼」、Controller 決定「誰講」。

三個 policy:
- :class:`CuedPolicy` — 點名模式。supervisor 永遠可講；crew 等被 cue (透過
  ``blackboard.coordination_directive.invited_speaker`` 或 chat 中被 @mention)。
- :class:`RoundRobinPolicy` — 輪流模式。Wrap ``reveal_queue.py`` FIFO；非 1.1c
  sub-phase 下，輪完一圈自動以預設順序重啟。
- :class:`OpenFloorPolicy` — 搶答模式。沿用既有 ``BaseAgent._compute_proactive_cooldown``
  公式 (已搬到本檔內)；學生 ``raise_hand`` 後下個 tick 享有優先窗口。

每次 ASSESS 階段呼叫 :func:`get_controller` 重新生成 (不快取)，這樣教師
從 ``PATCH /api/projects/{id}/turn-policy`` 切換後，下一個 tick 即生效。
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from app.agents import reveal_queue
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy enum + decision DTO
# ---------------------------------------------------------------------------


class TurnPolicy(str, Enum):
    """三模式名稱。值與 DB ``project.turn_policy`` 同步。"""

    CUED = "cued"
    ROUND_ROBIN = "round_robin"
    OPEN_FLOOR = "open_floor"


@dataclass(frozen=True)
class TurnDecision:
    """ASSESS layer 從 ``is_my_turn`` 拿到的結果。"""

    can_act: bool
    reason: str
    next_speaker: str | None = None
    allowed_actions: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# 預設順序 — 不在 reveal_queue 既有 spec 的場域使用
# ---------------------------------------------------------------------------


def _default_round_order(context: dict[str, Any]) -> list[str]:
    """從 context["seats"] 推出 RoundRobin 預設順序。

    supervisor → crew_1..N → 真人席位 (若有)。沒有 supervisor / 真人時降級到
    純 crew 順序。``reveal_queue.start_reveal_round`` 要求一個非空 list。
    """
    seats = context.get("seats") or []
    order: list[str] = []
    crew_seats: list[str] = []
    human_seats: list[str] = []
    for seat in seats:
        role = (seat.get("role") or seat.get("seat_role") or "").strip()
        occupant = (seat.get("type") or seat.get("occupant_type") or "").lower()
        if not role:
            continue
        if role == "supervisor":
            order.append(role)
        elif role.startswith("crew_"):
            crew_seats.append(role)
        if occupant == "human" and role not in order:
            human_seats.append(role)
    # crew 依 _1, _2, _3, _4 序
    crew_seats.sort()
    for seat in crew_seats:
        if seat not in order:
            order.append(seat)
    for seat in human_seats:
        if seat not in order:
            order.append(seat)
    if not order:
        # 最後保險：給一個合理 fallback，避免 start_reveal_round 收到空 list
        order = ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]
    return order


# round_robin 隊首為人類且逾時 → 視為單次 pass 自動推進（spec 20 §3.6，
# 單次、無重試）。spec 未給具體秒數，採 45s。
RR_HUMAN_TURN_TIMEOUT_SECONDS = 45.0

# cued 模式 invited_speaker 的「開放全體 crew」哨兵值（對齊 round_type=open_diverge
# 與 evaluator_guidance.publish_weak_area_guidance 寫入的 "all_crew"）。
_ALL_CREW_SENTINELS = frozenset({"all_crew", "all", "all_crews"})


def _coordination_directive(context: dict[str, Any]) -> dict[str, Any]:
    """安全取出 blackboard.coordination_directive（present-but-None 也回 {}）。"""
    blackboard = context.get("blackboard") or {}
    return blackboard.get("coordination_directive") or {}


def _cued_invited(context: dict[str, Any], my_seat: str) -> bool:
    """cued 模式：my_seat 是否被點名（含 all_crew 開放全體 crew）。"""
    invited = _coordination_directive(context).get("invited_speaker")
    if not invited:
        return False
    invited_str = str(invited).lower()
    seat = my_seat.lower()
    if invited_str in _ALL_CREW_SENTINELS:
        return seat.startswith("crew_")
    return seat in invited_str


# Phase 38 (spec/28 §7)：暖場已升格為 macro stage（0.0a），改用「組長 MC 逐一邀單一隊友」
# （cued 單席位點名）而非 open-floor surge——移除 surge 以免多 AI 同拍湧上灌爆暖場。
# 故此集合清空：0.0a 不走 open-share；1.1a 還原為一般 discover 步驟（不再 open-share）。
# 死結破除仍由 _cued_should_open_floor 的 B 分支（supervisor 講過但 crew 全沒講）保底。
_OPEN_SHARE_SUB_PHASES: frozenset[str] = frozenset()


def _cued_should_open_floor(context: dict[str, Any], my_seat: str) -> bool:
    """cued 無明確 invited_speaker 時，是否該對 crew 開放發言（避免永久凍結）。

    僅在「沒有任何明確點名」時觸發（supervisor 只要設了特定 invited_speaker 仍嚴格）：
      A) 破冰等全員分享階段（``_OPEN_SHARE_SUB_PHASES``）→ 全 crew 可分享。
      B) 死結破除：supervisor 已框題、但本關還沒有任何 AI crew 出過聲 → 開放，避免
         supervisor 一直宣告卻從不點名造成整場卡死。

    **Phase 42（1.1a 隊友沉默修復）**：B 分支改以 round_lock 的 ``participated_crews``
    為準（本關 scoped，**換關自動換鍵**），不再掃 project-wide ``recent_chat``——後者
    會被上一關（0.0a 暖場）殘留的 crew 訊息毒化、誤判「本關 crew 已講過」而永不開閘
    （即此 bug 根因）。值由 context_buffer 預先注入：
      - ``_round_lock_has_human``：本房是否有真人。
      - ``_cued_open_seat``：有真人房在死結窗口時，唯一可放行的 crew 席位（最小未分享席位；
        **一次只放一位**＝反灌爆，其餘維持嚴格等待、靠組長 B13 逐一點名）。
    這兩個鍵**僅** context_buffer 對 **1.1a** cued crew 注入；其餘 sub_phase（含全 AI 房、
    1.1a 以外的真人房）兩鍵不存在 → 一律走下方原 ``recent_chat`` 掃描分支（行為不變）。
    故 round_lock 單席位路徑只在 1.1a 真人房生效，毒化修復亦只針對「0.0a→1.1a」這條鏈。
    """
    seat = my_seat.lower()
    if not seat.startswith("crew_"):
        return False

    sub_phase = (context.get("current_sub_phase") or "").strip()
    if sub_phase in _OPEN_SHARE_SUB_PHASES:
        return True  # A

    # B：死結破除。
    if context.get("_round_lock_has_human"):
        # 真人房：round_lock 權威、本關 scoped、免毒化。只放單一未分享席位（反灌爆）。
        open_seat = context.get("_cued_open_seat")
        return bool(open_seat) and seat == str(open_seat).lower()

    # 全 AI 房：round_lock 不追蹤 → 沿用原 recent_chat 掃描（supervisor 講過但 crew 全沒講）。
    supervisor_spoke = False
    crew_spoke = False
    for msg in context.get("recent_chat") or []:
        sender = str(
            msg.get("sender_id") or msg.get("sender") or ""
        ).lower()
        if "supervisor" in sender or "引導者" in sender:
            supervisor_spoke = True
        elif "crew_" in sender:
            crew_spoke = True
    return supervisor_spoke and not crew_spoke


def _cued_crew_can_act(context: dict[str, Any], my_seat: str) -> bool:
    """cued 模式下某 crew 席位本回合能否發言（被點名 / 開放分享 / 死結破除）。"""
    if _cued_invited(context, my_seat):
        return True
    # 有明確點名給別人 → 嚴格等待；完全沒點名 → 視階段/死結決定是否開放。
    if _coordination_directive(context).get("invited_speaker"):
        return False
    return _cued_should_open_floor(context, my_seat)


def _human_seats(context: dict[str, Any]) -> set[str]:
    """context["seats"] 中 occupant 為人類的 seat_role 集合。"""
    result: set[str] = set()
    for seat in context.get("seats") or []:
        role = (seat.get("role") or seat.get("seat_role") or "").strip()
        occupant = (seat.get("type") or seat.get("occupant_type") or "").lower()
        if role and occupant == "human":
            result.add(role)
    return result


# ---------------------------------------------------------------------------
# Raise-hand 旗標 — Redis key, 後端 chat_ws.py 與 OpenFloorPolicy 共用
# ---------------------------------------------------------------------------


def _raise_hand_key(project_id: UUID) -> str:
    return f"project:{project_id}:user_priority_speak"


async def mark_user_priority_speak(project_id: UUID, seat_role: str) -> None:
    """學生按「我要發言」時呼叫。TTL 30s 自動過期。"""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.set(_raise_hand_key(project_id), seat_role, ex=30)
        finally:
            await r.aclose()
    except Exception:
        logger.debug("mark_user_priority_speak failed", exc_info=True)


async def consume_user_priority_speak(project_id: UUID) -> str | None:
    """讀取並清除 raise-hand 旗標。回傳 seat_role 或 None。"""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            value = await r.get(_raise_hand_key(project_id))
            if value:
                await r.delete(_raise_hand_key(project_id))
            return value
        finally:
            await r.aclose()
    except Exception:
        logger.debug("consume_user_priority_speak failed", exc_info=True)
        return None


async def peek_user_priority_speak(project_id: UUID) -> str | None:
    """不消耗地讀取 raise-hand 旗標 (用於 is_my_turn)。"""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            return await r.get(_raise_hand_key(project_id))
        finally:
            await r.aclose()
    except Exception:
        logger.debug("peek_user_priority_speak failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Cue retry counter — Phase 28：人類 cue 多次提醒機制
# ---------------------------------------------------------------------------


def _cue_retry_key(project_id: UUID, seat_role: str) -> str:
    """Redis key：紀錄某席位累計 retry 次數，B3 / B4 / supervisor reminder 共用。"""
    return f"project:{project_id}:cue_retry:{seat_role}"


async def reset_cue_retry(project_id: UUID, seat_role: str) -> None:
    """清掉某席位的 cue retry counter。被 cue 者回應後呼叫。

    Best-effort：Redis 失敗只 log debug，不 raise（避免阻塞 chat 主路徑）。
    """
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.delete(_cue_retry_key(project_id, seat_role))
        finally:
            await r.aclose()
    except Exception:
        logger.debug("reset_cue_retry failed", exc_info=True)


async def notify_human_speak_in_group(
    project_id: UUID,
    seat_role: str,
    policy_value: str | "TurnPolicy",
) -> None:
    """人類在群組 chat 發話的 hook（chat_ws.py 呼叫）。

    若該席位是 ``coordination_directive.invited_speaker`` →
      1. 呼叫 controller.on_speak（既有 CuedPolicy 邏輯會清掉 invited_speaker）
      2. reset_cue_retry（B4 watcher 共用的計數器）
      3. publish TurnStateEvent 通知前端

    否則 no-op（不打擾正常聊天）。

    全程 try/except 包覆，任何步驟失敗都只 log debug——
    cue 邏輯不應該因為 hook 失敗而 break user 訊息寫入。
    """
    if not seat_role:
        return
    try:
        # 1. 讀 blackboard 確認此 seat 是否被 cue
        from app.agents.blackboard import BlackboardManager

        bb = BlackboardManager(
            project_id=project_id,
            agent_id=seat_role,
            seat_role=seat_role,
        )
        directive = await bb.read_coordination_directive()
        if not directive or not directive.invited_speaker:
            return
        invited = str(directive.invited_speaker).lower()
        if seat_role.lower() not in invited:
            return  # 不是被 cue 的 seat → no-op

        # 2. 取 controller 並呼叫 on_speak（會清 invited_speaker）
        controller = await get_controller(policy_value, project_id)
        await controller.on_speak(seat_role, {"my_seat": seat_role})

        # 3. cancel cue timeout watcher（B4：避免人類已發話但 watcher 仍倒數 → 誤觸 retry）
        try:
            from app.agents.cue_timeout_watcher import cancel_cue_timeout_watcher

            cancel_cue_timeout_watcher(project_id, seat_role)
        except Exception:
            logger.debug("cancel_cue_timeout_watcher failed", exc_info=True)

        # 4. reset retry counter（B4 watcher 用）
        await reset_cue_retry(project_id, seat_role)

        # 4. publish TurnStateEvent 讓前端立即更新席位狀態
        from app.events.bus import event_bus
        from app.events.types import TurnStateEvent

        decision = await controller.is_my_turn(seat_role, {"my_seat": seat_role})
        await event_bus.publish(
            TurnStateEvent(
                project_id=project_id,
                policy=controller.policy.value,
                next_speaker=decision.next_speaker,
                allowed_actions=decision.allowed_actions,
            )
        )
    except Exception:
        logger.debug("notify_human_speak_in_group failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class TurnController(ABC):
    """各 policy 共用介面。"""

    policy: TurnPolicy

    def __init__(self, project_id: UUID) -> None:
        self.project_id = project_id

    @abstractmethod
    async def is_my_turn(
        self, my_seat: str, context: dict[str, Any]
    ) -> TurnDecision:
        """ASSESS 入口：本回合我能不能講？"""

    @abstractmethod
    async def on_speak(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        """成功送出 chat_message 後呼叫。policy 用來推進內部狀態。"""

    @abstractmethod
    async def on_pass(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        """學生 / agent 主動 pass 時呼叫。"""

    @abstractmethod
    async def compute_cooldown(
        self, my_seat: str, context: dict[str, Any], *, is_supervisor: bool
    ) -> float:
        """proactive cooldown 秒數。``float('inf')`` = 永遠不主動 act。"""

    @abstractmethod
    def system_prompt_fragment(self, context: dict[str, Any] | None = None) -> str:
        """注入 LLM system prompt 的中文段落，告知本回合的輪流規則。

        ``context`` 可選（向下相容）：政策可據此給「本回合此席位」更貼切的指示
        （如 cued 下對已開放發言的 crew 給主動分享許可，而非一律沉默）。
        """


# ---------------------------------------------------------------------------
# CuedPolicy — supervisor 主導點名
# ---------------------------------------------------------------------------


class CuedPolicy(TurnController):
    policy = TurnPolicy.CUED

    async def is_my_turn(
        self, my_seat: str, context: dict[str, Any]
    ) -> TurnDecision:
        is_supervisor = "supervisor" in my_seat.lower()
        if is_supervisor:
            return TurnDecision(
                can_act=True,
                reason="cued_supervisor_lead",
                next_speaker=my_seat,
                allowed_actions=("speak", "pass", "handoff"),
            )

        if _cued_invited(context, my_seat):
            return TurnDecision(
                can_act=True,
                reason="cued_invited",
                next_speaker=my_seat,
                allowed_actions=("speak", "pass"),
            )

        invited = _coordination_directive(context).get("invited_speaker")
        # 無明確點名時，破冰/全員分享階段或死結情境下開放 crew 發言（避免凍結）。
        if not invited and _cued_should_open_floor(context, my_seat):
            return TurnDecision(
                can_act=True,
                reason="cued_open_floor",
                next_speaker=my_seat,
                allowed_actions=("speak", "pass"),
            )

        return TurnDecision(
            can_act=False,
            reason="cued_not_invited",
            next_speaker=str(invited) if invited else None,
            allowed_actions=("pass",),
        )

    async def on_speak(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        # supervisor 講完 → blackboard 可能已被 set_directive 寫入新 invited_speaker
        # crew 講完 → 清掉 invited (避免重複命中)
        if "supervisor" in speaker_seat.lower():
            return
        try:
            from app.agents.blackboard import BlackboardManager
            from app.agents.blackboard_schemas import CoordinationDirective

            bb = BlackboardManager(
                project_id=self.project_id,
                agent_id=speaker_seat,
                seat_role=speaker_seat,
            )
            existing = await bb.read_coordination_directive()
            if existing and speaker_seat.lower() in str(
                existing.invited_speaker or ""
            ).lower():
                # 用同 round_type 覆蓋掉 invited
                cleared = CoordinationDirective(
                    round_type=existing.round_type,
                    focus_topic=existing.focus_topic,
                    invited_speaker=None,
                    instruction=existing.instruction,
                )
                await bb.write_coordination_directive(cleared)
        except Exception:
            logger.debug("CuedPolicy.on_speak clear invited failed", exc_info=True)

    async def on_pass(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        # pass 與 speak 行為相同 — 清掉自己的 invitation
        await self.on_speak(speaker_seat, context)

    async def compute_cooldown(
        self, my_seat: str, context: dict[str, Any], *, is_supervisor: bool
    ) -> float:
        # supervisor 用既有 supervisor cooldown 邏輯（移植自 OpenFloor 公式的 supervisor 分支）
        if is_supervisor:
            return _supervisor_cued_cooldown(context)
        # 被 cue 的人 cooldown=0（含 all_crew / 破冰開放 / 死結破除）；其他人不主動 (inf)
        if _cued_crew_can_act(context, my_seat):
            return 0.0
        return float("inf")

    def system_prompt_fragment(self, context: dict[str, Any] | None = None) -> str:
        base = (
            "【目前輪流規則：點名模式】\n"
            "由 Supervisor 主持，依需要點名某位成員回應。"
        )
        # crew 且本回合 floor 已對其開放（被點名 / 死結破除：組長講了但隊友都還沒講）→
        # 給「主動分享」許可，而非沉默。否則靜態沉默文案會把控制器已放行的 crew 也悶住
        # （盲測 2026-06-09：cued 單人房 crew 整場 0 發言）。
        if context is not None:
            my_seat = str(context.get("my_seat") or "")
            if my_seat.lower().startswith("crew_") and _cued_crew_can_act(
                context, my_seat
            ):
                return (
                    base
                    + "現在輪到你了——請主動分享一個你的角度或觀察（一次一個重點即可），"
                    "不要只是旁觀等別人。"
                )
        return (
            base
            + "被 @點名的成員必須在下一輪回應或 pass；未被點名者請保持沉默觀察，"
            "避免搶話。Supervisor 負責確保發言均衡。"
        )


def _supervisor_cued_cooldown(context: dict[str, Any]) -> float:
    """Cued 模式下 supervisor 的 cooldown。

    使用既有 ``_compute_proactive_cooldown`` 的 supervisor 分支邏輯，避免 supervisor
    在 all-AI 下每 2-7 秒就再開口 (fix #2)。
    """
    seats = context.get("seats", [])
    is_all_ai = all((s.get("type") or "ai") == "ai" for s in seats)
    recent_chat = context.get("recent_chat", [])
    human_active = any(
        m.get("sender_type") == "human" for m in recent_chat[-10:]
    )
    if is_all_ai or not human_active:
        base = 40.0
    else:
        base = 30.0
    active_thread = context.get("active_thread")
    if active_thread and active_thread.get("turn_count", 0) <= 3:
        base *= 0.5
    last_event_time = context.get("_last_event_time")
    if last_event_time:
        silence = time.time() - last_event_time
        if silence > 20:
            base *= 0.3
    return base


# ---------------------------------------------------------------------------
# RoundRobinPolicy — wrap reveal_queue.py
# ---------------------------------------------------------------------------


class RoundRobinPolicy(TurnController):
    policy = TurnPolicy.ROUND_ROBIN

    # 1.1c 是既有 Spec 13 reveal_round 場域，由 phase machine 自管 — 我們不在
    # 那裡自動重啟，避免與 phase 推進衝突。
    PHASE_MACHINE_OWNED_SUB_PHASES: frozenset[str] = frozenset({"1.1c"})

    async def is_my_turn(
        self, my_seat: str, context: dict[str, Any]
    ) -> TurnDecision:
        # spec 20 §3.6：隊首是人類且逾時 → 自動 pass 推進，避免 RR 卡死在
        # 不回應的人類席位（單次、無重試）。先處理再做常規輪序判斷。
        human_seats = _human_seats(context)
        if human_seats:
            await reveal_queue.timeout_advance_human_head(
                self.project_id, human_seats, RR_HUMAN_TURN_TIMEOUT_SECONDS
            )
        next_seat = await reveal_queue.peek_next_seat(self.project_id)
        if next_seat is None:
            # queue 空 — 在非 1.1c 的場域，自動以預設順序重啟一輪
            sub_phase = (context.get("current_sub_phase") or "").strip()
            if sub_phase in self.PHASE_MACHINE_OWNED_SUB_PHASES:
                return TurnDecision(
                    can_act=False,
                    reason="round_robin_phase_machine_owned_empty",
                    next_speaker=None,
                    allowed_actions=(),
                )
            await reveal_queue.start_reveal_round(
                self.project_id,
                _default_round_order(context),
                sub_phase or "auto",
            )
            next_seat = await reveal_queue.peek_next_seat(self.project_id)

        if next_seat is None:
            # 還是空 — 罕見場景 (seat_order 全空)，保守 wait
            return TurnDecision(
                can_act=False,
                reason="round_robin_empty_after_restart",
                next_speaker=None,
                allowed_actions=(),
            )

        if next_seat == my_seat:
            return TurnDecision(
                can_act=True,
                reason="round_robin_my_turn",
                next_speaker=my_seat,
                allowed_actions=("speak", "pass"),
            )

        return TurnDecision(
            can_act=False,
            reason="round_robin_not_my_turn",
            next_speaker=next_seat,
            allowed_actions=("pass",),
        )

    async def on_speak(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        await reveal_queue.advance_reveal(self.project_id, speaker_seat)

    async def on_pass(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        # pass 視同講過 — queue 推進，輪到下一位
        await reveal_queue.advance_reveal(self.project_id, speaker_seat)

    async def compute_cooldown(
        self, my_seat: str, context: dict[str, Any], *, is_supervisor: bool
    ) -> float:
        decision = await self.is_my_turn(my_seat, context)
        return 0.0 if decision.can_act else float("inf")

    def system_prompt_fragment(self, context: dict[str, Any] | None = None) -> str:
        return (
            "【目前輪流規則：輪流模式】\n"
            "每位成員依固定順序輪流發言，輪到時可以發言或選擇 pass。"
            "新想法請等所有人都輪完一圈後再提出，現在請聚焦於補強或回應已被講出的觀點。"
        )


# ---------------------------------------------------------------------------
# OpenFloorPolicy — 既有 _compute_proactive_cooldown 公式 + raise-hand 優先
# ---------------------------------------------------------------------------


class OpenFloorPolicy(TurnController):
    policy = TurnPolicy.OPEN_FLOOR

    async def is_my_turn(
        self, my_seat: str, context: dict[str, Any]
    ) -> TurnDecision:
        # 學生 raise_hand 後，下一個 tick 強制讓人類優先
        priority_seat = await peek_user_priority_speak(self.project_id)
        if priority_seat and priority_seat != my_seat:
            return TurnDecision(
                can_act=False,
                reason="open_floor_user_priority",
                next_speaker=priority_seat,
                allowed_actions=("pass",),
            )

        return TurnDecision(
            can_act=True,
            reason="open_floor",
            next_speaker=None,
            allowed_actions=("speak", "pass", "raise_hand"),
        )

    async def on_speak(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        # 真人發言後清掉 raise-hand 旗標
        priority_seat = await peek_user_priority_speak(self.project_id)
        if priority_seat and priority_seat == speaker_seat:
            await consume_user_priority_speak(self.project_id)

    async def on_pass(
        self, speaker_seat: str, context: dict[str, Any]
    ) -> None:
        # 沒有 queue 要推進，但 pass 同樣消耗 raise-hand 視窗
        priority_seat = await peek_user_priority_speak(self.project_id)
        if priority_seat and priority_seat == speaker_seat:
            await consume_user_priority_speak(self.project_id)

    async def compute_cooldown(
        self, my_seat: str, context: dict[str, Any], *, is_supervisor: bool
    ) -> float:
        return _open_floor_cooldown(context, my_seat, is_supervisor=is_supervisor)

    def system_prompt_fragment(self, context: dict[str, Any] | None = None) -> str:
        return (
            "【目前輪流規則：搶答模式】\n"
            "任何人都可以主動發言，但不要連續搶話。"
            "看到沉默 5 秒以上、或有人剛點出值得回應的觀點，再考慮插入。"
            "若人類成員按下「我要發言」，請禮讓並先讓人類講。"
        )


def _open_floor_cooldown(
    context: dict[str, Any], my_seat: str, *, is_supervisor: bool
) -> float:
    """既有 ``BaseAgent._compute_proactive_cooldown`` 公式整段搬來。

    保留原本注釋 (Fix #2) 與所有分支條件，避免行為漂移。
    """
    seats = context.get("seats", [])
    is_all_ai = all((s.get("type") or "ai") == "ai" for s in seats)
    recent_chat = context.get("recent_chat", [])
    human_active = any(
        m.get("sender_type") == "human" for m in recent_chat[-10:]
    )
    if is_all_ai or not human_active:
        # All-AI mode OR human present but silent: equal footing, short cooldown.
        # Fix #2: supervisor 不套 0.3 倍率，避免在 all-AI 下每 2-7 秒就再開口。
        if is_supervisor:
            base = 40.0
        else:
            base = 25.0 * 0.3
    else:
        # Human actively participating: longer cooldown to give them space
        base = 30.0 if is_supervisor else 40.0

    active_thread = context.get("active_thread")
    if active_thread and active_thread.get("turn_count", 0) <= 3:
        base *= 0.5

    last_event_time = context.get("_last_event_time")
    if last_event_time:
        silence = time.time() - last_event_time
        if silence > 20:
            base *= 0.3

    # Cued mode 把 directive bypass 邏輯收回去；Open-Floor 仍允許 supervisor 透過
    # directive 緊急優先點名 (但行為遠較 Cued 寬鬆 — 大多時候不會 fire)。
    directive = context.get("blackboard", {}).get("coordination_directive")
    if directive and directive.get("invited_speaker"):
        invited = str(directive["invited_speaker"])
        if my_seat.lower() in invited.lower():
            return 0.0

    return base


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_POLICY_TO_CLASS: dict[TurnPolicy, type[TurnController]] = {
    TurnPolicy.CUED: CuedPolicy,
    TurnPolicy.ROUND_ROBIN: RoundRobinPolicy,
    TurnPolicy.OPEN_FLOOR: OpenFloorPolicy,
}


def parse_policy(value: str | TurnPolicy | None) -> TurnPolicy:
    """容錯地把字串轉成 ``TurnPolicy``。不合法回 CUED (預設)。"""
    if isinstance(value, TurnPolicy):
        return value
    cleaned = (value or "").strip().lower()
    try:
        return TurnPolicy(cleaned)
    except ValueError:
        return TurnPolicy.CUED


async def get_controller(
    policy: str | TurnPolicy, project_id: UUID
) -> TurnController:
    """Factory。**每次 ASSESS 重取，不快取**，這樣 PATCH 切換後下個 tick 即生效。"""
    enum_policy = parse_policy(policy)
    cls = _POLICY_TO_CLASS[enum_policy]
    return cls(project_id)

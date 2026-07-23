"""回合鎖＋實質檢核（Phase 42 A2，spec 20 v2.0 §11/§12）。

純函式（型態表 / 滿足判定 / tier-1）不需基礎設施；狀態機測試用真 Redis
（settings.REDIS_URL，與既有 redis 測試同慣例）＋ monkeypatch `_seat_facts`
與事件 publish，以唯一 project_id 隔離、finally clear。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents import human_input_check as hic
from app.agents import round_lock
from app.events.types import InputBouncedEvent, WaitingForHumanEvent

# ---------------------------------------------------------------------------
# 純函式：逐關型態表 / required / 滿足判定（spec 20 §11.4）
# ---------------------------------------------------------------------------


def test_gate_types_warmup_dual_then_any():
    assert round_lock.gate_types_for("0.0a", 1) == (("note", "chat"), "all")
    assert round_lock.gate_types_for("0.0a", 2) == (("note", "chat"), "any")
    assert round_lock.gate_types_for("0.0a", 5) == (("note", "chat"), "any")


def test_gate_types_table_and_defaults():
    assert round_lock.gate_types_for("1.1a", 1) == (("chat",), "any")
    assert round_lock.gate_types_for("1.1b", 1) == (("note",), "any")
    assert round_lock.gate_types_for("1.1d", 1) == (("chat", "note"), "any")
    assert round_lock.gate_types_for("2.1", 1) == (("move", "chat"), "all")
    assert round_lock.gate_types_for("2.6", 1) == (("move", "chat"), "all")
    assert round_lock.gate_types_for("2.7", 1) == (("confirm",), "any")
    # 未知 / legacy（0.1/0.2/1.3–1.6）→ 降級「聊天・擇一」（A2 先於 C1 落地）。
    assert round_lock.gate_types_for("9.9", 1) == (("chat",), "any")
    assert round_lock.gate_types_for("1.5", 1) == (("chat",), "any")


def test_required_for_payload_shape():
    r = round_lock.required_for("2.1", 1)
    assert r == {"note": False, "chat": True, "move": True, "confirm": False, "mode": "all"}
    r2 = round_lock.required_for("0.0a", 1)
    assert r2["note"] and r2["chat"] and r2["mode"] == "all"
    r3 = round_lock.required_for("0.0a", 3)
    assert r3["mode"] == "any"


def test_satisfies_any_all_and_chat_confirm_interchange():
    assert round_lock._satisfies({"chat"}, "1.1a", 1)
    assert not round_lock._satisfies(set(), "1.1a", 1)
    # 2.1 拖 AND 說：兩件都要
    assert not round_lock._satisfies({"chat"}, "2.1", 1)
    assert not round_lock._satisfies({"move"}, "2.1", 1)
    assert round_lock._satisfies({"move", "chat"}, "2.1", 1)
    # 1.1b 貼：chat 不能頂替 note
    assert not round_lock._satisfies({"chat"}, "1.1b", 1)
    assert round_lock._satisfies({"note"}, "1.1b", 1)
    # 2.7 確認：chat 與 confirm 互通
    assert round_lock._satisfies({"chat"}, "2.7", 1)
    assert round_lock._satisfies({"confirm"}, "2.7", 1)
    # 0.0a 教學回合（mode all）：貼+聊缺一不可
    assert not round_lock._satisfies({"chat"}, "0.0a", 1)
    assert round_lock._satisfies({"note", "chat"}, "0.0a", 1)
    # 0.0a 之後回合（mode any）：任一即可
    assert round_lock._satisfies({"chat"}, "0.0a", 2)


# ---------------------------------------------------------------------------
# 純函式：tier-1 規則層（spec 20 §12.2）
# ---------------------------------------------------------------------------


def test_tier1_length_floor():
    assert hic.tier1_pass("好")[0] is False                  # 1 字 < 5
    assert hic.tier1_pass("我覺得這個想法不錯")[0] is True     # ≥5


def test_tier1_pure_emoji_and_punct():
    assert hic.tier1_pass("👍👍👍")[0] is False
    assert hic.tier1_pass("。。。！！！")[0] is False
    assert hic.tier1_pass("")[0] is False


def test_tier1_perfunctory_and_repeat():
    assert hic.tier1_pass("哈哈哈哈哈")[0] is False     # 單一重複字元填充
    assert hic.tier1_pass("嗯嗯嗯嗯嗯嗯")[0] is False
    ok, reason = hic.tier1_pass("好", is_confirm_context=True)
    assert ok and reason == "confirm_whitelist"           # confirm 白名單跳過


@pytest.mark.asyncio
async def test_check_human_input_passes_substantive_without_llm():
    res = await hic.check_human_input("衣架可以掰直拿來通水管", "0.0a", llm_ctx=None)
    assert res.passed


@pytest.mark.asyncio
async def test_check_human_input_bounce_has_clean_hint():
    res = await hic.check_human_input("好", "0.0a", llm_ctx=None)
    assert not res.passed
    assert res.reason_zh and res.hint_zh
    # #29：退回話術不得含內部機制詞
    for w in ("gate", "檢核", "規則", "回合鎖", "解鎖", "tier"):
        assert w not in res.reason_zh and w not in res.hint_zh


@pytest.mark.asyncio
async def test_check_human_input_confirm_context_passes_short():
    res = await hic.check_human_input("好", "2.7", llm_ctx=None, is_confirm_context=True)
    assert res.passed


# ── A2 補強：note 型輸入（human_create_note 端點接線）────────────────────────


def test_tier1_note_floor_allows_short_names():
    # 1.1b 便條只寫名字（spec 22/brief §3）：「學生」=2 字須過 note 地板。
    assert hic.tier1_pass("學生", input_type="note")[0] is True
    assert hic.tier1_pass("學生")[0] is False        # chat 地板仍 ≥5
    assert hic.tier1_pass("好", input_type="note")[0] is False   # 1 字仍擋
    assert hic.tier1_pass("👍", input_type="note")[0] is False   # 純 emoji 仍擋
    assert hic.tier1_pass("都可以", input_type="note")[0] is False  # 黑名單仍擋


def test_tier1_two_char_reduplicated_names_pass():
    # 疊字名稱（媽媽/爸爸）是正當利害關係人，不可被「單一重複字」誤殺；
    # 「哈哈」由黑名單擋、「哈哈哈」由 ≥3 字重複填充擋。
    assert hic.tier1_pass("媽媽", input_type="note")[0] is True
    assert hic.tier1_pass("哈哈", input_type="note")[0] is False
    assert hic.tier1_pass("哈哈哈", input_type="note")[0] is False


@pytest.mark.asyncio
async def test_process_group_input_note_registers(monkeypatch):
    calls: list = []

    async def fake_register(pid, sub, t):
        calls.append((sub, t))
        return True

    monkeypatch.setattr(round_lock, "register_human_input", fake_register)
    completed = await hic.process_group_input(
        uuid4(), uuid4(), "超商店員", "note", sub_phase="1.1b"
    )
    assert completed is True
    assert calls == [("1.1b", "note")]


@pytest.mark.asyncio
async def test_process_group_input_perfunctory_bounces(monkeypatch):
    registered: list = []
    bounced: list = []

    async def fake_register(pid, sub, t):
        registered.append(t)
        return True

    async def fake_publish(event):
        bounced.append(event.to_dict()["type"])

    monkeypatch.setattr(round_lock, "register_human_input", fake_register)
    from app.events import bus as event_bus_module

    monkeypatch.setattr(event_bus_module.event_bus, "publish", fake_publish)
    completed = await hic.process_group_input(
        uuid4(), uuid4(), "好", "chat", sub_phase="1.1a"
    )
    assert completed is False
    assert registered == []
    assert bounced == ["input_bounced"]


@pytest.mark.asyncio
async def test_process_group_input_blank_sub_phase_noop(monkeypatch):
    async def fake_register(pid, sub, t):
        raise AssertionError("空 sub_phase 不應註冊")

    monkeypatch.setattr(round_lock, "register_human_input", fake_register)
    assert await hic.process_group_input(
        uuid4(), uuid4(), "具體的有效輸入內容", "chat", sub_phase=""
    ) is False


# ---------------------------------------------------------------------------
# 狀態機（真 Redis；monkeypatch seats / publish）
# ---------------------------------------------------------------------------


@pytest.fixture
def captured(monkeypatch):
    waits: list = []
    turns: list = []

    async def fake_waiting(project_id, sub_phase, round_no, human_uid):
        waits.append((str(project_id), sub_phase, round_no, human_uid))

    async def fake_turn(project_id):
        turns.append(str(project_id))

    monkeypatch.setattr(round_lock, "_publish_waiting", fake_waiting)
    monkeypatch.setattr(round_lock, "_publish_turn_state", fake_turn)
    return {"waits": waits, "turns": turns}


def _patch_seats(monkeypatch, ai_crew, human_uid):
    async def fake_facts(project_id):
        return set(ai_crew), human_uid

    monkeypatch.setattr(round_lock, "_seat_facts", fake_facts)


@pytest.mark.asyncio
async def test_all_crew_act_then_freeze(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2", "crew_3"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "1.1a", "crew_1")
        await round_lock.mark_crew_output(pid, "1.1a", "crew_2")
        assert captured["waits"] == []  # 還沒全輪過
        blocked, _ = await round_lock.is_crew_blocked(pid, "1.1a", "crew_1")
        assert blocked  # crew_1 本回合已輸出
        free, _ = await round_lock.is_crew_blocked(pid, "1.1a", "crew_3")
        assert not free
        await round_lock.mark_crew_output(pid, "1.1a", "crew_3")
        assert len(captured["waits"]) == 1  # 全輪過 → 凍結
        b3, _ = await round_lock.is_crew_blocked(pid, "1.1a", "crew_3")
        assert b3  # waiting → 全擋
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_human_input_unlocks_next_round(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "1.1a", "crew_1")
        await round_lock.mark_crew_output(pid, "1.1a", "crew_2")  # 凍結
        completed = await round_lock.register_human_input(pid, "1.1a", "chat")
        assert completed is True
        b, _ = await round_lock.is_crew_blocked(pid, "1.1a", "crew_1")
        assert not b  # 新回合，crew_1 可再行動
        st = await round_lock.get_state(pid, "1.1a")
        assert st["round"] == 2 and not st["waiting"]
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_perfunctory_not_registered_keeps_frozen(monkeypatch, captured):
    # register_human_input 只應在「過實質檢核」後呼叫；未呼叫 → 凍結維持（敷衍不解鎖）。
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "1.1a", "crew_1")  # 凍結
        st = await round_lock.get_state(pid, "1.1a")
        assert st["waiting"]  # 真人沒有有效輸入 → 仍凍結
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_all_ai_house_never_freezes(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2"}, None)  # 無真人
    try:
        await round_lock.mark_crew_output(pid, "1.1a", "crew_1")
        await round_lock.mark_crew_output(pid, "1.1a", "crew_2")
        assert captured["waits"] == []
        b, _ = await round_lock.is_crew_blocked(pid, "1.1a", "crew_1")
        assert not b
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_dual_gate_needs_both_legs(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "2.1", "crew_1")  # 凍結
        assert len(captured["waits"]) == 1
        c1 = await round_lock.register_human_input(pid, "2.1", "chat")
        assert c1 is False  # 缺「拖」
        assert (await round_lock.get_state(pid, "2.1"))["waiting"]
        c2 = await round_lock.register_human_input(pid, "2.1", "move")
        assert c2 is True
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_note_cell_chat_does_not_unlock(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "1.1b", "crew_1")  # 凍結
        assert await round_lock.register_human_input(pid, "1.1b", "chat") is False
        assert await round_lock.register_human_input(pid, "1.1b", "note") is True
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_warmup_round1_requires_note_and_chat(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "0.0a", "crew_1")  # 凍結
        assert await round_lock.register_human_input(pid, "0.0a", "chat") is False
        assert await round_lock.register_human_input(pid, "0.0a", "note") is True
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_sub_phase_change_auto_resets(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "1.1a", "crew_1")  # 凍結 1.1a
        assert (await round_lock.is_crew_blocked(pid, "1.1a", "crew_1"))[0]
        # 推進到 1.1b → 以 sub_phase 為界天生重置（time-box 穿透凍結的基礎）
        b, _ = await round_lock.is_crew_blocked(pid, "1.1b", "crew_1")
        assert not b
        st = await round_lock.get_state(pid, "1.1b")
        assert st["round"] == 1 and not st["waiting"]
    finally:
        await round_lock.clear(pid)


@pytest.mark.asyncio
async def test_declare_round_end_freezes_without_full_cycle(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2"}, "u1")
    try:
        await round_lock.declare_round_end(pid, "1.1a")  # 組長 cue 真人，crew 未全輪
        assert len(captured["waits"]) == 1
        assert (await round_lock.is_crew_blocked(pid, "1.1a", "crew_1"))[0]
        # declared 後真人有效輸入仍能解鎖（即使 crew 未全輪過）
        assert await round_lock.register_human_input(pid, "1.1a", "chat") is True
        st = await round_lock.get_state(pid, "1.1a")
        assert st["round"] == 2 and not st["waiting"]
    finally:
        await round_lock.clear(pid)


# ---------------------------------------------------------------------------
# WS 事件 payload（spec 06 §3.1 / spec 20 §5.6/§5.7）
# ---------------------------------------------------------------------------


def test_waiting_for_human_event_payload():
    e = WaitingForHumanEvent(
        project_id=uuid4(),
        sub_phase="0.0a",
        round=1,
        required={"note": True, "chat": True, "move": False, "confirm": False, "mode": "all"},
        target_user_id="u1",
    )
    d = e.to_dict()
    assert d["type"] == "waiting_for_human"
    p = d["payload"]
    assert p["sub_phase"] == "0.0a" and p["round"] == 1
    assert p["required"]["mode"] == "all" and p["target_user_id"] == "u1"
    assert "chat_id" not in p  # 無 chat_id → 廣播全房


def test_input_bounced_event_payload():
    e = InputBouncedEvent(project_id=uuid4(), user_id="u1", reason_zh="r", hint_zh="h")
    d = e.to_dict()
    assert d["type"] == "input_bounced"
    assert d["payload"]["reason_zh"] == "r" and d["payload"]["hint_zh"] == "h"
    assert "chat_id" not in d["payload"]


# ---------------------------------------------------------------------------
# Phase 42 B1：累積參與集合（participated）＋ get_state 新欄位（spec 28 §5.1）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_participated_persists_across_rounds(monkeypatch, captured):
    """跨回合累積：crew_1 在第 1 回合出過聲，回合完成清掉 per-round 集合後仍在 participated。"""
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "0.0a", "crew_1")
        await round_lock.mark_crew_output(pid, "0.0a", "crew_2")  # 全輪過 → 凍結
        await round_lock.register_human_input(pid, "0.0a", "chat")
        await round_lock.register_human_input(pid, "0.0a", "note")  # R1 雙工具 → round 2
        st = await round_lock.get_state(pid, "0.0a")
        assert st["round"] == 2
        assert st["crews_acted"] == []  # per-round 集合已清
        assert st["participated_crews"] == ["crew_1", "crew_2"]  # 累積集合不清
        assert st["ai_crew"] == ["crew_1", "crew_2"]
    finally:
        await round_lock.clear(pid, "0.0a")


@pytest.mark.asyncio
async def test_clear_erases_participated(monkeypatch, captured):
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    await round_lock.mark_crew_output(pid, "0.0a", "crew_1")
    st = await round_lock.get_state(pid, "0.0a")
    assert st["participated_crews"] == ["crew_1"]
    await round_lock.clear(pid, "0.0a")
    st2 = await round_lock.get_state(pid, "0.0a")
    assert st2["participated_crews"] == []


@pytest.mark.asyncio
async def test_get_state_human_inputs_mid_round(monkeypatch, captured):
    """真人本回合已有過檢核輸入（round 未完成）→ human_inputs 反映型態。"""
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1", "crew_2"}, "u1")
    try:
        await round_lock.register_human_input(pid, "1.1b", "note")
        st = await round_lock.get_state(pid, "1.1b")
        assert st["round"] == 1  # crew 未全輪過，回合未完成
        assert st["human_inputs"] == ["note"]
    finally:
        await round_lock.clear(pid, "1.1b")


@pytest.mark.asyncio
async def test_get_state_all_ai_house_empty_tracking(monkeypatch, captured):
    """全 AI 房：mark_crew_output 不追蹤 → participated_crews 恆空、has_human=False。"""
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, None)
    await round_lock.mark_crew_output(pid, "0.0a", "crew_1")
    st = await round_lock.get_state(pid, "0.0a")
    assert st["has_human"] is False
    assert st["participated_crews"] == []


@pytest.mark.asyncio
async def test_get_state_redis_failure_keeps_db_has_human(monkeypatch, captured):
    """B1 review 修正：席位讀到（有真人）但 Redis 失敗 → has_human 不可塌成 False。

    否則暖場「全員參與」gate 會把有真人的房誤判成全 AI 房而被繞過。
    """
    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")

    class _BrokenRedis:
        async def __aenter__(self):
            raise ConnectionError("redis down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(round_lock, "_redis", lambda: _BrokenRedis())
    st = await round_lock.get_state(pid, "0.0a")
    assert st["has_human"] is True  # DB 真值保留
    assert st["human_satisfied"] is False  # 保守：不視為已參與
    assert st["participated_crews"] == []


@pytest.mark.asyncio
async def test_refresh_ttl_extends_existing_keys(monkeypatch, captured):
    """Phase 42 補正 R4（裁定⑤）：喚醒續期——既有鍵 TTL 續回 _TTL_SECONDS；
    鍵不存在時 no-op 不炸。"""
    import redis.asyncio as aioredis

    from app.config import settings

    pid = uuid4()
    _patch_seats(monkeypatch, {"crew_1"}, "u1")
    try:
        await round_lock.mark_crew_output(pid, "2.2", "crew_1")
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            meta_key = round_lock._meta_key(pid, "2.2")
            # 人工把 TTL 壓低，模擬「休眠很久、快過期」。
            await r.expire(meta_key, 5)
            assert (await r.ttl(meta_key)) <= 5
            await round_lock.refresh_ttl(pid, "2.2")
            assert (await r.ttl(meta_key)) > 3000  # 續回 ~3600
        finally:
            await r.aclose()
        # 無鍵 sub_phase：安全 no-op。
        await round_lock.refresh_ttl(pid, "9.9")
    finally:
        await round_lock.clear(pid)

"""Unified LLM judge layer — Spec 14 §5 / Phase 18 Step A0.

提供統一的 LLM-based 內容判斷介面，取代散落各處的 regex 純規則判斷。

三層架構：
  Tier 1: regex / 啟發式 預過濾（快、抓明顯違規）
  Tier 2: LLM judge（考慮上下文，能處理引述 / 否定 / Meta 討論）
  Tier 3: LLM 失敗時保守 pass（不擋），結果寫入 trace 供老師查看

特性：
  - 內容指紋快取（sha1 + rule_module，60 秒 TTL）
  - 批次評估 API（同 tick 多個 rule 合併成一個 LLM call）
  - 結果寫入 agent_decision_trace（teacher dashboard 可見）
  - LLM 失敗 fallback 至 pass，不阻塞流程
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from app.config import settings
from app.llm.factory import LLMProviderFactory
from app.llm.json_utils import parse_llm_json

logger = logging.getLogger(__name__)

Verdict = Literal["pass", "violate", "borderline"]


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JudgeResult:
    """單次 LLM judge 的結構化結果。"""

    verdict: Verdict
    confidence: float           # 0.0–1.0
    reasoning_zh: str
    rule_module: str
    fallback_used: bool = False  # True 表示走了 conservative pass


@dataclass(frozen=True)
class BatchJudgeResult:
    """批次評估：rule_module → JudgeResult。"""

    results: dict[str, JudgeResult]
    total_llm_ms: int
    cache_hits: int = 0


# ---------------------------------------------------------------------------
# Rule module prompts
# ---------------------------------------------------------------------------

# 每個 rule_module 一份 system prompt（用 LLM 判斷的提示）
_RULE_PROMPTS: dict[str, str] = {
    # Phase 42 C1：no_interpretation／empathy_says_no_inference 判準隨舊 1.5/1.6 移除
    # （全程 assumption-based，無「原始觀察」可言，spec 04-06 v4.25 §5.5）。

    "no_feature_jump": """你正在審查「發想痛點與情境」階段的便條紙。
本階段只描述具體情境與卡點（誰、在什麼情況下、卡在哪），先不想解法；
寫成「他需要某個功能 / 一個 App」屬於跳到功能，要提醒改寫（軟性擋下）。

請判斷以下文字是否違規：
- pass：描述具體情境與卡點（「結帳時才想起沒帶袋子」）、引述既有做法或失敗案例、否定句（「不是要做 App」）、Meta 討論
- violate：把痛點寫成功能或產品需求（「他需要一個提醒功能」「做一個 App 幫他記」）
- borderline：難以判斷時""",

    "no_solution_language": """你正在審查 Define（Phase 2）階段的便條紙或聊天訊息。
Phase 2 是定義問題，禁止直接寫解法（build / design a / 做一個 / 開發 / 設計一個 / 我們應該做 X）。

請判斷以下文字是否違規：
- pass：定義問題、描述觀察、POV 句型「[使用者] 需要 [需求]，因為 [洞察]」、否定句（「我們不應該做一個 App」）、引述過去的失敗案例
- violate：直接陳述要做什麼解法（「做一個 App」「開發一個提醒系統」「我們應該蓋一個 wizard」）
- borderline：難以判斷時""",

    "no_feasibility_talk": """你正在審查發散階段的便條紙或聊天訊息。
發散階段禁止可行性討論（技術 / 成本 / 時間 / 實際性）。

請判斷以下文字是否違規：
- pass：拋出點子、引述使用者抱怨成本、Meta 討論
- violate：評估某想法的可行性（「這做不到」「成本太高」「技術不可行」「來不及」「不實際」），或疑問句評估（「這能做嗎?」「這要多久?」）
- borderline：難以判斷時""",

    "no_production_code": """你正在審查 4-1f「雛形製作」階段（v1）的便條紙或聊天訊息。
v1 強制 low-fidelity（paper / sketch / wireframe / Figma click-through / role-play），禁止 production code。

請判斷以下文字是否違規：
- pass：描述 paper / wireframe / role-play 雛形、闡明 high-fi 必要的理由
- violate：要求正式上線 / production / 完整實作
- borderline：難以判斷時""",

    "no_criticism": """你正在審查 DT 流程中任何階段的聊天訊息。
DT 規則：禁止批評他人的想法（含委婉批評）；有疑慮可以補充或提出不同角度，但不否定別人。

請判斷以下文字是否違規：
- pass：建設性追問、補充細節、提出不同視角、Meta 討論
- violate：直接否定他人想法（「這不可能」「太蠢」「太貴」「不切實際」「這做不出來」「沒人會用」）、委婉批評（「這個方向我覺得 emm...」「不是說不好啦，但...」）
- borderline：難以判斷時""",

    "pov_quality": """你正在審查一張 2-2 階段的 POV 便條紙。
合格的 POV 必須：
  1. 三欄都填：[USER] 需要 [NEED]，因為 [INSIGHT]
  2. INSIGHT 必須回答「為什麼這個需求對這位使用者特別重要」
  3. INSIGHT 不能是 NEED 的同義反覆

請判斷以下 POV 文字是否合格：
- pass：三欄完整、INSIGHT 與 NEED 不同義、INSIGHT 解釋了背後脈絡
- violate：INSIGHT 是 NEED 的同義反覆（例：「需要快速結帳，因為他想要快速結帳」）、INSIGHT 空泛
- borderline：難以判斷時""",

    "mention_detection": """你正在判斷一句聊天訊息是否在點名某個 agent 或角色。
被點名的 agent 通常會回應；沒被點名則可選擇旁觀。

請判斷以下文字是否在點名 target agent：
- pass（= 沒被點名）：泛指、討論他人、Meta 討論
- violate（= 有點名）：明確 @標記、稱呼角色名（「同理心專家」/「empathy 大師」/「@crew_1」/ 「結構化的你」）、提問且明顯指向特定人
- borderline：難以判斷時""",

    "deliverable_quality": """你正在判斷一個 sub-phase 的產出物（便條紙集合）是否品質達到推進下一階段的標準。
請依該 sub-phase 的目標審視內容。

- pass：產出物有實質內容、回應了 sub-phase 目標
- violate：產出物空洞 / 敷衍 / 與目標脫節
- borderline：難以判斷時""",

    "debrief_depth": """你正在審查一張 4-2 Debrief 三題的答案便條紙。
合格的答案必須有實質內容，不能是「ok / 沒問題 / 大家都同意」這類空話。

- pass：答案具體、有信念對比 / 有引用前面階段的觀察
- violate：空洞、單字回應、與題目無關
- borderline：難以判斷時""",

    "task_hypothesis_alignment": """你正在審查一張 Task Ticket 是否真的能驗證它對應的 Hypothesis。

- pass：Task 驗收條件能直接證實 / 否證 Hypothesis 的 success / fail 條件
- violate：Task 與 Hypothesis 無對應關係 / 驗收條件無法驗證假設
- borderline：難以判斷時""",

    "off_topic": """你正在判斷團隊聊天中最新一則成員訊息是否偏離當前任務（spec 15 §2.3.1）。

請判斷以下文字是否偏離：
- pass：與當前任務相關的貢獻——提想法、接話、表態、給理由、回答別人的問題、操作說明
- violate：規則外／好奇／搞不清楚狀況的提問（「現在是哪一關？」「這題到底要幹嘛？」「那個群是什麼意思？」），或與當前任務無關的閒聊岔題
- borderline：難以判斷時""",

    "silence_type": """有某 agent 已 N 分鐘無發言。請依當前 chat 氣氛判斷是哪種沉默：

- pass（= 思考型）：其他人也安靜 / 在寫便條 / 正在獨立發散，這是健康沉默不需打擾
- violate（= 退縮型）：其他人熱絡討論、該 agent 明顯被晾在一邊，需要組長點名邀請
- borderline：難以判斷時""",

    "category_diversity": """你正在審查 Idea pool 的點子集合。
請判斷點子是否集中在同一機制 / 類別。

- pass：點子多元、涵蓋多種機制
- violate：集中在同一機制（例如「全部都在加新功能」「全部都是 app 介面方案」）
- borderline：難以判斷時""",

    "must_be_concept": """你正在審查一張「接話式」便條紙。
接話式的每張便條必須是**沉澱後的概念／洞見**（一句可獨立成立的判斷或主張），
不是逐字對白、不是問句、不是聊天記錄。

請判斷以下文字是否違規：
- pass：沉澱後的概念 / 洞見（例：「在意 CP 值，不是單純嫌貴」「願意為品質多付一點」），即使含問號的反詰式洞察也算
- violate：逐字對白（「他說：隔壁便宜兩成」）、純資訊問句（「跟哪一家比？」「為什麼這麼貴？」）、聊天填充語（「嗯嗯好喔」）
- borderline：難以判斷時""",
}


_DEFAULT_PROMPT = """請判斷以下文字是否違反規則 '{rule_module}'：
- pass：未違規
- violate：明顯違規
- borderline：難以判斷"""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_KEY_TMPL = "judge_cache:{fingerprint}:{rule}"
_CACHE_TTL = 60  # seconds


def _fingerprint(text: str) -> str:
    """Content fingerprint (truncated SHA1)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _cache_get(fingerprint: str, rule_module: str) -> JudgeResult | None:
    try:
        r = await _get_redis()
        try:
            raw = await r.get(_CACHE_KEY_TMPL.format(fingerprint=fingerprint, rule=rule_module))
        finally:
            await r.aclose()
        if not raw:
            return None
        data = json.loads(raw)
        return JudgeResult(
            verdict=data["verdict"],
            confidence=float(data["confidence"]),
            reasoning_zh=data["reasoning_zh"],
            rule_module=rule_module,
            fallback_used=bool(data.get("fallback_used", False)),
        )
    except Exception:
        return None


async def _cache_put(fingerprint: str, rule_module: str, result: JudgeResult) -> None:
    try:
        r = await _get_redis()
        try:
            await r.set(
                _CACHE_KEY_TMPL.format(fingerprint=fingerprint, rule=rule_module),
                json.dumps({
                    "verdict": result.verdict,
                    "confidence": result.confidence,
                    "reasoning_zh": result.reasoning_zh,
                    "fallback_used": result.fallback_used,
                }),
                ex=_CACHE_TTL,
            )
        finally:
            await r.aclose()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Trace recording
# ---------------------------------------------------------------------------

async def _record_to_trace(
    project_id: UUID | None,
    agent_id: str | None,
    text: str,
    result: JudgeResult,
    context: dict[str, Any],
) -> None:
    """Append judgment to agent_decision_trace for teacher dashboard.

    Non-fatal: failures are swallowed.
    """
    if project_id is None or agent_id is None:
        return
    try:
        from app.db.session import async_session_factory
        from app.db.models.agent_decision_trace import AgentDecisionTrace  # type: ignore[attr-defined]

        async with async_session_factory() as session:
            trace = AgentDecisionTrace(  # type: ignore[call-arg]
                project_id=project_id,
                agent_id=agent_id,
                decision_type="llm_judge",
                details={
                    "rule_module": result.rule_module,
                    "verdict": result.verdict,
                    "confidence": result.confidence,
                    "reasoning_zh": result.reasoning_zh,
                    "fallback_used": result.fallback_used,
                    "text_preview": text[:120],
                    "sub_phase": context.get("sub_phase"),
                    "zone": context.get("zone"),
                },
            )
            session.add(trace)
            await session.commit()
    except Exception:
        logger.debug("judge trace recording failed (non-fatal)", exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def judge_content(
    text: str,
    rule_module: str,
    context: dict[str, Any] | None = None,
    project_id: UUID | None = None,
    agent_id: str | None = None,
    skip_cache: bool = False,
    owning_user_id: UUID | None = None,
) -> JudgeResult:
    """單一文字 + 單一 rule 的 LLM 判斷。

    Args:
        text: 要判斷的文字
        rule_module: 對應的規則模組 id（見 _RULE_PROMPTS）
        context: 額外上下文（sub_phase / zone / recent_chat）
        project_id / agent_id: 寫入 trace 用
        skip_cache: 強制重新判斷

    Returns:
        JudgeResult。LLM 失敗時 verdict="pass", fallback_used=True。
    """
    if not text or not text.strip():
        return JudgeResult(
            verdict="pass",
            confidence=1.0,
            reasoning_zh="空文字，預設通過",
            rule_module=rule_module,
        )

    context = context or {}
    fp = _fingerprint(text)

    # Tier 1 cache
    if not skip_cache:
        cached = await _cache_get(fp, rule_module)
        if cached is not None:
            return cached

    # Tier 2 LLM — skip if no owning user (every call must be attributable).
    if owning_user_id is None:
        return JudgeResult(
            verdict="pass",
            confidence=0.0,
            reasoning_zh="無 owning_user_id，跳過 LLM 判斷，保守通過",
            rule_module=rule_module,
            fallback_used=True,
        )
    try:
        result = await _llm_judge_single(
            text, rule_module, context, owning_user_id=owning_user_id, project_id=project_id
        )
    except Exception as exc:
        logger.warning(
            "LLM judge failed for rule=%s text='%s...': %s — fallback to pass",
            rule_module, text[:40], exc,
        )
        result = JudgeResult(
            verdict="pass",
            confidence=0.0,
            reasoning_zh=f"LLM 判斷失敗（{type(exc).__name__}），保守通過",
            rule_module=rule_module,
            fallback_used=True,
        )

    # Cache + record
    await _cache_put(fp, rule_module, result)
    await _record_to_trace(project_id, agent_id, text, result, context)

    return result


async def judge_batch(
    text: str,
    rule_modules: list[str],
    context: dict[str, Any] | None = None,
    project_id: UUID | None = None,
    agent_id: str | None = None,
    owning_user_id: UUID | None = None,
) -> BatchJudgeResult:
    """批次評估：同一段文字對多個 rule 跑一個 LLM call（省 token）。"""
    if not text or not text.strip():
        return BatchJudgeResult(
            results={
                m: JudgeResult(
                    verdict="pass", confidence=1.0,
                    reasoning_zh="空文字", rule_module=m,
                )
                for m in rule_modules
            },
            total_llm_ms=0,
        )

    context = context or {}
    fp = _fingerprint(text)
    results: dict[str, JudgeResult] = {}
    cache_hits = 0
    uncached: list[str] = []
    for m in rule_modules:
        cached = await _cache_get(fp, m)
        if cached is not None:
            results[m] = cached
            cache_hits += 1
        else:
            uncached.append(m)

    if not uncached:
        return BatchJudgeResult(results=results, total_llm_ms=0, cache_hits=cache_hits)

    if owning_user_id is None:
        # No owner — skip LLM; mark all uncached as conservative pass.
        for m in uncached:
            results[m] = JudgeResult(
                verdict="pass",
                confidence=0.0,
                reasoning_zh="無 owning_user_id，跳過 LLM 判斷，保守通過",
                rule_module=m,
                fallback_used=True,
            )
        return BatchJudgeResult(results=results, total_llm_ms=0, cache_hits=cache_hits)

    started = time.time()
    try:
        llm_results = await _llm_judge_batch(
            text, uncached, context, owning_user_id=owning_user_id, project_id=project_id
        )
    except Exception as exc:
        logger.warning(
            "LLM batch judge failed: %s — all uncached fallback to pass",
            exc,
        )
        llm_results = {
            m: JudgeResult(
                verdict="pass",
                confidence=0.0,
                reasoning_zh=f"LLM 批次判斷失敗，保守通過",
                rule_module=m,
                fallback_used=True,
            )
            for m in uncached
        }
    elapsed_ms = int((time.time() - started) * 1000)

    for m, r in llm_results.items():
        results[m] = r
        await _cache_put(fp, m, r)
        await _record_to_trace(project_id, agent_id, text, r, context)

    return BatchJudgeResult(
        results=results,
        total_llm_ms=elapsed_ms,
        cache_hits=cache_hits,
    )


# ---------------------------------------------------------------------------
# LLM call internals
# ---------------------------------------------------------------------------

async def _llm_judge_single(
    text: str,
    rule_module: str,
    context: dict[str, Any],
    *,
    owning_user_id: UUID,
    project_id: UUID | None = None,
) -> JudgeResult:
    """單規則 LLM call。"""
    rule_prompt = _RULE_PROMPTS.get(rule_module, _DEFAULT_PROMPT.format(rule_module=rule_module))
    sub_phase = context.get("sub_phase", "?")
    zone = context.get("zone", "?")

    system = f"你是 DT 流程的紀律與內容監督員。{rule_prompt}"
    user = (
        f"當前 sub-phase: {sub_phase}\n"
        f"當前 zone: {zone}\n\n"
        f"待審文字：\n\"\"\"\n{text}\n\"\"\"\n\n"
        '回 JSON：{"verdict": "pass" | "violate" | "borderline", '
        '"confidence": 0.0-1.0, "reasoning": "..."}'
    )

    llm = LLMProviderFactory.get_service()
    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=200,
        caller="llm_judge_single",
        owning_user_id=owning_user_id,
        project_id=project_id,
    )
    parsed = parse_llm_json(response.content)
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM 回應非 JSON: {response.content[:120]}")

    verdict = parsed.get("verdict", "borderline")
    if verdict not in ("pass", "violate", "borderline"):
        verdict = "borderline"
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    reasoning = str(parsed.get("reasoning", ""))[:300]

    return JudgeResult(
        verdict=verdict,  # type: ignore[arg-type]
        confidence=max(0.0, min(1.0, confidence)),
        reasoning_zh=reasoning,
        rule_module=rule_module,
    )


async def _llm_judge_batch(
    text: str,
    rule_modules: list[str],
    context: dict[str, Any],
    *,
    owning_user_id: UUID,
    project_id: UUID | None = None,
) -> dict[str, JudgeResult]:
    """批次 LLM call：一次評估多個規則。"""
    rules_block = "\n\n".join(
        f"### {m}\n{_RULE_PROMPTS.get(m, _DEFAULT_PROMPT.format(rule_module=m))}"
        for m in rule_modules
    )
    sub_phase = context.get("sub_phase", "?")
    zone = context.get("zone", "?")

    system = "你是 DT 流程的紀律與內容監督員。你會逐一評估多條規則。"
    user = (
        f"當前 sub-phase: {sub_phase}\n"
        f"當前 zone: {zone}\n\n"
        f"待審文字：\n\"\"\"\n{text}\n\"\"\"\n\n"
        f"請逐一判斷以下規則：\n{rules_block}\n\n"
        f"回 JSON object，key 為 rule_module，value 為 "
        '{"verdict": "pass|violate|borderline", "confidence": 0.X, "reasoning": "..."}'
    )

    llm = LLMProviderFactory.get_service()
    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=600,
        caller="llm_judge_batch",
        owning_user_id=owning_user_id,
        project_id=project_id,
    )
    parsed = parse_llm_json(response.content)
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM 批次回應非 JSON: {response.content[:200]}")

    out: dict[str, JudgeResult] = {}
    for m in rule_modules:
        entry = parsed.get(m)
        if not isinstance(entry, dict):
            out[m] = JudgeResult(
                verdict="pass",
                confidence=0.0,
                reasoning_zh="批次回應缺漏，保守通過",
                rule_module=m,
                fallback_used=True,
            )
            continue
        verdict = entry.get("verdict", "borderline")
        if verdict not in ("pass", "violate", "borderline"):
            verdict = "borderline"
        try:
            confidence = float(entry.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out[m] = JudgeResult(
            verdict=verdict,  # type: ignore[arg-type]
            confidence=max(0.0, min(1.0, confidence)),
            reasoning_zh=str(entry.get("reasoning", ""))[:300],
            rule_module=m,
        )
    return out


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def is_violating(result: JudgeResult, min_confidence: float = 0.6) -> bool:
    """Strict violation check: only block if LLM is confident."""
    return result.verdict == "violate" and result.confidence >= min_confidence


def list_supported_modules() -> list[str]:
    return list(_RULE_PROMPTS.keys())

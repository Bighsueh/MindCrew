import asyncio
import logging
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.interview import InterviewExchange, InterviewSession
from app.interview.profiles import STAKEHOLDERS
from app.interview.provider import GenerationError, InterviewProvider

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
SETUP_ERRORS = {
    "configuration", "missing_key", "missing_model", "unsupported_provider",
    "openai_auth", "openai_model", "openai_quota", "openai_request",
}
ERROR_MESSAGES = {
    "configuration": "訪談模型目前無法使用。設定恢復後，可以重試本題。",
    "missing_key": "訪談後端尚未收到 OPENAI_API_KEY。請管理者設定後重試。",
    "missing_model": "訪談後端尚未收到 INTERVIEW_LLM_MODEL。請管理者設定後重試。",
    "unsupported_provider": "訪談供應商設定有誤。請管理者確認 INTERVIEW_LLM_PROVIDER。",
    "openai_auth": "OpenAI 驗證失敗。請管理者檢查後端 API 金鑰。",
    "openai_model": "OpenAI 拒絕存取訪談模型。請管理者檢查模型 ID 與專案權限。",
    "openai_quota": "OpenAI API 額度不足。請管理者檢查專案額度與帳單設定。",
    "openai_request": "OpenAI 拒絕訪談請求。請管理者確認模型支援 Responses API。",
    "temporary": "暫時無法取得受訪者回答。你的問題已保存。",
    "openai_timeout": "等待模型回答逾時。你的問題已保存，可以重試。",
    "openai_connection": "訪談後端無法連到 OpenAI。你的問題已保存，請管理者檢查伺服器連線。",
    "openai_rate_limit": "OpenAI 暫時限制請求頻率。你的問題已保存，請稍後重試。",
    "openai_unavailable": "OpenAI 服務暫時無法回應。你的問題已保存，請稍後重試。",
    "interview_internal": "訪談後端處理回答時發生錯誤。你的問題已保存，請管理者查看後端日誌。",
    "context_limit": "這段訪談超過模型可處理的長度。請結束本場並開啟新訪談。",
    "invalid_reply": "模型未提供完整的受訪者回答。你的問題已保存。",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def exchange_status(exchange: InterviewExchange) -> tuple[str, str | None]:
    if exchange.status == "waiting" and exchange.waiting_until <= utcnow():
        return "failed", "temporary"
    return exchange.status, exchange.error_code


def can_retry(exchange: InterviewExchange) -> bool:
    status, error = exchange_status(exchange)
    return status == "failed" and error != "context_limit" and (
        error in SETUP_ERRORS or exchange.attempt_count < MAX_ATTEMPTS
    )


def retry_wait(exchange: InterviewExchange) -> int:
    if exchange.status != "failed" or exchange.waiting_until is None or not can_retry(exchange):
        return 0
    return max(0, ceil((exchange.waiting_until - utcnow()).total_seconds()))


async def get_session(db: AsyncSession, owner_id: UUID, session_id: UUID, *, lock: bool = False) -> InterviewSession:
    query = select(InterviewSession).where(
        InterviewSession.id == session_id, InterviewSession.owner_id == owner_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    session = await db.scalar(query)
    if session is None:
        raise HTTPException(404, "找不到訪談。")
    return session


async def get_exchanges(db: AsyncSession, session: InterviewSession) -> list[InterviewExchange]:
    query = select(InterviewExchange).where(InterviewExchange.session_id == session.id).order_by(
        InterviewExchange.sequence
    ).execution_options(populate_existing=True)
    return list((await db.scalars(query)).all())


def ensure_open(session: InterviewSession) -> None:
    if session.ended_at:
        raise HTTPException(409, "這場訪談已結束。")


def skip(exchange: InterviewExchange) -> None:
    exchange.status = "skipped"
    exchange.attempt_token = exchange.waiting_until = exchange.error_code = None


async def generate_answer(
    db: AsyncSession,
    session: InterviewSession,
    exchanges: list[InterviewExchange],
    exchange: InterviewExchange,
    provider: InterviewProvider,
) -> InterviewExchange:
    # The caller owns the Session row lock. Commit the question before network I/O.
    owner_id, session_id, sequence = session.owner_id, session.id, exchange.sequence
    stakeholder = STAKEHOLDERS[session.stakeholder_id]
    messages = [
        message
        for turn in exchanges
        if turn.status == "answered"
        for message in (
            {"role": "user", "content": turn.question},
            {"role": "assistant", "content": turn.answer},
        )
    ]
    messages.append({"role": "user", "content": exchange.question})
    token = uuid4()
    exchange.attempt_token = token
    exchange.attempt_count += 1
    exchange.status = "waiting"
    exchange.error_code = None
    timeout = settings.INTERVIEW_LLM_TIMEOUT_SECONDS
    exchange.waiting_until = utcnow() + timedelta(seconds=timeout + 5)
    await db.commit()

    answer = None
    error = None
    retry_after = None
    try:
        answer = await asyncio.wait_for(provider.generate(stakeholder.instructions(), messages), timeout)
        if not answer.content.strip() or "\x00" in answer.content:
            raise GenerationError("invalid_reply")
    except GenerationError as exc:
        error = exc.code if exc.code in ERROR_MESSAGES else "temporary"
        retry_after = exc.retry_after
    except TimeoutError:
        error = "openai_timeout"
    except Exception as exc:
        # Record only the type, because SDK exception details may contain request data.
        logger.error("Interview provider exception type: %s", type(exc).__name__)
        error = "interview_internal"

    session = await get_session(db, owner_id, session_id, lock=True)
    current = (await get_exchanges(db, session))[sequence - 1]
    if session.ended_at or current.attempt_token != token or current.status != "waiting":
        await db.commit()
        return current
    if exchange_status(current)[0] != "waiting":
        error = "openai_timeout"

    current.attempt_token = current.waiting_until = None
    if error:
        current.error_code, current.status = error, "failed"
        if error in SETUP_ERRORS:
            current.attempt_count -= 1
        if error in {"openai_rate_limit", "openai_unavailable"}:
            delay = retry_after if retry_after is not None else 15 * 2 ** (min(current.attempt_count, MAX_ATTEMPTS) - 1)
            current.waiting_until = utcnow() + timedelta(seconds=delay)
        await db.commit()
        logger.info("Interview generation failed: %s", error)
        raise HTTPException(503, {"code": error, "message": ERROR_MESSAGES[error]})
    current.status = "answered"
    current.answer, current.answered_at = answer.content, utcnow()
    current.provider, current.model = provider.name, answer.model
    await db.commit()
    return current

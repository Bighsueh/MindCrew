"""DT 教練測試共用 helper（從 ``test_dt_coach.py`` 抽出以維持 < 500 行）。

僅包含：
  - HTTP helper（register / create_project / ask_coach）
  - Fake LLM 物件（_FakeLLM / _FailingLLM / patch_llm）
  - DB polling helper（wait_for_messages）

底線開頭命名 `_dt_coach_helpers.py` 是為了讓 pytest 預設不收集本檔；
真正的測試在 ``test_dt_coach.py`` 中 import 並使用。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coach import service as coach_service_module
from app.db.models.message import Message


# --------- HTTP helpers ----------------------------------------------------


async def register_user(
    client: AsyncClient, email: str, name: str = "Tester"
) -> dict:
    """註冊一位 user，回 ``{token, user_id, display_name}``。"""
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "pass", "display_name": name},
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    return {
        "token": body["access_token"],
        "user_id": UUID(body["user"]["id"]),
        "display_name": name,
    }


async def create_project(client: AsyncClient, token: str) -> UUID:
    """建立一個 project（caller 即為 creator）。"""
    resp = await client.post(
        "/api/projects",
        json={"name": "DT Coach Test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return UUID(resp.json()["id"])


async def ask_coach(
    client: AsyncClient,
    project_id: UUID,
    token: str,
    *,
    content: str,
    stage: str = "discover",
    micro_phase: str = "empathize",
) -> Response:
    """POST /dt-coach/ask 的精簡 helper。"""
    return await client.post(
        f"/api/projects/{project_id}/dt-coach/ask",
        json={"content": content, "stage": stage, "micro_phase": micro_phase},
        headers={"Authorization": f"Bearer {token}"},
    )


# --------- Fake LLM --------------------------------------------------------


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _FakeLLMResponse:
    content: str
    usage: _FakeUsage = field(default_factory=_FakeUsage)
    model: str = "fake"
    finish_reason: str = "stop"


class _FakeLLM:
    """假 LLMService：紀錄呼叫並回固定內容。"""

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> _FakeLLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return _FakeLLMResponse(content=self._content)


class _FailingLLM:
    """假 LLMService：永遠 raise，用來測 503 fallback。"""

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> _FakeLLMResponse:
        raise RuntimeError("All LLM providers failed. Last error: boom")


def patch_llm(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    """把 ``dt_coach_service`` 內部用的 LLMProviderFactory.get_service() 換成 fake。"""

    class _FakeFactory:
        @staticmethod
        def get_service() -> object:
            return fake

    monkeypatch.setattr(
        coach_service_module, "LLMProviderFactory", _FakeFactory
    )


# --------- DB polling -----------------------------------------------------


async def wait_for_messages(
    db_session: AsyncSession,
    *,
    project_id: UUID,
    chat_id: str,
    expected: int,
    timeout: float = 3.0,
) -> list[Message]:
    """輪詢等待背景任務把 Coach reply 寫進 DB。

    背景 task 用 ``asyncio.create_task`` 排程；測試函式 return 前可能尚未完成。
    用 short polling 等到看到預期筆數（含 user_message + Coach reply）才繼續。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    last_rows: list[Message] = []
    while asyncio.get_event_loop().time() < deadline:
        result = await db_session.execute(
            select(Message)
            .where(Message.project_id == project_id)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at)
        )
        last_rows = list(result.scalars().all())
        if len(last_rows) >= expected:
            return last_rows
        await asyncio.sleep(0.05)
    return last_rows

"""Phase 22：短碼產生器

教師 signature_code 與專案 invite_code 共用。
- 去除容易看錯的字母（0/O/1/I/L）
- 預設 6 碼，碰撞時由呼叫方重試（passive collision handling）
"""
from __future__ import annotations

import secrets

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_DEFAULT_LENGTH = 6


def generate_code(length: int = _DEFAULT_LENGTH) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))

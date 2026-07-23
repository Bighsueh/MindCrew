"""⚠️ ARCHIVE（Phase 42 補正 R3／P1-6，user 裁定 2026-07-07）——已下架、無進入點。

Phase 31 的 AI Suggest helper（spec/23 §3）。下架原因：前端零 caller；
5 個 prompt builder 有 3 個教現行 v2.0 模板的禁字/錯句型（`from:`、「我們如何」、
「｜佐證」、訪談筆記）＋殘留 persona 參數——「打了必 502 或教錯示範」的中間態。
原 REST 進入點 `POST /{project_id}/templates/{template_id}/suggest` 已自
projects/router.py 移除。

復活條件：依 spec 23 v2.0 §2 模板重寫**全部** builder＋拔 persona 參數，
並重新掛回 router（spec 23 v2.2 版本紀錄有註記）。在那之前不得 import 使用。
"""

from app.agents.template_suggest.suggester import (
    TemplateSuggestError,
    TemplateSuggester,
)

__all__ = ["TemplateSuggester", "TemplateSuggestError"]

# MindCrew 模擬訪談 MVP

登入後，從學生或教師的上方導覽選「模擬訪談」，也可以開啟 `/interviews`。選擇林沂或何澄後按「開始新訪談」。每場只綁定一位合成受訪者，選另一位即可建立另一場。可使用 Enter 送出、Shift+Enter 換行。結束後仍可從角色的歷史訪談回看，並複製或下載完整 UTF-8 TXT。

- **題目與情境**。可選「校園公共學習空間」，或自訂題目名稱、背景及選定角色的關係與合成經驗。情境在建立場次時固定，變更後可另開一場。
- **我的筆記**。在對話右側或手機的筆記分頁撰寫及預覽 Markdown，按「儲存筆記」即可在刷新後回看。筆記按場次保存，結束後仍可編輯，獨立於模型請求和 TXT。
- **Persona**。從「模擬訪談」切換到 Persona，建立空白草稿，填寫預設欄位或新增、改名、排序及移除自訂欄位。從右側選擇一場自己的訪談，可將原始提問或回答附到對應欄位，再保存草稿。

## 本機設定與啟動

既有開發環境可直接沿用。新環境先依 [MindCrew 本機設定](../README.md) 啟動基礎服務並建立可登入帳號。在 backend 的本機環境檔或程序環境設定以下變數：

| 設定 | 用途 |
| --- | --- |
| `INTERVIEW_LLM_PROVIDER=openai` | 預設供應商。 |
| `INTERVIEW_LLM_MODEL` | 選用你的 OpenAI 專案可存取、支援 Responses API 的文字模型。切換模型後重啟後端。 |
| `OPENAI_API_KEY` | 由後端的環境或秘密管理器注入。 |
| `INTERVIEW_LLM_MAX_OUTPUT_TOKENS=240` | 每次回答的輸出 token 上限。 |
| `INTERVIEW_LLM_TIMEOUT_SECONDS=30` | 單次回答的總等待時間，最高可設 45 秒。 |
| `INTERVIEW_MAX_QUESTIONS=12` | 每場題數上限。每題最多 600 Unicode 字元。 |

從 repo 根目錄分別執行。若也要使用既有畫布，可依原開發指南啟動 Sidecar。

```sh
docker compose -f docker-compose.dev.yml up -d postgres redis
```

```sh
cd backend
pip install -r requirements.txt
# 使用本機開發資料庫，例如 docker-compose.dev.yml 對外的 5433。
export DATABASE_URL=postgresql+asyncpg://dtai:dtai@localhost:5433/dtai
# 首次 migration 需要依原啟動文件設定 INITIAL_ADMIN_PASSWORD。
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```sh
cd frontend
npm ci
npm run dev
```

開啟 `http://localhost:5173/interviews`。使用本 repo 的 `docker-compose.yml` 部署到 Dokploy 時，在該 Compose 服務的 **Environment** 填寫 `INTERVIEW_LLM_PROVIDER=openai`、`INTERVIEW_LLM_MODEL` 與 `OPENAI_API_KEY`，保存後重新部署。Compose 會把這三個變數傳給 backend 容器。如果 Dokploy 使用自訂 Compose 檔，請沿用 repo 中 backend 的對應環境變數映射。

未配置金鑰或模型時仍可開始、瀏覽、結束和匯出，已送出的問題會保留。設定修正且後端重新部署後，回到原訪談按「重試回答」。

模型連線失敗時，請從後端容器檢查 DNS 和到 `api.openai.com:443` 的 HTTPS 連線。若畫面顯示等待回答逾時，可在 Dokploy 的 **Environment** 將 `INTERVIEW_LLM_TIMEOUT_SECONDS` 調至 `45`，重新部署後重試。若後端日誌出現 `Interview generation failed:`，其後的代碼可用於診斷。

## 紀錄與供應商

PostgreSQL 的 `interview_sessions` 儲存使用者與場次，`interview_exchanges` 依序保留原始問題、回答、時間及回答所用的 provider/model。每個已送達的問題會先保存，再等待模型。若逾時，可以重試原題或略過。停用模型不影響已保存的紀錄。TXT 含合成資料標示、場次、受訪者和時間，未回答的問題會保留並標記。

每次生成只送出當前受訪者設定、同場已完成的問答及本題。Responses 請求使用 `store: false`，對話上下文由 MindCrew 從 PostgreSQL 重建。模型用於生成合成受訪者的回答，實際角色一致性仍需以選定帳號與模型做多輪驗收。[OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)

若要改接 Ollama 或其他服務，在 [provider.py](../backend/app/interview/provider.py) 新增實作 `InterviewProvider` 的 adapter，註冊於 `get_interview_provider()`，再以 `INTERVIEW_LLM_PROVIDER` 與 `INTERVIEW_LLM_MODEL` 選用。新 adapter 應保留 system 指示與 user/assistant 的訊息邊界，回傳文字與模型，並映射暫時錯誤及無效回覆。訪談 UI、資料表及既有 Crew 的 LLM 設定可以沿用。

## 測試

```sh
cd backend
pytest app/tests/test_interview.py app/tests/test_interview_provider.py
```

API 整合測試沿用 repo 的 `dtai_test` 測試資料庫 fixture，會建立與清理測試表。務必使用專用的空測試實例。Provider 測試用 Mock HTTP transport 驗證 SDK 的 request 與錯誤回應。

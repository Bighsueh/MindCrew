<div align="center">

# MindCrew

**一組 AI 隊友，在即時共用白板上帶你完成一場有引導的設計思考工作坊。**

[English](README.md) | 繁體中文

</div>

> 本頁為精簡版。技術細節、架構圖與開發說明請見 [English README](README.md)。

## 為什麼做這個

設計思考最適合 4–6 人一組、再加一位引導者控流程和時間。但學生常常一個人做，或組員不足、沒人會帶，結果容易跳過研究、直接想解法，問題定義也很淺。

直接開聊天機器人解決不了：只有一個聲音、會直接給答案而不是引導思考、沒有共用的產出物，也沒有人把關流程和時間。

MindCrew 補上缺少的團隊：學生和 **1 位 AI 組長**（引導、點名、控時）＋ **1–4 位 AI 組員**（各自帶不同利害關係人人格）在即時白板上一起走完設計思考的第一顆鑽石（**發現 → 定義**），最後產出「我們可以怎麼…」設計題目。

## 主要功能

- **有引導的第一鑽石流程**：13 個步驟（暖場 1、發現 5、定義 7），可選 40 / 60 / 90 分鐘。
- **人格化 AI 組員**：依專案題目用兩階段 LLM 流程生成組員人格。
- **三種發言模式**：點名、輪流、搶答（可舉手），進行中可切換。
- **共用白板＋群組聊天**：AI 和真人在同一塊白板上貼、移動、分群便條。
- **離席自動暫停**：真人斷線超過 30 秒（或單人房被點名未回應）時，整個房間連同計時器凍結，回來後自動恢復。
- **管理後台**：LLM 供應商管理（API key 加密儲存）、健康狀態、日誌與用量統計。

## 技術亮點

| 問題 | 做法 |
|---|---|
| 多個 AI 同房會搶話、洗版 | 每個 agent 獨立的決策迴圈，加上發言模式、節流閘門、行動協調佇列、回合鎖與組長訊息去重 |
| 真人和 AI 同時改同一塊白板 | Yjs CRDT 文件由 Node sidecar 託管；後端不直接碰 tldraw，AI 編輯一律走 HTTP Canvas API |
| LLM 不會排版 | AI 只指定語意位置（分區／群組），座標由後端排版引擎計算，加上放置鎖與每回合自動重排 |
| 不能讓 LLM 自己決定階段完成 | 明確的狀態機＋產出閘門＋規則評分為主、LLM 評估為輔 |
| 自架小模型不穩定 | Provider 抽象層與分級路由、健康監控、容錯解析、OpenCC 簡轉繁 |

詳細說明與對應程式碼連結見 [English README › Engineering challenges](README.md#engineering-challenges)。

## 快速啟動

```bash
git clone https://github.com/Bighsueh/MindCrew.git
cd MindCrew
cp .env.example .env   # 至少填入 JWT_SECRET_KEY、LLM_PROVIDER_KEY_MASTER、INITIAL_ADMIN_PASSWORD
docker compose up --build -d
```

開啟 http://localhost:3000，以 `admin` 登入後到 **Admin → Providers** 設定 OpenAI 相容的 LLM 端點。完整步驟見 [English README › Getting started](README.md#getting-started)。

## 授權

以 [PolyForm Noncommercial License 1.0.0](LICENSE) 授權（source-available）：可在非商業用途下使用、修改與分享；商業使用需另行取得授權。

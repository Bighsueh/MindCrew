// 12 個 micro phase 的前端文案
// label 對齊 backend `backend/app/stages/micro_phases.py` 的 name_zh，
// description 為「此微階段要做什麼」的一句話摘要。

import type { DTStage, MicroPhaseId } from '../../types/models'

export interface MicroPhaseMeta {
  id: MicroPhaseId
  label: string
  description: string
}

export interface MacroStageMeta {
  stage: Exclude<DTStage, 'completed'>
  label: string
  /** 設計思考雙鑽石中的位置屬性 */
  shape: '發散' | '收斂' | '純發散' | '收斂+產出'
  /** 一行 macro 階段重點 */
  summary: string
  micro: [MicroPhaseMeta, MicroPhaseMeta, MicroPhaseMeta]
}

// 文案原則：寫給「沒做過 Design Thinking」的使用者看，避免 HMW / POV / Debrief
// / Empathy Map / Journey Map / category-shift / low-fidelity / Loop 等專有名詞，
// 一律用日常中文說明做什麼、為什麼這樣做。

export const MACRO_STAGES: MacroStageMeta[] = [
  {
    stage: 'discover',
    label: 'Discover 了解使用者',
    shape: '發散',
    summary: '先弄清楚「使用者真正在意什麼」——多聽、多看、不急著想答案。',
    micro: [
      {
        id: '1.1',
        label: '暖身與選對象',
        description: '大家先聊聊自己對這個主題的經驗，然後列出「會被影響的人」有哪些，挑出最值得了解的對象。',
      },
      {
        id: '1.2',
        label: '收集多元觀點',
        description: '分頭去訪談、觀察、查資料，把不同角色的故事和想法都收集回來。',
      },
      {
        id: '1.3',
        label: '整理使用者畫像',
        description: '把訪談聽到的內容整理成「使用者是誰、他想什麼、做什麼」的清楚畫面；先寫下原話，不要急著下結論。',
      },
    ],
  },
  {
    stage: 'define',
    label: 'Define 找出問題',
    shape: '收斂',
    summary: '從一堆資訊裡挑出最關鍵的痛點，問對問題比急著想答案更重要。',
    micro: [
      {
        id: '2.1',
        label: '畫使用情境',
        description: '把使用者完成這件事的流程拆開，看看哪一步最卡、最讓人不爽。',
      },
      {
        id: '2.2',
        label: '挑出關鍵痛點',
        description: '從訪談裡找出 3 個以上「沒被滿足的需求」或「明顯的矛盾」，用一句話寫清楚。',
      },
      {
        id: '2.3',
        label: '決定要解哪個問題',
        description: '先講好「用什麼標準選」，投票挑出 1–3 個最值得解的問題，改寫成「我們可以怎麼…？」這種好回答的問句。',
      },
    ],
  },
  {
    stage: 'develop',
    label: 'Develop 想各種解法',
    shape: '純發散',
    summary: '針對選定的問題盡量丟點子，這一階段「點子多」比「點子好」重要。',
    micro: [
      {
        id: '3.1',
        label: '訂規則 + 各自寫點子',
        description: '先講好遊戲規則：先別管做不做得到、想到什麼都寫下來。每個人安靜地把點子寫在便條紙上。',
      },
      {
        id: '3.2',
        label: '把點子分類組合',
        description: '一起看所有便條紙，把性質相近的歸成一群、把兩個點子合在一起、相互激發新想法。',
      },
      {
        id: '3.3',
        label: '挑出要繼續做的方案',
        description: '看看是不是還缺哪一類的方案，補上幾個之後，選出最有潛力的 1–2 個帶到下一階段。',
      },
    ],
  },
  {
    stage: 'deliver',
    label: 'Deliver 做出來測一下',
    shape: '收斂+產出',
    summary: '把想法做成最簡單的版本給人試用，看真的有解決問題嗎；學到的回頭再改。',
    micro: [
      {
        id: '4.1',
        label: '快速做出簡單原型',
        description: '先講清楚「我假設這樣做使用者會喜歡」，然後拆成小任務，用紙、便條、簡單畫圖做出能讓人試用的版本（不用做完美的成品）。',
      },
      {
        id: '4.2',
        label: '規劃怎麼測試',
        description: '想清楚要找誰來試、怎麼算成功怎麼算失敗、要觀察什麼。',
      },
      {
        id: '4.3',
        label: '試用後回顧',
        description: '跑完試用後問三個問題：哪些想法被證實 / 哪些要修 / 還有哪裡可以更好。決定就此收工或再迭代一輪。',
      },
    ],
  },
]

/** 依 stage 查 macro meta */
export const MACRO_BY_STAGE: Record<
  Exclude<DTStage, 'completed'>,
  MacroStageMeta
> = MACRO_STAGES.reduce(
  (acc, m) => {
    acc[m.stage] = m
    return acc
  },
  {} as Record<Exclude<DTStage, 'completed'>, MacroStageMeta>,
)

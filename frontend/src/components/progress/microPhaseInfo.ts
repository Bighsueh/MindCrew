// Phase 42 C1 (spec/22 v2.0 §2.3a): 新 6 桶（0.0／1.1／1.2／2.1／2.2／2.3）。
// label 對齊 backend `backend/app/stages/micro_phases.py` 的 name_zh，
// description 為「此微階段要做什麼」的一句話摘要（assumption-based：全程在系統內
// 用討論＋便條進行，無線下調查、無投票）。

import type { DTStage, MicroPhaseId } from '../../types/models'

export interface MicroPhaseMeta {
  id: MicroPhaseId
  label: string
  description: string
}

export interface MacroStageMeta {
  stage: Exclude<DTStage, 'completed'>
  label: string
  /** 設計思考流程中的位置屬性 */
  shape: '暖身' | '發散' | '收斂' | '純發散' | '收斂+產出'
  /** 一行 macro 階段重點 */
  summary: string
  /** 該 macro 階段的微階段（暖場 1 個；發現 2 個；定義 3 個）。 */
  micro: MicroPhaseMeta[]
}

// 文案原則：寫給「沒做過 Design Thinking」的使用者看，避免 HMW / POV / Debrief
// / Empathy Map / Journey Map / category-shift / low-fidelity / Loop 等專有名詞，
// 一律用日常中文說明做什麼、為什麼這樣做。

export const MACRO_STAGES: MacroStageMeta[] = [
  {
    stage: 'warmup',
    label: '🔥暖場 破冰熱身',
    shape: '暖身',
    summary: '正式開始前先暖身——玩個快遊戲，把腦袋打開、跟隊友熟一下。',
    micro: [
      {
        id: '0.0',
        label: '破冰暖身',
        description: '玩一場「這東西還能拿來幹嘛？」的快遊戲——越多越意想不到越好，沒有標準答案。',
      },
    ],
  },
  {
    stage: 'discover',
    label: '🔍發現（同理） 了解使用者',
    shape: '發散',
    summary: '把問題盡量打開、先不做決定——從自己的經驗出發，想像會被影響的人在哪裡卡住。',
    micro: [
      {
        id: '1.1',
        label: '聊經驗、列對象',
        description: '先聊聊自己真實遇過的經驗，再列出「這件事會影響到誰」——把相似的歸成幾群、排好先挖誰後挖誰（不刪人）。',
      },
      {
        id: '1.2',
        label: '發想痛點與情境',
        description: '照排好的順序，想像每群人在什麼情況下會卡住、麻煩、受不了；聊出具體的情境再貼成便條、掛在那一群底下。',
      },
    ],
  },
  {
    stage: 'define',
    label: '📌定義（聚焦） 找出問題',
    shape: '收斂',
    summary: '反過來慢慢收：把痛點收成一句清楚的設計題目，問對問題比急著想答案更重要。',
    micro: [
      {
        id: '2.1',
        label: '痛點歸類',
        description: '把痛點從「按人掛」改成「按同一件事放」——不同人但卡在同一件事的，拖到一起，幫每群取個主題名稱。',
      },
      {
        id: '2.2',
        label: '寫問題定義、往下挖',
        description: '把痛點寫成「某使用者 需要 某需求，因為 某洞察」的完整句子，多問幾次為什麼、看看市面上已經有什麼。',
      },
      {
        id: '2.3',
        label: '挑問題、改寫設計題目',
        description: '先講好用什麼準則挑，對著準則討論、把最值得做的一到三句搬進選定區，最後改寫成「我們可以怎麼…？」的設計題目。',
      },
    ],
  },
  // 第一鑽石終局後，project.current_stage 轉為 'completed'，由 Phase 34
  // closing ritual 主持結業匯報。
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

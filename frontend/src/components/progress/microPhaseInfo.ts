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

export const MACRO_STAGES: MacroStageMeta[] = [
  {
    stage: 'discover',
    label: 'Discover 發現',
    shape: '發散',
    summary: '深入了解使用者的真實需求與痛點。',
    micro: [
      {
        id: '1.1',
        label: '暖場與經驗分享',
        description: '團隊先各自分享對該議題的使用經驗，建立共同認知；然後獨立列出利害關係人並收斂。',
      },
      {
        id: '1.2',
        label: '視角擴展',
        description: '依利害關係人分工，透過訪談、觀察、二手資料搜集多元觀點。',
      },
      {
        id: '1.3',
        label: '同理心收斂',
        description: '把訪談資料用 Empathy Map / Persona / Journey Map 結構化，先保留原音、延後詮釋。',
      },
    ],
  },
  {
    stage: 'define',
    label: 'Define 定義',
    shape: '收斂',
    summary: '從大量資訊中產生候選問題陳述，收斂出核心 HMW。',
    micro: [
      {
        id: '2.1',
        label: '使用者旅程追蹤',
        description: '整理使用者完成任務的流程，找出痛點與機會點。',
      },
      {
        id: '2.2',
        label: '洞察萃取與矛盾發掘',
        description: '用 POV 句型寫出 ≥3 個候選問題陳述；INSIGHT 不能是 NEED 的同義反覆。',
      },
      {
        id: '2.3',
        label: 'HMW 問題陳述',
        description: '建立收斂準則 → 投票選出 1–3 個高優先級問題 → 改寫為 How Might We 開放式挑戰。',
      },
    ],
  },
  {
    stage: 'develop',
    label: 'Develop 發展',
    shape: '純發散',
    summary: '天馬行空提出解法，禁止討論可行性。',
    micro: [
      {
        id: '3.1',
        label: '規則建立與大量發散',
        description: '建立發散規則（不批判、外部化），每人獨立寫下點子。',
      },
      {
        id: '3.2',
        label: '概念分群與合併',
        description: '揭示所有點子、分群、結合，激發新想法。',
      },
      {
        id: '3.3',
        label: '評估收斂與方案選定',
        description: '依組長判斷，用 category-shift 換機制再發散，確保多樣性後選定方向。',
      },
    ],
  },
  {
    stage: 'deliver',
    label: 'Deliver 交付',
    shape: '收斂+產出',
    summary: '收斂方案、製作雛形、內部 Debrief，決定 Close 或 Loop。',
    micro: [
      {
        id: '4.1',
        label: '原型規劃與快速製作',
        description: '口頭闡明假設 → 拆 Task Ticket → 強制 low-fidelity 雛形（禁寫 production code）。',
      },
      {
        id: '4.2',
        label: '測試設計',
        description: '設計能驗證假設的測試方式，包含 success / fail 條件與保真度上限。',
      },
      {
        id: '4.3',
        label: '模擬測試與學習迭代',
        description: '跑完雛形做三題 Debrief（信念更新／回應 HMW／回溯反省），決定 Close 或 Loop。',
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

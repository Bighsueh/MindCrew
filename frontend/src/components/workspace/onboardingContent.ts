// 新手導引 Modal 文案常數
// 集中於此便於日後 i18n / OpenCC 抽換

import type { DTStage } from '../../types/models'

export const ONBOARDING_LEAD_IN = '接下來幾分鐘，我們會帶你看懂這裡發生什麼事。'

export const DT_DEFINITION =
  '設計思考（Design Thinking）是一種以使用者為中心的問題解決流程：先「找對問題」，再「做對解法」。它強調從觀察與訪談中發掘真實需求，並用快速雛形驗證假設。'

export const DOUBLE_DIAMOND_NARRATIVE = [
  '雙鑽石（Double Diamond）由兩段「先發散、再收斂」的循環組成：',
  '第一鑽石聚焦「找對問題」——Discover 廣泛探索，Define 收斂出值得解的問題。',
  '第二鑽石聚焦「做對解法」——Develop 放膽發想，Deliver 收斂、雛形、驗證。',
  '兩個收斂點（Define 與 Deliver）都必須有明確判準，不能只憑感覺投票。',
]

export interface PhaseDescription {
  id: 'p0' | 'p1' | 'p2' | 'p3' | 'p4'
  label: string
  shape: '前置' | '發散' | '收斂' | '純發散' | '收斂+產出'
  body: string
}

export const PHASE_DESCRIPTIONS: PhaseDescription[] = [
  {
    id: 'p0',
    label: 'Phase 0 · 前置作業',
    shape: '前置',
    body: '確定主題、選出組長（Supervisor），為雙鑽石做準備。',
  },
  {
    id: 'p1',
    label: 'Phase 1 · Discover 發現',
    shape: '發散',
    body: '從定義利害關係人起手，透過訪談、觀察、二手資料蒐集第一手洞察，先保留原音、延後詮釋。',
  },
  {
    id: 'p2',
    label: 'Phase 2 · Define 定義',
    shape: '收斂',
    body: '用 POV 句型產出 ≥3 個候選問題陳述，建立收斂準則後投票，再改寫為 HMW。',
  },
  {
    id: 'p3',
    label: 'Phase 3 · Develop 發展',
    shape: '純發散',
    body: '天馬行空、不討論可行性。組長用 category-shift 推大家跳出第一波思路。',
  },
  {
    id: 'p4',
    label: 'Phase 4 · Deliver 交付',
    shape: '收斂+產出',
    body: '口頭闡明假設 → 拆 Task Ticket → 低保真原型 → 內部 Debrief → 決定 Close / Loop。',
  },
]

export const COLLAB_NOTE = '合作面向由「組長（Supervisor）」貫穿全程管控，包括節奏控制與規則偵測。'

export const STAGE_NEXT_HINT: Record<DTStage, string> = {
  discover:
    '請從「定義利害關係人」開始：每人先各自列出，再揭示、歸類，最後附上「為什麼選這群」的理由。',
  define:
    '請用 POV 句型「[USER] needs [NEED] because [INSIGHT]」，至少寫出 3 個候選問題陳述。',
  develop:
    '對選定的 HMW，每個人先各自寫下點子（外部化、不口頭講過就消失），禁止討論可行性。',
  deliver:
    '先口頭明確說出要驗證什麼假設、成功/失敗條件，再做 low-fidelity 雛形，禁寫 production code。',
  completed: '活動已完成。可從 Spec 文檔回顧設計決策與假設驗證的 traceback。',
}

export const STAGE_HEADING_LABEL: Record<DTStage, string> = {
  discover: 'Phase 1 · Discover',
  define: 'Phase 2 · Define',
  develop: 'Phase 3 · Develop',
  deliver: 'Phase 4 · Deliver',
  completed: '已完成',
}

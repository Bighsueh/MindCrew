import type { AIContribution, TurnPolicy } from '../types/models'
import type { TimerMode } from '../components/timer/TimerConfigForm'

/**
 * Phase 43（spec/29）：實驗深連結自動代填。
 * 解析 /projects?study=1&name&desc&turn&ai&crew&timer 的受控欄位組。
 * allowlist 驗證採 fail-loud：任一必填參數缺漏或非法 → 整組回 null（正常模式），
 * 寧可在 pilot 期讓研究者看到未代填的表單，也不默默用錯條件蒐集資料。
 */
export interface StudyConfig {
  readonly name: string
  readonly description: string
  readonly turnPolicy: TurnPolicy
  readonly aiContribution: AIContribution
  readonly aiCrewCount: number
  readonly timerMode: TimerMode
}

const TURN_POLICIES: readonly TurnPolicy[] = ['cued', 'round_robin', 'open_floor']
const AI_CONTRIBUTIONS: readonly AIContribution[] = ['low', 'medium', 'high']

/** timer 參數（分鐘）→ 既有 preset（spec/16），不新增 preset */
const TIMER_PRESETS: Record<string, TimerMode> = {
  '40': 'preset_40min',
  '60': 'preset_60min',
  '90': 'preset_90min',
}

export function parseStudyParams(params: URLSearchParams): StudyConfig | null {
  if (params.get('study') !== '1') return null

  const name = (params.get('name') ?? '').trim()
  const turn = params.get('turn') as TurnPolicy | null
  const ai = params.get('ai') as AIContribution | null
  // 嚴格比對原字串(與 turn/ai/timer 同樣 fail-loud)——不靠 Number() 的寬鬆轉換,
  // 避免 '3 '/'0x3'/'3e0' 等怪字串被默默接受。
  const crewRaw = params.get('crew') ?? ''
  const timerMode = TIMER_PRESETS[params.get('timer') ?? '']

  if (!name) return null
  if (!turn || !TURN_POLICIES.includes(turn)) return null
  if (!ai || !AI_CONTRIBUTIONS.includes(ai)) return null
  if (!/^[1-4]$/.test(crewRaw)) return null
  if (!timerMode) return null

  return {
    name,
    description: (params.get('desc') ?? '').trim(),
    turnPolicy: turn,
    aiContribution: ai,
    aiCrewCount: Number(crewRaw),
    timerMode,
  }
}

// ── sessionStorage 鏡像（spec/29 §3.1）─────────────────────────────────────
// URL 參數即拆即清後，靠這份鏡像讓「重整 / 中途離開再回來」延續 study 模式；
// onCreated 時清除退出。慣例同 ProjectsPage 的 mc_redirect_notice。

const STORAGE_KEY = 'mc_study_config'

export function saveStudySession(config: StudyConfig): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch {
    // sessionStorage 不可用（隱私模式等）：僅失去重整續走，當次流程不受影響
  }
}

export function readStudySession(): StudyConfig | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StudyConfig>
    // 鏡像同樣過 allowlist：sessionStorage 可被手動竄改，不可信任
    const params = new URLSearchParams({
      study: '1',
      name: parsed.name ?? '',
      desc: parsed.description ?? '',
      turn: parsed.turnPolicy ?? '',
      ai: parsed.aiContribution ?? '',
      crew: String(parsed.aiCrewCount ?? ''),
      timer: timerModeToMinutes(parsed.timerMode),
    })
    return parseStudyParams(params)
  } catch {
    return null
  }
}

export function clearStudySession(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // 清除失敗無礙：study state 已由呼叫端清空
  }
}

function timerModeToMinutes(mode: TimerMode | undefined): string {
  const entry = Object.entries(TIMER_PRESETS).find(([, m]) => m === mode)
  return entry?.[0] ?? ''
}

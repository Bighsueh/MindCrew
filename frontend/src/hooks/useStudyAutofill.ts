import { useEffect, useMemo, useRef, useState } from 'react'
import type { AIContribution, TurnPolicy } from '../types/models'
import type { TimerMode } from '../components/timer/TimerConfigForm'
import type { StudyConfig } from '../lib/studyParams'
import { useReducedMotion } from './useReducedMotion'

/**
 * Phase 43（spec/29 §3.2–§3.4）：幽靈代填動畫。
 * 在 study 模式下把六個受控欄位當著受試者的面逐一填好（打字機＋逐格選中），
 * 完成後鎖定。動畫是「讓實驗條件可見」的溝通手段；條件完整性靠最終值＋鎖定保證。
 */

export type StudyFieldKey =
  | 'name'
  | 'description'
  | 'turnPolicy'
  | 'aiContribution'
  | 'aiCrewCount'
  | 'timerMode'

export type AutofillPhase = 'idle' | 'typing_name' | 'typing_desc' | 'selecting' | 'done'

/** BriefStep 消費的展示狀態（單一內聚物件，spec/29 §4.1） */
export interface StudyAutofillUI {
  readonly lockedFields: ReadonlySet<StudyFieldKey>
  readonly highlightTarget: StudyFieldKey | null
  readonly isAnimating: boolean
}

interface AutofillSetters {
  setName: (v: string) => void
  setDescription: (v: string) => void
  setTurnPolicy: (v: TurnPolicy) => void
  setAiContribution: (v: AIContribution) => void
  setAiCrewCount: (v: number) => void
  setTimerMode: (v: TimerMode) => void
}

interface Options {
  /** null = 非 study 模式，hook 完全 no-op */
  config: StudyConfig | null
  /** isOpen && step === 'brief'：精靈開在第一步時才跑 */
  active: boolean
  setters: AutofillSetters
}

interface Result {
  isStudy: boolean
  phase: AutofillPhase
  isAnimating: boolean
  narration: string | null
  ui: StudyAutofillUI | undefined
}

const ALL_FIELDS: ReadonlySet<StudyFieldKey> = new Set([
  'name',
  'description',
  'turnPolicy',
  'aiContribution',
  'aiCrewCount',
  'timerMode',
])
const NO_FIELDS: ReadonlySet<StudyFieldKey> = new Set()

const NAME_MS_PER_CHAR = 50
const DESC_MS_PER_CHAR = 30
const SELECT_DELAY_MIN_MS = 400
const SELECT_DELAY_MAX_MS = 600
const FINALE_DELAY_MS = 500

const DONE_NARRATION = '✓ 實驗條件已就緒，請按「下一步」繼續'

export function useStudyAutofill({ config, active, setters }: Options): Result {
  const [phase, setPhase] = useState<AutofillPhase>('idle')
  const [narration, setNarration] = useState<string | null>(null)
  const [highlightTarget, setHighlightTarget] = useState<StudyFieldKey | null>(null)
  const reducedMotion = useReducedMotion()

  // dialog 關閉不 unmount（ProjectsPage 無條件 render），ref 跨關閉/重開存活。
  // 只在動畫「成功跑完」的尾端標記（commit point）——StrictMode 第一輪 mount 會被
  // cleanup abort、到不了這裡，因此不會誤標已播過讓第二輪憑空跳到完成態。
  const playedRef = useRef(false)
  const settersRef = useRef(setters)
  settersRef.current = setters

  useEffect(() => {
    if (!config || !active) return

    const s = settersRef.current
    const applyAll = () => {
      s.setName(config.name)
      s.setDescription(config.description)
      s.setTurnPolicy(config.turnPolicy)
      s.setAiContribution(config.aiContribution)
      s.setAiCrewCount(config.aiCrewCount)
      s.setTimerMode(config.timerMode)
      setHighlightTarget(null)
      setNarration(DONE_NARRATION)
      setPhase('done')
    }

    // 播畢重開不重播（spec/29 §3.4）；reduced-motion 直填（無障礙）
    if (playedRef.current || reducedMotion) {
      playedRef.current = true
      applyAll()
      return
    }

    const ctrl = new AbortController()
    const { signal } = ctrl

    const run = async () => {
      setNarration('正在為你佈置這次的實驗條件…')
      await sleep(600, signal)

      setPhase('typing_name')
      setNarration('正在填入專案名稱…')
      setHighlightTarget('name')
      await typewriter(config.name, s.setName, NAME_MS_PER_CHAR, signal)

      if (config.description) {
        setPhase('typing_desc')
        setNarration('正在填入專案描述…')
        setHighlightTarget('description')
        await typewriter(config.description, s.setDescription, DESC_MS_PER_CHAR, signal)
      }

      setPhase('selecting')
      const steps: ReadonlyArray<[StudyFieldKey, string, () => void]> = [
        ['turnPolicy', '正在設定對話模式…', () => s.setTurnPolicy(config.turnPolicy)],
        ['aiContribution', '正在設定 AI 貢獻度…', () => s.setAiContribution(config.aiContribution)],
        ['aiCrewCount', '正在設定 AI 組員人數…', () => s.setAiCrewCount(config.aiCrewCount)],
        ['timerMode', '正在設定時間配置…', () => s.setTimerMode(config.timerMode)],
      ]
      for (const [field, message, apply] of steps) {
        await sleep(selectDelay(field), signal)
        setNarration(message)
        setHighlightTarget(field)
        apply()
      }

      await sleep(FINALE_DELAY_MS, signal)
      setHighlightTarget(null)
      setNarration(DONE_NARRATION)
      setPhase('done')
      playedRef.current = true
    }

    run().catch((err: unknown) => {
      if ((err as { name?: string }).name !== 'AbortError') throw err
    })

    return () => {
      ctrl.abort()
      // 中斷時清掉動畫 UI 狀態；欄位值由 dialog 的 reset() 負責
      setPhase('idle')
      setNarration(null)
      setHighlightTarget(null)
    }
    // setters 經 ref 取用，不進 deps
  }, [config, active, reducedMotion])

  const isStudy = config !== null
  // study 模式下只要尚未完成就視為「動畫中」——涵蓋開場 sleep 的 idle 前奏，
  // 讓六個受控欄位從第一幀就鎖住（spec/29 §3.3「動畫進行中欄位同樣不可操作」），
  // 不留 readOnly/disabled 尚未生效的可編輯空窗。programmatic 打字機 setState 不受影響。
  const isAnimating = isStudy && phase !== 'done'
  // 已播畢過(playedRef)即恆鎖：避免「下一步→上一步」回到 brief 時 phase 暫為 idle
  // 造成鎖定徽章閃掉一幀。
  const lockedFields = phase === 'done' || playedRef.current ? ALL_FIELDS : NO_FIELDS

  const ui = useMemo<StudyAutofillUI | undefined>(
    () => (isStudy ? { lockedFields, highlightTarget, isAnimating } : undefined),
    [isStudy, lockedFields, highlightTarget, isAnimating],
  )

  return { isStudy, phase, isAnimating, narration: isStudy ? narration : null, ui }
}

// ── helpers ──────────────────────────────────────────────────────────────────

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(() => resolve(), ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

/**
 * 逐字打入。每 tick 寫「絕對 prefix」（slice(0, i)）而非累加——
 * 冪等（StrictMode abort 後重播不疊字）、code point 切分不切壞 surrogate pair。
 */
async function typewriter(
  text: string,
  set: (v: string) => void,
  msPerChar: number,
  signal: AbortSignal,
): Promise<void> {
  const chars = Array.from(text)
  for (let i = 1; i <= chars.length; i++) {
    await sleep(msPerChar, signal)
    set(chars.slice(0, i).join(''))
  }
}

/** toggle 間隔 400–600ms；以欄位名做確定性散佈（避免 Math.random 在測試中不穩） */
function selectDelay(field: StudyFieldKey): number {
  let hash = 0
  for (const ch of field) hash = (hash * 31 + ch.charCodeAt(0)) % 997
  return SELECT_DELAY_MIN_MS + (hash % (SELECT_DELAY_MAX_MS - SELECT_DELAY_MIN_MS))
}

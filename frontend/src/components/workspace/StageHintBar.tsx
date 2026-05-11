import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Compass,
  Lightbulb,
  Rocket,
  Sparkles,
  Target,
  type LucideIcon,
} from 'lucide-react'
import type { DTStage } from '../../types/models'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useFirstRunFlag } from '../../hooks/useFirstRunFlag'

interface StageHintBarProps {
  stage: DTStage
  projectId: string
  goalText?: string
  onTaskClick?: () => void
  onStartWithAiClick?: () => void
  defaultCollapsed?: boolean
  /** 在白板第一次出現便利貼時由父層遞增此計數 → 觸發 [起頭] chip 一次性 flash 動畫。 */
  startChipFlashKey?: number
}

interface StageMeta {
  label: string
  icon: LucideIcon
  defaultGoal: string
}

const STAGE_META: Record<DTStage, StageMeta> = {
  discover: {
    label: 'Discover',
    icon: Compass,
    defaultGoal: '透過訪談找出真實痛點，產出洞察便利貼。',
  },
  define: {
    label: 'Define',
    icon: Target,
    defaultGoal: '把痛點收斂成一句 HMW（How might we）問題。',
  },
  develop: {
    label: 'Develop',
    icon: Lightbulb,
    defaultGoal: '為 HMW 發散多個解法構想，再投票收斂。',
  },
  deliver: {
    label: 'Deliver',
    icon: Rocket,
    defaultGoal: '將最佳構想做成可測試的原型與測試計畫。',
  },
  completed: {
    label: 'Completed',
    icon: Rocket,
    defaultGoal: '專案已完成，回顧成果並整理紀錄。',
  },
}

const STORAGE_PREFIX = 'mindcrew.stageHintBar.'
const SWEEP_DURATION_MS = 1100

function readStoredCollapsed(projectId: string): boolean | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${projectId}.collapsed`)
    if (raw === '1') return true
    if (raw === '0') return false
    return null
  } catch {
    return null
  }
}

function writeStoredCollapsed(projectId: string, collapsed: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${projectId}.collapsed`, collapsed ? '1' : '0')
  } catch {
    /* ignore */
  }
}

function isTabletPortrait(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(orientation: portrait) and (max-width: 1023px)').matches
}

export function StageHintBar({
  stage,
  projectId,
  goalText,
  onTaskClick,
  onStartWithAiClick,
  defaultCollapsed,
  startChipFlashKey = 0,
}: StageHintBarProps) {
  const reducedMotion = useReducedMotion()
  const [isFirstRun, dismissFirstRun] = useFirstRunFlag(`stage-bar-${projectId}`)
  const [flashing, setFlashing] = useState<boolean>(false)
  const lastFlashKeyRef = useRef<number>(0)

  useEffect(() => {
    if (startChipFlashKey === 0 || startChipFlashKey === lastFlashKeyRef.current) return
    lastFlashKeyRef.current = startChipFlashKey
    if (reducedMotion) return
    setFlashing(true)
    const t = window.setTimeout(() => setFlashing(false), 1500)
    return () => window.clearTimeout(t)
  }, [startChipFlashKey, reducedMotion])

  const meta = STAGE_META[stage] ?? STAGE_META.discover
  const Icon = meta.icon
  const goal = goalText ?? meta.defaultGoal

  // Initial collapsed state (immutable derivation, computed once per mount).
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (isFirstRun) return false
    const stored = readStoredCollapsed(projectId)
    if (stored !== null) return stored
    if (typeof defaultCollapsed === 'boolean') return defaultCollapsed
    return isTabletPortrait()
  })

  // Sweep animation key — remounts overlay on each stage change.
  const [sweepKey, setSweepKey] = useState<number>(() => (isFirstRun ? 1 : 0))
  const prevStageRef = useRef<DTStage>(stage)
  const firstRunHandledRef = useRef<boolean>(false)

  // First-run side effect: trigger sweep + dismiss flag once.
  useEffect(() => {
    if (isFirstRun && !firstRunHandledRef.current) {
      firstRunHandledRef.current = true
      if (!reducedMotion) setSweepKey((k) => k + 1)
      dismissFirstRun()
    }
  }, [isFirstRun, reducedMotion, dismissFirstRun])

  // Stage change side effect: re-expand once + sweep.
  useEffect(() => {
    if (prevStageRef.current === stage) return
    prevStageRef.current = stage
    setCollapsed(false)
    writeStoredCollapsed(projectId, false)
    if (!reducedMotion) setSweepKey((k) => k + 1)
  }, [stage, projectId, reducedMotion])

  // Auto-clear sweep overlay after animation completes.
  const [sweepActive, setSweepActive] = useState<boolean>(false)
  useEffect(() => {
    if (sweepKey === 0 || reducedMotion) {
      setSweepActive(false)
      return
    }
    setSweepActive(true)
    const t = window.setTimeout(() => setSweepActive(false), SWEEP_DURATION_MS + 50)
    return () => window.clearTimeout(t)
  }, [sweepKey, reducedMotion])

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      writeStoredCollapsed(projectId, next)
      return next
    })
  }, [projectId])

  const stageChip = useMemo(
    () => (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-accent/10 text-accent px-2 py-0.5 text-xs font-medium shrink-0"
        aria-label={`Stage: ${meta.label}`}
      >
        <Icon className="w-3.5 h-3.5" aria-hidden="true" />
        <span>{meta.label}</span>
      </span>
    ),
    [Icon, meta.label],
  )

  return (
    <div
      className={`relative w-full bg-bg-warm/50 border-b border-border-light overflow-hidden transition-[height] duration-200 ${
        collapsed ? 'h-6' : 'h-14'
      }`}
      role="region"
      aria-label="Stage hint"
    >
      {/* Expanded content */}
      <div
        className={`absolute inset-0 flex items-center gap-3 px-4 transition-opacity duration-200 ${
          collapsed ? 'opacity-0 pointer-events-none' : 'opacity-100'
        }`}
        aria-hidden={collapsed}
      >
        {stageChip}
        <p className="text-sm text-text-muted truncate flex-1 min-w-0">{goal}</p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onTaskClick}
            className="inline-flex items-center gap-1 rounded-full bg-surface-hover hover:bg-surface text-text-muted hover:text-text px-2.5 py-1 text-xs transition-colors"
          >
            <ClipboardList className="w-3.5 h-3.5" aria-hidden="true" />
            <span>任務</span>
          </button>
          <button
            type="button"
            onClick={onStartWithAiClick}
            data-startwith-anchor=""
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-colors ${
              flashing
                ? 'bg-accent/15 text-accent animate-chip-flash'
                : 'bg-surface-hover hover:bg-surface text-text-muted hover:text-text'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
            <span>起頭</span>
          </button>
          <button
            type="button"
            onClick={toggle}
            className="inline-flex items-center justify-center w-7 h-7 rounded-full text-text-muted hover:text-text hover:bg-surface-hover transition-colors"
            aria-label="收合階段提示"
          >
            <ChevronUp className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Collapsed content — entire bar acts as expand affordance. */}
      <button
        type="button"
        onClick={toggle}
        className={`absolute inset-0 flex items-center gap-2 px-4 text-left transition-opacity duration-200 ${
          collapsed ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        aria-hidden={!collapsed}
        aria-label="展開階段提示"
        tabIndex={collapsed ? 0 : -1}
      >
        {stageChip}
        <span className="text-xs text-text-muted truncate flex-1 min-w-0">點此展開階段提示</span>
        <ChevronDown className="w-4 h-4 text-text-muted shrink-0" aria-hidden="true" />
      </button>

      {/* Sweep overlay — remounts on stage change via key. */}
      {sweepActive && !reducedMotion && (
        <div
          key={sweepKey}
          className="animate-stage-sweep absolute inset-0"
          aria-hidden="true"
        />
      )}
    </div>
  )
}

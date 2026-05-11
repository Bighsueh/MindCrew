// 雙鑽石進度條
// 以 SVG + Tailwind 繪製 4 個鑽石（與 OnboardingModal 的 DoubleDiamondDiagram 視覺一致），
// 各鑽石為可 hover 的按鈕；hover 後浮出 popover 顯示該 macro stage 的 3 個 micro phase。

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/utils'
import type { DTStage, MicroPhaseId } from '../../types/models'
import { MACRO_STAGES, type MacroStageMeta } from './microPhaseInfo'

const PHASE_ORDER: Record<DTStage, number> = {
  discover: 0,
  define: 1,
  develop: 2,
  deliver: 3,
  completed: 4,
}

const MICRO_PHASE_ORDER: MicroPhaseId[] = [
  '1.1', '1.2', '1.3',
  '2.1', '2.2', '2.3',
  '3.1', '3.2', '3.3',
  '4.1', '4.2', '4.3',
]

interface DoubleDiamondProgressProps {
  currentStage: DTStage
  currentMicroPhase?: MicroPhaseId
  onPhaseClick?: (stage: DTStage) => void
  /** sm 給 workspace header（精簡）；md 給 lobby（含 summary 行） */
  size?: 'sm' | 'md'
}

type Status = 'completed' | 'current' | 'future'

export function DoubleDiamondProgress({
  currentStage,
  currentMicroPhase,
  onPhaseClick,
  size = 'sm',
}: DoubleDiamondProgressProps) {
  const currentIdx = PHASE_ORDER[currentStage] ?? 0
  const isAllCompleted = currentStage === 'completed'
  const [hoveredStage, setHoveredStage] = useState<MacroStageMeta['stage'] | null>(null)
  const anchorsRef = useRef<Map<string, HTMLButtonElement>>(new Map())
  const hoverTimerRef = useRef<number | null>(null)

  // hover 進入/離開都帶 80ms 緩衝，讓滑鼠能從 chip 滑到 popover 不被立刻關掉
  const scheduleHover = (stage: MacroStageMeta['stage'] | null) => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current)
    }
    hoverTimerRef.current = window.setTimeout(() => {
      setHoveredStage(stage)
    }, stage === null ? 120 : 0)
  }

  useEffect(() => () => {
    if (hoverTimerRef.current !== null) window.clearTimeout(hoverTimerRef.current)
  }, [])

  return (
    <div
      className={cn(
        'flex items-center',
        size === 'sm' ? 'gap-1.5' : 'gap-3',
      )}
    >
      {MACRO_STAGES.map((macro, idx) => {
        const status: Status = isAllCompleted || idx < currentIdx
          ? 'completed'
          : macro.stage === currentStage
            ? 'current'
            : 'future'

        return (
          <DiamondChip
            key={macro.stage}
            macro={macro}
            status={status}
            size={size}
            currentMicroPhase={
              status === 'current' ? currentMicroPhase : undefined
            }
            isHovered={hoveredStage === macro.stage}
            onMouseEnter={() => scheduleHover(macro.stage)}
            onMouseLeave={() => scheduleHover(null)}
            onFocus={() => scheduleHover(macro.stage)}
            onBlur={() => scheduleHover(null)}
            onClick={() => {
              if (status === 'completed') onPhaseClick?.(macro.stage)
            }}
            registerAnchor={(el) => {
              if (el) anchorsRef.current.set(macro.stage, el)
              else anchorsRef.current.delete(macro.stage)
            }}
          />
        )
      })}

      {isAllCompleted && (
        <span className="ml-1 rounded-full bg-success/15 px-2.5 py-1 text-xs font-semibold text-success">
          完成
        </span>
      )}

      {hoveredStage && (
        <StagePopover
          macro={MACRO_STAGES.find((m) => m.stage === hoveredStage)!}
          anchor={anchorsRef.current.get(hoveredStage) ?? null}
          currentMicroPhase={
            hoveredStage === currentStage ? currentMicroPhase : undefined
          }
          onMouseEnter={() => scheduleHover(hoveredStage)}
          onMouseLeave={() => scheduleHover(null)}
        />
      )}
    </div>
  )
}

// ── DiamondChip ────────────────────────────────────────────────────────────

interface DiamondChipProps {
  macro: MacroStageMeta
  status: Status
  size: 'sm' | 'md'
  currentMicroPhase?: MicroPhaseId
  isHovered: boolean
  onMouseEnter: () => void
  onMouseLeave: () => void
  onFocus: () => void
  onBlur: () => void
  onClick: () => void
  registerAnchor: (el: HTMLButtonElement | null) => void
}

function DiamondChip({
  macro,
  status,
  size,
  currentMicroPhase,
  isHovered,
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
  onClick,
  registerAnchor,
}: DiamondChipProps) {
  const diamondSize = size === 'sm' ? 22 : 32
  const showMicroDots = Boolean(currentMicroPhase) && status === 'current'

  return (
    <button
      type="button"
      ref={registerAnchor}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
      disabled={status === 'future'}
      aria-label={`${macro.label}（${macro.shape}）`}
      aria-expanded={isHovered}
      className={cn(
        'group relative flex flex-col items-center gap-1 rounded-md px-2 py-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        status !== 'future' && 'cursor-pointer hover:bg-accent/5',
        status === 'future' && 'cursor-default opacity-60',
        isHovered && 'bg-accent/5',
      )}
    >
      <svg
        width={diamondSize}
        height={diamondSize}
        viewBox="0 0 24 24"
        aria-hidden="true"
        className={cn(
          'transition-transform',
          status === 'current' && 'animate-pulse',
          isHovered && 'scale-110',
        )}
      >
        <polygon
          points="12,2 22,12 12,22 2,12"
          className={cn(
            'transition-colors',
            status === 'completed' && 'fill-accent stroke-accent',
            status === 'current' && 'fill-accent/30 stroke-accent',
            status === 'future' && 'fill-transparent stroke-border',
          )}
          strokeWidth={2}
        />
        {status === 'current' && (
          <polygon
            points="12,6 18,12 12,18 6,12"
            className="fill-accent"
          />
        )}
      </svg>

      <span
        className={cn(
          size === 'sm' ? 'text-xs' : 'text-sm',
          'font-medium whitespace-nowrap',
          status === 'completed' && 'text-accent',
          status === 'current' && 'text-text font-semibold',
          status === 'future' && 'text-text-muted',
        )}
      >
        {macro.label.split(' ')[0]}
      </span>

      {showMicroDots && (
        <div className="flex gap-0.5">
          {macro.micro.map((mp) => {
            const microIdx = MICRO_PHASE_ORDER.indexOf(mp.id)
            const curIdx = MICRO_PHASE_ORDER.indexOf(currentMicroPhase as MicroPhaseId)
            const isCompleted = microIdx < curIdx
            const isCurrent = mp.id === currentMicroPhase
            return (
              <span
                key={mp.id}
                className={cn(
                  'h-1 w-1 rounded-full transition-all',
                  isCompleted && 'bg-accent',
                  isCurrent && 'bg-accent animate-pulse',
                  !isCompleted && !isCurrent && 'bg-text-muted/30',
                )}
              />
            )
          })}
        </div>
      )}
    </button>
  )
}

// ── Stage Popover ──────────────────────────────────────────────────────────

interface StagePopoverProps {
  macro: MacroStageMeta
  anchor: HTMLElement | null
  currentMicroPhase?: MicroPhaseId
  onMouseEnter: () => void
  onMouseLeave: () => void
}

const POPOVER_WIDTH = 320

function StagePopover({
  macro,
  anchor,
  currentMicroPhase,
  onMouseEnter,
  onMouseLeave,
}: StagePopoverProps) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    if (!anchor) return
    const update = () => {
      const r = anchor.getBoundingClientRect()
      const vw = window.innerWidth
      let left = r.left + r.width / 2 - POPOVER_WIDTH / 2
      left = Math.max(8, Math.min(vw - POPOVER_WIDTH - 8, left))
      const top = r.bottom + 8
      setPos({ top, left })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [anchor])

  if (!pos || !anchor) return null

  return createPortal(
    <div
      role="tooltip"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="fixed z-50 rounded-xl border border-border bg-surface shadow-xl animate-popover-enter"
      style={{ top: pos.top, left: pos.left, width: POPOVER_WIDTH }}
    >
      <div className="border-b border-border px-4 pt-3 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text">{macro.label}</span>
          <span className="rounded-sm bg-accent/10 px-1.5 py-[1px] text-[10px] font-medium text-accent">
            {macro.shape}
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-text-muted">{macro.summary}</p>
      </div>
      <ol className="flex flex-col gap-2 px-4 py-3">
        {macro.micro.map((mp) => {
          const isCurrent = mp.id === currentMicroPhase
          return (
            <li
              key={mp.id}
              className={cn(
                'flex gap-2 rounded-md border px-2.5 py-1.5 transition-colors',
                isCurrent
                  ? 'border-accent/50 bg-accent/5'
                  : 'border-transparent',
              )}
            >
              <span
                className={cn(
                  'mt-[2px] inline-block h-4 w-4 shrink-0 rounded-full text-[10px] font-medium leading-4 text-center',
                  isCurrent ? 'bg-accent text-text-inverse' : 'bg-bg-warm text-text-muted',
                )}
              >
                {mp.id}
              </span>
              <div className="flex-1">
                <p
                  className={cn(
                    'text-xs font-semibold',
                    isCurrent ? 'text-text' : 'text-text',
                  )}
                >
                  {mp.label}
                  {isCurrent && (
                    <span className="ml-1.5 rounded-sm bg-accent px-1 py-[1px] text-[9px] font-medium text-text-inverse">
                      進行中
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                  {mp.description}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
    </div>,
    document.body,
  )
}

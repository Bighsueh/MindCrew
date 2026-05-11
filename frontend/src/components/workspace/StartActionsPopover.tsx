import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import {
  STAGE_ACTIONS,
  STAGE_LABEL,
  StartActionGrid,
  type StartActionStage,
} from '../canvas/CanvasEmptyState'
import { useReducedMotion } from '../../hooks/useReducedMotion'

export interface StartActionsPopoverProps {
  open: boolean
  stage: StartActionStage
  /** CSS selector for the chip / button to anchor against. */
  anchorSelector: string
  onClose: () => void
  onActionClick?: (actionId: string) => void
}

const POPOVER_WIDTH = 360
const POPOVER_GAP = 8

interface AnchorRect {
  left: number
  top: number
  bottom: number
  right: number
  width: number
}

function measure(selector: string): AnchorRect | null {
  if (typeof document === 'undefined') return null
  const el = document.querySelector(selector) as HTMLElement | null
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { left: r.left, top: r.top, bottom: r.bottom, right: r.right, width: r.width }
}

export function StartActionsPopover({
  open,
  stage,
  anchorSelector,
  onClose,
  onActionClick,
}: StartActionsPopoverProps) {
  const reducedMotion = useReducedMotion()
  const popoverRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    const update = () => {
      const a = measure(anchorSelector)
      if (!a) {
        setPos({ top: 80, left: 16 })
        return
      }
      const vw = window.innerWidth
      const top = a.bottom + POPOVER_GAP
      // Align popover's right edge with anchor's right edge; clamp to viewport.
      let left = a.right - POPOVER_WIDTH
      left = Math.max(8, Math.min(vw - POPOVER_WIDTH - 8, left))
      setPos({ top, left })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, { capture: true })
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, { capture: true } as EventListenerOptions)
    }
  }, [open, anchorSelector])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        const anchor = document.querySelector(anchorSelector)
        if (anchor && anchor.contains(e.target as Node)) return
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open, onClose, anchorSelector])

  if (!open || !pos) return null

  const actions = STAGE_ACTIONS[stage]
  const stageLabel = STAGE_LABEL[stage]

  return createPortal(
    <div
      ref={popoverRef}
      role="dialog"
      aria-label={`${stageLabel} 階段起手式`}
      className="fixed z-50 rounded-xl border border-border bg-surface shadow-xl animate-popover-enter"
      style={{
        top: pos.top,
        left: pos.left,
        width: POPOVER_WIDTH,
        transformOrigin: 'top right',
      }}
    >
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wide text-text-muted">
            起手式 · {stageLabel} 階段
          </span>
          <h3 className="text-sm font-semibold text-text">挑一個方式開始</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="關閉起手式"
          className="flex h-7 w-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover hover:text-text transition-colors"
        >
          <X size={14} />
        </button>
      </div>
      <div className="px-4 pb-4">
        <StartActionGrid
          actions={actions}
          onActionClick={(id) => {
            onActionClick?.(id)
            onClose()
          }}
          dense
          animate={!reducedMotion}
        />
      </div>
    </div>,
    document.body,
  )
}

export default StartActionsPopover

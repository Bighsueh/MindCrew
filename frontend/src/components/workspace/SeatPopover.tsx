import { useEffect, useRef, useState } from 'react'
import { cn } from '../../lib/utils'
import type { Seat } from '../../types/models'
import { SeatPersonaCard, type SeatStatus } from './SeatPersonaCard'

// 沿用舊匯出路徑：SeatBar / SeatChip 仍從 './SeatPopover' 取 SeatStatus。
export type { SeatStatus } from './SeatPersonaCard'

interface SeatPopoverProps {
  seat: Seat
  status: SeatStatus
  displayName: string
  roleLabel: string
  preview?: string
  isCurrentUser: boolean
  onClose: () => void
  /** 彈出方向：'top' = 往上開（底部 bar 用，預設）；'bottom' = 往下開（頂部 bar 用）。 */
  placement?: 'top' | 'bottom'
  /** 建立者且此席為 AI 組員時為 true → 卡片可就地編輯人設。 */
  canEditPersona?: boolean
  projectId?: string
  onPersonaSaved?: (seat: Seat) => void
}

/**
 * SeatPopover — 座位 chip 浮出的資料卡「定位外框」。
 * 內容本體共用 {@link SeatPersonaCard}（與聊天室隊友清單一致）。
 */
export function SeatPopover({
  seat,
  status,
  displayName,
  roleLabel,
  preview,
  isCurrentUser,
  onClose,
  placement = 'top',
  canEditPersona = false,
  projectId,
  onPersonaSaved,
}: SeatPopoverProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // 編輯中按 Esc 先退出編輯態，不直接關卡片（避免誤丟草稿）。
      if (e.key !== 'Escape') return
      if (editing) setEditing(false)
      else onClose()
    }
    const onClick = (e: MouseEvent) => {
      // 編輯中不因點外面就關閉，避免半填的人設被丟掉。
      if (editing) return
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [onClose, editing])

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={`${displayName} 資料卡`}
      className={cn(
        'absolute left-1/2 z-50 w-80 -translate-x-1/2',
        placement === 'bottom' ? 'top-full mt-2' : 'bottom-full mb-2',
        'animate-popover-enter rounded-xl border border-border bg-surface shadow-xl',
        'max-h-[70vh] overflow-auto',
      )}
      style={{ transformOrigin: placement === 'bottom' ? 'top center' : 'bottom center' }}
    >
      <SeatPersonaCard
        seat={seat}
        status={status}
        displayName={displayName}
        roleLabel={roleLabel}
        preview={preview}
        isCurrentUser={isCurrentUser}
        editing={editing}
        onEditingChange={setEditing}
        canEditPersona={canEditPersona}
        projectId={projectId}
        onPersonaSaved={onPersonaSaved}
        onClose={onClose}
      />
    </div>
  )
}

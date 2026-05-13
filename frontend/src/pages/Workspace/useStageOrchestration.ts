import { useCallback, useEffect, useRef, useState } from 'react'
import type { DTStage } from '../../types/models'

interface UseStageOrchestrationOptions {
  currentStage: DTStage
}

interface UseStageOrchestrationResult {
  /** 「請 AI 起頭」chip 的一次性 flash 計數；遞增即觸發動畫。 */
  startChipFlashKey: number
  flashStartChip: () => void

  /** 起手式 popover 開關。 */
  startPopoverOpen: boolean
  openStartPopover: () => void
  closeStartPopover: () => void
  toggleStartPopover: () => void

  /** 哪些階段的 EmptyState banner 已被使用者收起，不再自動顯示。 */
  bannerDismissedStages: Set<DTStage>
  dismissBanner: (stage: DTStage) => void

  /** 白板上 shape 數量（由 CanvasPanel onShapeCountChange 回報）。 */
  shapeCount: number
  setShapeCount: (n: number) => void
}

/**
 * Workspace stage orchestration：管理 EmptyState banner、起手式 popover、
 * 「起頭」chip flash 動畫等與階段切換相關的暫存 UI state。
 *
 * 注意：所有狀態都是 session 範圍，不持久化（避免使用者離開重來時 banner 永遠不顯示）。
 */
export function useStageOrchestration({
  currentStage,
}: UseStageOrchestrationOptions): UseStageOrchestrationResult {
  const [startChipFlashKey, setStartChipFlashKey] = useState(0)
  const [startPopoverOpen, setStartPopoverOpen] = useState(false)
  const [bannerDismissedStages, setBannerDismissedStages] = useState<Set<DTStage>>(
    () => new Set(),
  )
  const [shapeCount, setShapeCount] = useState(0)

  // 階段切換 → reset dismissed flag（讓 banner 在新階段重新出現一次）。
  const prevStageRef = useRef<DTStage>(currentStage)
  useEffect(() => {
    if (prevStageRef.current === currentStage) return
    prevStageRef.current = currentStage
    setBannerDismissedStages((prev) => {
      if (!prev.has(currentStage)) return prev
      const next = new Set(prev)
      next.delete(currentStage)
      return next
    })
  }, [currentStage])

  const flashStartChip = useCallback(() => {
    setStartChipFlashKey((k) => k + 1)
  }, [])

  const openStartPopover = useCallback(() => setStartPopoverOpen(true), [])
  const closeStartPopover = useCallback(() => setStartPopoverOpen(false), [])
  const toggleStartPopover = useCallback(() => setStartPopoverOpen((v) => !v), [])

  const dismissBanner = useCallback((stage: DTStage) => {
    setBannerDismissedStages((prev) => {
      if (prev.has(stage)) return prev
      const next = new Set(prev)
      next.add(stage)
      return next
    })
  }, [])

  return {
    startChipFlashKey,
    flashStartChip,
    startPopoverOpen,
    openStartPopover,
    closeStartPopover,
    toggleStartPopover,
    bannerDismissedStages,
    dismissBanner,
    shapeCount,
    setShapeCount,
  }
}

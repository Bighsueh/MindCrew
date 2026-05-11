import { useCallback, useEffect, useLayoutEffect, useState } from 'react'
import { useFirstRunFlag } from '../../hooks/useFirstRunFlag'
import { useReducedMotion } from '../../hooks/useReducedMotion'

export interface TourStep {
  id: string
  selector: string
  caption: string
  fallbackPosition?: { top: number; left: number }
  captionSide?: 'top' | 'bottom' | 'left' | 'right'
}

export interface FirstRunTourProps {
  steps: TourStep[]
  storageKey?: string
  forceShow?: boolean
}

interface DotPosition {
  top: number
  left: number
}

const DOT_SIZE = 12
const CAPTION_GAP = 12

function measureAnchor(step: TourStep): DotPosition {
  if (typeof document === 'undefined') {
    return step.fallbackPosition ?? { top: 0, left: 0 }
  }
  const el = document.querySelector(step.selector)
  if (!el) {
    return step.fallbackPosition ?? { top: window.innerHeight / 2, left: window.innerWidth / 2 }
  }
  const rect = el.getBoundingClientRect()
  return {
    top: rect.top + rect.height / 2,
    left: rect.left + rect.width / 2,
  }
}

function captionOffset(side: TourStep['captionSide']): { top: number; left: number; transform: string } {
  switch (side) {
    case 'top':
      return { top: -(DOT_SIZE / 2 + CAPTION_GAP), left: 0, transform: 'translate(-50%, -100%)' }
    case 'bottom':
      return { top: DOT_SIZE / 2 + CAPTION_GAP, left: 0, transform: 'translate(-50%, 0)' }
    case 'left':
      return { top: 0, left: -(DOT_SIZE / 2 + CAPTION_GAP), transform: 'translate(-100%, -50%)' }
    case 'right':
    default:
      return { top: 0, left: DOT_SIZE / 2 + CAPTION_GAP, transform: 'translate(0, -50%)' }
  }
}

export function FirstRunTour({ steps, storageKey, forceShow = false }: FirstRunTourProps) {
  const [shouldShow, dismiss] = useFirstRunFlag(storageKey ?? 'workspace-tour')
  const reducedMotion = useReducedMotion()

  const [stepIndex, setStepIndex] = useState(0)
  const [position, setPosition] = useState<DotPosition>({ top: 0, left: 0 })
  const [captionVisible, setCaptionVisible] = useState(false)
  const [fadingOut, setFadingOut] = useState(false)
  const [unmounted, setUnmounted] = useState(false)

  const active = (shouldShow || forceShow) && !unmounted && steps.length > 0
  const currentStep = active ? steps[Math.min(stepIndex, steps.length - 1)] : null

  const advance = useCallback(() => {
    setStepIndex((prev) => prev + 1)
  }, [])

  // 量測目前 step 的錨點位置
  useLayoutEffect(() => {
    if (!currentStep) return
    setPosition(measureAnchor(currentStep))
  }, [currentStep])

  // caption 進場動畫：每次切換 step 重新觸發
  useEffect(() => {
    if (!currentStep) return
    setCaptionVisible(false)
    const t = window.setTimeout(() => setCaptionVisible(true), 60)
    return () => window.clearTimeout(t)
  }, [currentStep])

  // resize / scroll 重新量測
  useEffect(() => {
    if (!currentStep) return
    const remeasure = () => setPosition(measureAnchor(currentStep))
    window.addEventListener('resize', remeasure)
    window.addEventListener('scroll', remeasure, true)
    return () => {
      window.removeEventListener('resize', remeasure)
      window.removeEventListener('scroll', remeasure, true)
    }
  }, [currentStep])

  // 把 click listener 綁到實際的錨點元素，使「點擊真實元素」也能 advance
  useEffect(() => {
    if (!currentStep) return
    const el = document.querySelector(currentStep.selector)
    if (!el) return
    const handler = () => advance()
    el.addEventListener('click', handler, { once: true })
    return () => el.removeEventListener('click', handler)
  }, [currentStep, advance])

  // 走完所有 step：fade out → dismiss → unmount
  useEffect(() => {
    if (!active) return
    if (stepIndex < steps.length) return
    setFadingOut(true)
    const t = window.setTimeout(() => {
      dismiss()
      setUnmounted(true)
    }, 300)
    return () => window.clearTimeout(t)
  }, [stepIndex, steps.length, active, dismiss])

  if (!active || !currentStep) return null

  const offset = captionOffset(currentStep.captionSide ?? 'right')
  const dotAnimClass = reducedMotion ? '' : 'animate-breathing'
  const overlayOpacity = fadingOut ? 0 : 1

  return (
    <div
      className="fixed inset-0 z-50"
      style={{ pointerEvents: 'none', opacity: overlayOpacity, transition: 'opacity 300ms var(--ease-standard)' }}
      aria-live="polite"
    >
      <button
        type="button"
        aria-label={`第 ${stepIndex + 1} 步，共 ${steps.length} 步：${currentStep.caption}`}
        onClick={advance}
        className={`absolute bg-accent rounded-full ${dotAnimClass}`}
        style={{
          width: DOT_SIZE,
          height: DOT_SIZE,
          top: position.top,
          left: position.left,
          transform: 'translate(-50%, -50%)',
          transition: reducedMotion ? 'none' : 'top 600ms var(--ease-standard), left 600ms var(--ease-standard)',
          pointerEvents: 'auto',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
        }}
      />

      <div
        className="absolute bg-surface text-text text-xs px-2 py-1 rounded-md shadow-md flex items-center gap-2 whitespace-nowrap"
        style={{
          top: position.top + offset.top,
          left: position.left + offset.left,
          transform: `${offset.transform} translateY(${captionVisible ? 0 : 4}px)`,
          opacity: captionVisible ? 1 : 0,
          transition: 'opacity 180ms var(--ease-standard), transform 180ms var(--ease-standard)',
          pointerEvents: 'none',
        }}
      >
        <span className="opacity-60">{stepIndex + 1}/{steps.length}</span>
        <span>{currentStep.caption}</span>
      </div>

      <button
        type="button"
        onClick={() => {
          setFadingOut(true)
          window.setTimeout(() => {
            dismiss()
            setUnmounted(true)
          }, 200)
        }}
        className="fixed bottom-4 right-4 bg-surface text-text text-xs px-3 py-1.5 rounded-md shadow-md hover:opacity-80"
        style={{ pointerEvents: 'auto' }}
      >
        略過
      </button>
    </div>
  )
}

export default FirstRunTour

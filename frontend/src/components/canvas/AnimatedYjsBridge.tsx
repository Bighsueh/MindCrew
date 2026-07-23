/**
 * AnimatedYjsBridge — Manages CSS transition toggle for AI note movements.
 *
 * Rendered inside <Tldraw> to access useEditor(). Adds/removes the
 * `.ai-animating` class on the tldraw shape container to enable CSS
 * transition on .tl-shape elements during AI-initiated position changes.
 *
 * Human drags are excluded: pointerDown immediately removes the class.
 */
import { useCallback, useEffect, useRef } from 'react'
import { useEditor } from '@tldraw/tldraw'
import type { TLStore } from '@tldraw/tldraw'
import type * as Y from 'yjs'
import { useAnimatedYjsSync } from './useAnimatedYjsSync'
import { useHumanDragSync } from './useHumanDragSync'
import { adjustedDuration } from '../../lib/animationCapability'

// Phase 42 D1b (spec 12 §3.3 v4.1)：單張動畫時長下限 600ms（與 index.css 一致）；
// 依 animationCapability 縮放（reduced 砍半、off 0）。disable timer 用縮放後值＋buffer。
const TRANSITION_DURATION_MS = 600
const TRANSITION_BUFFER_MS = 200

interface AnimatedYjsBridgeProps {
  shapesMap: Y.Map<unknown> | null
  store: TLStore
}

export function AnimatedYjsBridge({ shapesMap, store }: AnimatedYjsBridgeProps) {
  const editor = useEditor()
  const containerRef = useRef<HTMLElement | null>(null)
  const timerRef = useRef<number>(0)

  // Find the tldraw shapes container once
  useEffect(() => {
    // tldraw renders shapes inside a div with class "tl-shapes"
    const findContainer = () => {
      const el = document.querySelector('.tl-shapes') as HTMLElement | null
      if (el) {
        containerRef.current = el
      } else {
        // Retry on next frame if tldraw hasn't mounted yet
        requestAnimationFrame(findContainer)
      }
    }
    findContainer()
  }, [])

  const enableTransition = useCallback(() => {
    const el = containerRef.current
    if (!el) return

    // Don't enable if user is currently interacting (dragging)
    if (editor.inputs.isPointing) return

    el.classList.add('ai-animating')
    // Reset the disable timer — will be set by onPositionChangeEnd
    clearTimeout(timerRef.current)
  }, [editor])

  const scheduleDisableTransition = useCallback(() => {
    clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      containerRef.current?.classList.remove('ai-animating')
    }, adjustedDuration(TRANSITION_DURATION_MS) + TRANSITION_BUFFER_MS)
  }, [])

  // Remove transition immediately on any pointer interaction
  useEffect(() => {
    const removeTransition = () => {
      containerRef.current?.classList.remove('ai-animating')
      clearTimeout(timerRef.current)
    }

    // Listen for pointer down on the tldraw container
    const container = document.querySelector('.tl-container')
    if (container) {
      container.addEventListener('pointerdown', removeTransition)
      return () => container.removeEventListener('pointerdown', removeTransition)
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(timerRef.current)
      containerRef.current?.classList.remove('ai-animating')
    }
  }, [])

  useAnimatedYjsSync(shapesMap, store, enableTransition, scheduleDisableTransition)
  // Phase 42 C0 ⑥(a)：真人拖曳回寫 Yjs（move-delta 事件的資料前提）
  useHumanDragSync(shapesMap, store)

  return null
}

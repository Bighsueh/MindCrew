import { useCallback, useEffect, useRef, useState, type TransitionEvent } from 'react'
import { cn } from '@/lib/utils'
import heroBgVideo from '@/assets/hero-bg.mp4'

const INITIAL_PLAY_DELAY_MS = 500
const POST_END_PAUSE_MS = 3000
const PRE_RESTART_DELAY_MS = 2000
const FADE_DURATION_MS = 3000
const FADE_END_FALLBACK_BUFFER_MS = 120

interface HeroBackgroundVideoProps {
  /** 'playing' = normal loop, 'static-frame' = paused at frame 0 */
  readonly mode?: 'playing' | 'static-frame'
}

export function HeroBackgroundVideo({ mode = 'playing' }: HeroBackgroundVideoProps) {
  const isStatic = mode === 'static-frame'
  const playVideoRef = useRef<HTMLVideoElement>(null)
  const startFrameVideoRef = useRef<HTMLVideoElement>(null)
  const timeoutIdsRef = useRef<number[]>([])
  const mountedRef = useRef(true)
  const reducedMotionRef = useRef(false)
  const expectingFadeEndRef = useRef(false)
  const [showStartFrame, setShowStartFrame] = useState(false)
  const [noOpacityTransition, setNoOpacityTransition] = useState(false)

  const fadeTransitionStyle = noOpacityTransition
    ? undefined
    : {
        transitionTimingFunction: 'var(--ease-out)',
        transitionDuration: `${FADE_DURATION_MS}ms`,
      }

  const clearScheduledTimeouts = useCallback(() => {
    timeoutIdsRef.current.forEach((id) => window.clearTimeout(id))
    timeoutIdsRef.current = []
  }, [])

  const scheduleTimeout = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(() => {
      timeoutIdsRef.current = timeoutIdsRef.current.filter((t) => t !== id)
      fn()
    }, ms)
    timeoutIdsRef.current.push(id)
  }, [])

  const tryPlay = useCallback((el: HTMLVideoElement | null) => {
    if (!el || !mountedRef.current) return
    const run = () => {
      if (!mountedRef.current) return
      void el.play().catch(() => {})
    }
    if (el.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
      run()
    } else {
      const onCanPlay = () => {
        run()
      }
      el.addEventListener('canplay', onCanPlay, { once: true })
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    reducedMotionRef.current = mq.matches
    const onChange = () => {
      reducedMotionRef.current = mq.matches
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  // Handle mode changes: pause/resume playback
  useEffect(() => {
    if (isStatic) {
      clearScheduledTimeouts()
      expectingFadeEndRef.current = false
      const playEl = playVideoRef.current
      if (playEl) {
        playEl.pause()
      }
      setShowStartFrame(true)
      setNoOpacityTransition(true)
    } else {
      // Resume playing mode
      setNoOpacityTransition(true)
      setShowStartFrame(false)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!mountedRef.current) return
          setNoOpacityTransition(false)
          scheduleTimeout(() => tryPlay(playVideoRef.current), INITIAL_PLAY_DELAY_MS)
        })
      })
    }
    return () => {
      clearScheduledTimeouts()
    }
  }, [isStatic, scheduleTimeout, tryPlay, clearScheduledTimeouts])

  const completeCrossfade = useCallback(() => {
    if (!expectingFadeEndRef.current) return
    expectingFadeEndRef.current = false

    const playEl = playVideoRef.current
    if (playEl) {
      playEl.pause()
      playEl.currentTime = 0
    }
    const startFrameEl = startFrameVideoRef.current
    if (startFrameEl) {
      startFrameEl.pause()
      startFrameEl.currentTime = 0
    }
    if (!mountedRef.current) return
    scheduleTimeout(() => {
      if (reducedMotionRef.current || !mountedRef.current) return
      setNoOpacityTransition(true)
      setShowStartFrame(false)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!mountedRef.current) return
          setNoOpacityTransition(false)
          tryPlay(playVideoRef.current)
        })
      })
    }, PRE_RESTART_DELAY_MS)
  }, [scheduleTimeout, tryPlay])

  const handleEnded = useCallback(() => {
    if (reducedMotionRef.current) return
    scheduleTimeout(() => {
      if (reducedMotionRef.current || !mountedRef.current) return
      const startFrameEl = startFrameVideoRef.current
      if (startFrameEl) {
        startFrameEl.pause()
        startFrameEl.currentTime = 0
      }
      expectingFadeEndRef.current = true
      setShowStartFrame(true)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!mountedRef.current || !expectingFadeEndRef.current) return
          scheduleTimeout(
            () => completeCrossfade(),
            FADE_DURATION_MS + FADE_END_FALLBACK_BUFFER_MS,
          )
        })
      })
    }, POST_END_PAUSE_MS)
  }, [completeCrossfade, scheduleTimeout])

  const handlePlayLayerTransitionEnd = useCallback(
    (e: TransitionEvent<HTMLDivElement>) => {
      if (e.propertyName !== 'opacity') return
      completeCrossfade()
    },
    [completeCrossfade],
  )

  return (
    <div className="relative h-full w-full">
      <div
        className={cn(
          'absolute inset-0',
          noOpacityTransition ? 'transition-none' : 'transition-opacity',
          showStartFrame ? 'opacity-0' : 'opacity-100',
        )}
        style={fadeTransitionStyle}
        onTransitionEnd={handlePlayLayerTransitionEnd}
      >
        <video
          ref={playVideoRef}
          muted
          playsInline
          preload="auto"
          className="h-full w-full object-cover"
          onEnded={handleEnded}
        >
          <source src={heroBgVideo} type="video/mp4" />
        </video>
      </div>

      <div
        className={cn(
          'absolute inset-0',
          noOpacityTransition ? 'transition-none' : 'transition-opacity',
          showStartFrame ? 'opacity-100' : 'opacity-0',
        )}
        style={fadeTransitionStyle}
        aria-hidden
      >
        <video
          ref={startFrameVideoRef}
          muted
          playsInline
          preload="metadata"
          className="h-full w-full object-cover"
          onLoadedData={() => {
            const el = startFrameVideoRef.current
            if (!el) return
            el.pause()
            el.currentTime = 0
          }}
        >
          <source src={heroBgVideo} type="video/mp4" />
        </video>
      </div>
    </div>
  )
}

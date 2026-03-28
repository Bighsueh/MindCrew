interface StickyNoteSVGProps {
  readonly color: string
  readonly rotation: number
  readonly text: string
  /** Enable subtle floating animation. Default: false */
  readonly float?: boolean
  /** Animation delay for stagger effect (e.g. '0s', '0.5s'). */
  readonly floatDelay?: string
}

export function StickyNoteSVG({ color, rotation, text, float = false, floatDelay = '0s' }: StickyNoteSVGProps) {
  return (
    <div
      className={`hidden sm:flex h-28 w-28 items-center justify-center rounded-sm p-3 shadow-note md:h-36 md:w-36 ${float ? 'animate-float-note' : ''}`}
      style={{
        backgroundColor: color,
        transform: `rotate(${rotation}deg)`,
        ['--note-rotate' as string]: `${rotation}deg`,
        animationDelay: float ? floatDelay : undefined,
      }}
    >
      <p className="text-center text-sm font-bold text-primary/90 leading-tight md:text-base">
        {text}
      </p>
    </div>
  )
}

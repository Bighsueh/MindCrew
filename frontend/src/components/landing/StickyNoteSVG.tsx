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
      className={`hidden sm:flex h-20 w-20 items-center justify-center rounded-sm p-2 shadow-md md:h-24 md:w-24 ${float ? 'animate-float' : ''}`}
      style={{
        backgroundColor: color,
        transform: `rotate(${rotation}deg)`,
        ['--note-rotate' as string]: `${rotation}deg`,
        animationDelay: float ? floatDelay : undefined,
      }}
    >
      <p className="text-center text-[10px] font-semibold text-primary/70 leading-tight md:text-xs">
        {text}
      </p>
    </div>
  )
}

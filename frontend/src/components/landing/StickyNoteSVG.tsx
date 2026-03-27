interface StickyNoteSVGProps {
  readonly color: string
  readonly rotation: number
  readonly text: string
}

export function StickyNoteSVG({ color, rotation, text }: StickyNoteSVGProps) {
  return (
    <div
      className="hidden sm:flex h-20 w-20 items-center justify-center rounded-sm p-2 shadow-md md:h-24 md:w-24"
      style={{
        backgroundColor: color,
        transform: `rotate(${rotation}deg)`,
      }}
    >
      <p className="text-center text-[10px] font-semibold text-primary/70 leading-tight md:text-xs">
        {text}
      </p>
    </div>
  )
}

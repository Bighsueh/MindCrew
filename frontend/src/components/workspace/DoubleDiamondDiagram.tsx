// 雙鑽石示意圖（Onboarding Modal 用）
// 純 SVG + Tailwind，不依賴外部 asset。

import type { DTStage } from '../../types/models'

export interface DoubleDiamondDiagramProps {
  /** 若提供，會以 accent 色 highlight 對應階段標籤；不提供則全部平等呈現 */
  currentStage?: DTStage
  className?: string
}

interface StagePoint {
  id: Exclude<DTStage, 'completed'>
  label: string
  x: number
  /** 'top' | 'bottom' — 文字相對於菱形頂點的位置 */
  anchor: 'top' | 'bottom'
}

// viewBox 0 0 600 200；兩個菱形：左 (20,100)→(160,40)→(300,100)→(160,160)
//                                右 (300,100)→(440,40)→(580,100)→(440,160)
const STAGE_POINTS: StagePoint[] = [
  { id: 'discover', label: 'Discover 發現', x: 20, anchor: 'bottom' },
  { id: 'define', label: 'Define 定義', x: 300, anchor: 'top' },
  { id: 'develop', label: 'Develop 發展', x: 300, anchor: 'bottom' },
  { id: 'deliver', label: 'Deliver 交付', x: 580, anchor: 'top' },
]

const DIAMOND_LEFT = 'M 20 100 L 160 40 L 300 100 L 160 160 Z'
const DIAMOND_RIGHT = 'M 300 100 L 440 40 L 580 100 L 440 160 Z'

export function DoubleDiamondDiagram({
  currentStage,
  className = '',
}: DoubleDiamondDiagramProps) {
  return (
    <div className={`w-full ${className}`}>
      <svg
        viewBox="0 0 600 240"
        role="img"
        aria-label="設計思考雙鑽石流程示意圖"
        className="h-auto w-full"
      >
        {/* 兩個鑽石外框 */}
        <path
          d={DIAMOND_LEFT}
          className="fill-accent/5 stroke-accent/50"
          strokeWidth={2}
        />
        <path
          d={DIAMOND_RIGHT}
          className="fill-accent/5 stroke-accent/50"
          strokeWidth={2}
        />

        {/* 中段收斂點（Define）與右端收斂點（Deliver）— 實心圓強調收斂 */}
        <circle cx={300} cy={100} r={6} className="fill-accent" />
        <circle cx={580} cy={100} r={6} className="fill-accent" />

        {/* 鑽石中央標籤 */}
        <text
          x={160}
          y={105}
          textAnchor="middle"
          className="fill-text-muted text-[12px] font-medium"
        >
          第一鑽石・找對問題
        </text>
        <text
          x={440}
          y={105}
          textAnchor="middle"
          className="fill-text-muted text-[12px] font-medium"
        >
          第二鑽石・做對解法
        </text>

        {/* 四個階段標籤 */}
        {STAGE_POINTS.map((p) => {
          const isActive = currentStage === p.id
          const y = p.anchor === 'top' ? 30 : 185
          return (
            <g key={p.id}>
              <text
                x={p.x}
                y={y}
                textAnchor="middle"
                className={
                  isActive
                    ? 'fill-accent text-[13px] font-semibold'
                    : 'fill-text text-[13px] font-medium'
                }
              >
                {p.label}
              </text>
            </g>
          )
        })}

        {/* 底部說明 — 發散 / 收斂屬性 */}
        <text x={90} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          發散
        </text>
        <text x={230} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          收斂
        </text>
        <text x={370} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          發散
        </text>
        <text x={510} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          收斂
        </text>
      </svg>
    </div>
  )
}

export default DoubleDiamondDiagram

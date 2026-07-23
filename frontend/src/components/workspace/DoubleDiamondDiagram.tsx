// 單鑽石示意圖（Onboarding Modal 用）
// 純 SVG + Tailwind，不依賴外部 asset。

import type { DTStage } from '../../types/models'
import { STAGE_LABELS_PLAIN } from '../../utils/formatters'

export interface DoubleDiamondDiagramProps {
  /** 若提供，會以 accent 色 highlight 對應階段標籤；不提供則全部平等呈現 */
  currentStage?: DTStage
  className?: string
}

interface StagePoint {
  id: Exclude<DTStage, 'completed'>
  x: number
  /** 'top' | 'bottom' — 文字相對於菱形頂點的位置 */
  anchor: 'top' | 'bottom'
}

// viewBox 0 0 600 200；單菱形左 (60,100)→(280,40)→(500,100)→(280,160)
// 右端 (560,100) 為「第一鑽石完成」標記。
// 階段標籤一律取自 STAGE_LABELS_PLAIN 單一真相源（spec 28 §6：元件不得自帶英文 map）。
const STAGE_POINTS: StagePoint[] = [
  { id: 'discover', x: 60, anchor: 'bottom' },
  { id: 'define', x: 500, anchor: 'top' },
]

const DIAMOND = 'M 60 100 L 280 40 L 500 100 L 280 160 Z'

export function DoubleDiamondDiagram({
  currentStage,
  className = '',
}: DoubleDiamondDiagramProps) {
  const isCompleted = currentStage === 'completed'

  return (
    <div className={`w-full ${className}`}>
      <svg
        viewBox="0 0 600 240"
        role="img"
        aria-label="設計思考第一鑽石流程示意圖"
        className="h-auto w-full"
      >
        {/* 第一鑽石外框 */}
        <path
          d={DIAMOND}
          className="fill-accent/5 stroke-accent/50"
          strokeWidth={2}
        />

        {/* 收斂點（定義階段）— 實心圓強調收斂 */}
        <circle cx={500} cy={100} r={6} className="fill-accent" />

        {/* 完成圖示（在收斂點右側） */}
        {isCompleted && (
          <g>
            <circle cx={560} cy={100} r={14} className="fill-success/15 stroke-success" strokeWidth={2} />
            <text
              x={560}
              y={105}
              textAnchor="middle"
              className="fill-success text-[14px] font-bold"
            >
              ✓
            </text>
          </g>
        )}

        {/* 鑽石中央標籤 */}
        <text
          x={280}
          y={105}
          textAnchor="middle"
          className="fill-text-muted text-[12px] font-medium"
        >
          第一鑽石・找對問題
        </text>

        {/* 兩個階段標籤 */}
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
                {STAGE_LABELS_PLAIN[p.id]}
              </text>
            </g>
          )
        })}

        {/* 底部說明 — 發散 / 收斂屬性 */}
        <text x={150} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          發散
        </text>
        <text x={400} y={220} textAnchor="middle" className="fill-text-muted text-[11px]">
          收斂
        </text>
      </svg>
    </div>
  )
}

export default DoubleDiamondDiagram

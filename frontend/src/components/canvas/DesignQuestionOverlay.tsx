/**
 * DesignQuestionOverlay — 設計題目（2.7）專屬外框＋角標（Phase 42 C2）.
 *
 * spec 23 v2.0 §2.4 / spec 25 v2.0 §3.3：設計題目便條文字＝「我們可以怎麼…？」句型；
 * 便條色＝作者身分色，**語意不得用顏色表達**（#34）。故由前端依文字句型辨識，畫一個
 * 專屬外框＋左上角小字「設計題目」。純視覺、與 gate 判定無關（列此防混淆）。
 *
 * 註：`kind` 欄位僅 content|label（spec 27 §10），不擴充 enum；「kind 驅動」於此落地為
 * 「依便條內容類型（文字句型）渲染」。
 */
import { useEditor } from '@tldraw/tldraw'
import type { TLShape } from '@tldraw/tldraw'
import { track } from '@tldraw/state-react'

const NOTE_W = 200
const NOTE_H = 150

// 與後端 hmw 模板同句型（spec 23 v2.0 §2.4，text_templates.py）。
const DESIGN_QUESTION_RE = /我們可以怎麼.+[?？]/

function isDesignQuestion(shape: TLShape): boolean {
  if (shape.type !== 'note') return false
  const text = (shape.props as { text?: string })?.text ?? ''
  return DESIGN_QUESTION_RE.test(text)
}

export const DesignQuestionOverlay = track(function DesignQuestionOverlay() {
  const editor = useEditor()
  const zoom = editor.getZoomLevel()

  const matches = editor.getCurrentPageShapes().filter(isDesignQuestion)
  if (matches.length === 0) return null

  return (
    <>
      {matches.map((shape) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        return (
          <div
            key={`dq-${shape.id}`}
            className="pointer-events-none absolute z-20"
            style={{
              left: point.x,
              top: point.y,
              width: NOTE_W * zoom,
              height: NOTE_H * zoom,
            }}
          >
            {/* 專屬外框（不依賴便條填色傳達語意，#34） */}
            <div className="absolute inset-0 rounded-md border-2 border-indigo-500/80" />
            {/* 左上角小字角標 */}
            <div className="absolute -top-2 left-1 rounded bg-indigo-600 px-1.5 py-0.5 text-[10px] font-medium leading-none text-white shadow">
              設計題目
            </div>
          </div>
        )
      })}
    </>
  )
})

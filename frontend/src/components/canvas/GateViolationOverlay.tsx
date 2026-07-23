/**
 * GateViolationOverlay — 把 GateViolationBadge 掛到實際便條上（Phase 42 C0 ⑥(b)）。
 *
 * 真人 force_publish 的便條由後端寫入 gate_violation metadata（sidecar 合併進
 * NoteShape → buildRecord 帶進 meta，JSON 字串）。本 overlay 對有違規標記的便條
 * 在右下角渲染 ⚠️ badge（Spec 13 §7.1）。
 */
import { useEditor } from '@tldraw/tldraw'
import { track } from '@tldraw/state-react'
import { GateViolationBadge, type GateViolationMeta } from './GateViolationBadge'

const NOTE_W = 200
const NOTE_H = 150

function parseViolation(raw: unknown): GateViolationMeta | null {
  if (typeof raw !== 'string' || raw.length === 0) return null
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object') return null
    return {
      phase: String(parsed.phase ?? ''),
      zone_id: typeof parsed.zone_id === 'string' ? parsed.zone_id : undefined,
      rule: String(parsed.rule ?? ''),
      module: String(parsed.module ?? ''),
      matched_text:
        typeof parsed.matched_text === 'string' ? parsed.matched_text : undefined,
    }
  } catch {
    return null
  }
}

export const GateViolationOverlay = track(function GateViolationOverlay() {
  const editor = useEditor()
  const zoom = editor.getZoomLevel()

  const flagged = editor
    .getCurrentPageShapes()
    .map((shape) => ({
      shape,
      violation:
        shape.type === 'note'
          ? parseViolation((shape.meta as Record<string, unknown>).gate_violation)
          : null,
    }))
    .filter((entry) => entry.violation !== null)

  if (flagged.length === 0) return null

  return (
    <>
      {flagged.map(({ shape, violation }) => {
        const point = editor.pageToViewport({ x: shape.x, y: shape.y })
        return (
          <div
            key={`gv-${shape.id}`}
            className="pointer-events-none absolute z-20"
            style={{
              left: point.x,
              top: point.y,
              width: NOTE_W * zoom,
              height: NOTE_H * zoom,
            }}
          >
            <div className="pointer-events-auto relative h-full w-full">
              <GateViolationBadge violation={violation as GateViolationMeta} />
            </div>
          </div>
        )
      })}
    </>
  )
})

/**
 * Phase 22：當前使用者在 tldraw 上自建便利貼時，自動套用「我這個席位」的鎖定色。
 *
 * 監聽 editor.sideEffects after-create-shape，只攔截 source==='user' 且 type==='note'，
 * 把 props.color 改成我的 seat.sticky_color；同時把 meta.author 寫上以便 AuthorOverlay 顯示名字。
 */
import { useEffect } from 'react'
import { useEditor } from '@tldraw/tldraw'
import type { TLShape } from '@tldraw/tldraw'
import { useAuthStore } from '../../stores/authStore'
import { useProjectStore } from '../../stores/projectStore'

export function HumanNoteColorInjector() {
  const editor = useEditor()
  const user = useAuthStore((s) => s.user)
  const currentProject = useProjectStore((s) => s.currentProject)

  const mySeat = currentProject?.seats?.find(
    (s) => s.user_id === user?.id && s.occupant_type === 'human',
  )
  const myColor = mySeat?.sticky_color ?? null

  useEffect(() => {
    if (!editor) return
    const cleanup = editor.sideEffects.registerAfterCreateHandler(
      'shape',
      (shape: TLShape, source) => {
        if (source !== 'user') return
        if (shape.type !== 'note') return
        const props = shape.props as { color?: string }
        const meta = shape.meta as Record<string, unknown>

        const nextProps =
          myColor && props.color !== myColor ? { ...props, color: myColor } : props
        // Phase 24：補上 created_at 以支援 Activity Highlight 時間配對
        const hasAuthor =
          typeof meta.author === 'string' && (meta.author as string).length > 0
        const hasCreatedAt =
          typeof meta.created_at === 'string' && (meta.created_at as string).length > 0
        const needsAuthor = !!user && !hasAuthor
        const needsCreatedAt = !hasCreatedAt
        const nextMeta =
          needsAuthor || needsCreatedAt
            ? {
                ...meta,
                ...(needsAuthor && user
                  ? { author: `${user.display_name}(human)` }
                  : {}),
                ...(needsCreatedAt
                  ? { created_at: new Date().toISOString() }
                  : {}),
              }
            : meta

        if (nextProps !== props || nextMeta !== meta) {
          editor.updateShape({
            id: shape.id,
            type: shape.type,
            props: nextProps,
            // tldraw 對 meta 型別嚴格（JsonObject），這裡走 runtime 已知為 JSON-safe
            meta: nextMeta as unknown as Record<string, string>,
          })
        }
      },
    )
    return cleanup
  }, [editor, myColor, user])

  return null
}

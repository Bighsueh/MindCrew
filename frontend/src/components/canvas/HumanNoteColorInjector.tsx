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
        const nextMeta =
          user && !meta.author
            ? { ...meta, author: `${user.display_name}(human)` }
            : meta

        if (nextProps !== props || nextMeta !== meta) {
          editor.updateShape({
            id: shape.id,
            type: shape.type,
            props: nextProps,
            meta: nextMeta,
          })
        }
      },
    )
    return cleanup
  }, [editor, myColor, user])

  return null
}

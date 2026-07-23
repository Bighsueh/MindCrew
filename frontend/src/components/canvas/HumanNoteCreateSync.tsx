/**
 * HumanNoteCreateSync — 真人「建立」便條接線（Phase 42 C0 ⑥(b) 最小範圍）。
 *
 * 修復既存斷線：tldraw 建便條原本只存在本地瀏覽器（projectService.createNoteForcePublish
 * 是零呼叫者死碼、RejectToast 建好沒掛）。本元件把流程接通：
 *
 *   tldraw 建便條（本地草稿）→ 編輯結束 → POST /canvas/notes（content gate）
 *     ├─ 成功 → 刪本地草稿，等 sidecar 版經 Yjs 回流（A2 note 型回合鎖因此在真 UI 解鎖）
 *     └─ 被擋 → RejectToast（修改 / 丟棄 / 仍要送出 force_publish 留違規標記）
 *
 * 真人「編輯 / 刪除」既有便條的同步不在本步（C0 拍板）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useEditor } from '@tldraw/tldraw'
import { track } from '@tldraw/state-react'
import type { TLShape, TLShapeId } from '@tldraw/tldraw'
import type * as Y from 'yjs'
import { RejectToast, type RejectInfo } from './RejectToast'
import { createHumanNote, createNoteForcePublish } from '../../services/projectService'
import { useTimerStore } from '../../stores/timerStore'

// module-level：tldraw children 可能 double-render，跨實例去重避免重複 POST
const inflight = new Set<string>()

interface HumanNoteCreateSyncProps {
  projectId: string
  shapesMap: Y.Map<unknown> | null
}

// track()：讓本元件對 render 中讀到的 tldraw signal（editingShapeId）自反應——
// 否則 editingId 只在父層恰好 re-render 時更新，編輯結束事件會漏接（C0 live 實證）。
export const HumanNoteCreateSync = track(function HumanNoteCreateSync({
  projectId,
  shapesMap,
}: HumanNoteCreateSyncProps) {
  const editor = useEditor()
  const [reject, setReject] = useState<RejectInfo | null>(null)
  // 本地草稿（user 建立、sidecar 還沒有）的 shape id 集合
  const draftsRef = useRef<Set<string>>(new Set())

  // 1. 攔截 user 建立的 note：登記為本地草稿
  useEffect(() => {
    const cleanup = editor.sideEffects.registerAfterCreateHandler(
      'shape',
      (shape: TLShape, source) => {
        if (source !== 'user' || shape.type !== 'note') return
        if (shapesMap?.has(shape.id)) return
        draftsRef.current.add(shape.id)
      },
    )
    return cleanup
  }, [editor, shapesMap])

  const submit = useCallback(
    async (shapeId: string, force: boolean) => {
      const key = `${projectId}:${shapeId}:${force ? 'f' : 'n'}`
      if (inflight.has(key)) return
      const shape = editor.getShape(shapeId as TLShapeId)
      if (!shape || shape.type !== 'note') {
        draftsRef.current.delete(shapeId)
        return
      }
      const text = ((shape.props as { text?: string }).text ?? '').trim()
      if (!text) return // 空便條留在本地，等下次編輯結束再送

      // timer 未啟用時 timer 快照的 current_sub_phase 為 null——便條**仍要送出**（後端
      // 用 project 權威 current_sub_phase 補上），否則便條只留在本地、agent 永遠看不到
      // 真人貼的便條（組長一直問「貼了嗎？」）。送空字串、後端衍生即可、不會誤送 gate。
      const subPhase = useTimerStore.getState().snapshot.current_sub_phase ?? ''

      inflight.add(key)
      try {
        // color 僅為通過後端驗證的佔位；實際便條色＝作者席位鎖定色（伺服器端覆蓋）
        const payload = {
          text,
          color: 'yellow',
          x: shape.x,
          y: shape.y,
          sub_phase_id: subPhase,
        }
        const res = force
          ? await createNoteForcePublish(projectId, payload)
          : await createHumanNote(projectId, payload)
        if (res.success) {
          draftsRef.current.delete(shapeId)
          setReject(null)
          // sidecar 版便條會經 Yjs 回流；刪本地草稿避免重影
          editor.deleteShapes([shapeId as TLShapeId])
        } else if (res.rejection) {
          setReject({
            reasonZh: res.rejection.reason_zh,
            ruleModule: res.rejection.rule_module,
            ruleName: res.rejection.rule_name,
            matchedText: res.rejection.matched_text,
            draftId: shapeId,
          })
        }
      } catch (err: unknown) {
        // 網路 / 伺服器錯誤：便條留在本地，不打斷使用者
        console.warn('HumanNoteCreateSync: create note failed', err)
      } finally {
        inflight.delete(key)
      }
    },
    [editor, projectId],
  )

  // 2. 草稿編輯結束（使用者打完字點別處）→ 送出。
  // 偵測方式＝500ms 輪詢 editingShapeId。live 實測淘汰了兩個方案：
  // useValue/track（依賴 re-render 時序，第二次之後漏接）與 store.listen
  // （session scope 對 editing 變化在部分 page load 完全不觸發）。輪詢每次
  // 只讀一個 signal、無渲染負擔，行為跨 mount 一致。
  useEffect(() => {
    let prev: string | null = editor.getEditingShapeId()
    const timer = window.setInterval(() => {
      const current = editor.getEditingShapeId()
      if (current === prev) return
      const ended = prev
      prev = current
      if (ended && draftsRef.current.has(ended)) {
        void submit(ended, false)
      }
    }, 500)
    return () => window.clearInterval(timer)
  }, [editor, submit])

  return (
    <RejectToast
      info={reject}
      onEdit={(draftId) => {
        setReject(null)
        editor.setEditingShape(draftId as TLShapeId)
      }}
      onDiscard={(draftId) => {
        setReject(null)
        draftsRef.current.delete(draftId)
        editor.deleteShapes([draftId as TLShapeId])
      }}
      onForcePublish={(draftId) => {
        setReject(null)
        void submit(draftId, true)
      }}
      onDismiss={() => setReject(null)}
    />
  )
})

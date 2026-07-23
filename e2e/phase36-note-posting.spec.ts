/**
 * Phase 36 / Spec 27 v2.0 — 便條貼法模式 端到端驗收（Playwright + Chrome）。
 *
 * v2.0（A 案）：移除「概念演進線」——畫面只有便條紙一種工具。
 * 本 spec 驗證真實 app 管線（非 mock）：
 *   sidecar(Yjs) → backend canvas-state API → 前端 workspace 渲染。
 *
 * 對應 spec 27 §12 驗收：
 *   #2 同主題聚一起（group_id 全鏈路）
 *   #4 標籤便條（kind=label）
 *   #6 擺放像人（organic 落點、非網格）
 *   #11 畫面只有便條紙（資料層無 relation/derived_from_id/lineage_id；前端無演進線 Overlay）
 *
 * 行為面（#1 概念萃取 / #5 暖場 / #7-8 整理講原因 / #9 無重複 / #10 可學）
 * 由 backend 單元測試涵蓋，並於 docs/phase36-acceptance/REPORT.md 記錄 live 觀察與機制。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, createMinimalProject, apiCall } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

const SIDECAR = 'http://localhost:4000'

interface SeedNote {
  content: string
  color: string
  x?: number
  y?: number
  kind?: 'content' | 'label'
  group_id?: string | null
}

async function seedNote(projectId: string, n: SeedNote): Promise<string> {
  const body: Record<string, unknown> = {
    content: n.content,
    author: `${n.kind ?? 'content'}(ai)`,
    color: n.color,
    kind: n.kind ?? 'content',
    group_id: n.group_id ?? null,
  }
  if (n.x !== undefined && n.y !== undefined) body.position = { x: n.x, y: n.y }
  const res = await fetch(`${SIDECAR}/api/projects/${projectId}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const parsed = (await res.json()) as { id: string }
  return parsed.id
}

interface CanvasNote {
  id: string
  content: string
  kind?: string
  group_id?: string | null
  [k: string]: unknown
}

const EMAIL = `phase36_v2_${Date.now()}@e2e.test`
const PASSWORD = 'Test1234!'

test.describe('Phase 36 v2.0 — 便條貼法模式（無演進線）', () => {
  let projectId: string
  let token: string

  test.beforeAll(async () => {
    const teacher = await loginOrRegisterTeacher(EMAIL, PASSWORD, 'Phase36 v2 Teacher')
    token = teacher.token
    projectId = await createMinimalProject(token, 'Phase36 v2 接話式')
  })

  test('#2/#11 資料面：kind + group_id 全鏈路；無 relation/derived_from_id/lineage_id', async () => {
    // 顧客群 3 張沉澱概念
    await seedNote(projectId, { content: '價格太貴', color: 'orange', x: 100, y: 100, group_id: '顧客' })
    await seedNote(projectId, { content: '在意CP值，不是單純嫌貴', color: 'orange', x: 320, y: 100, group_id: '顧客' })
    await seedNote(projectId, { content: '願意為品質多付一點', color: 'orange', x: 540, y: 100, group_id: '顧客' })

    const resp = await apiCall<{ notes: CanvasNote[] }>(
      'GET', `/api/projects/${projectId}/canvas-state`, undefined, token,
    )
    expect(resp.status).toBe(200)
    const notes = resp.body.notes
    expect(notes.length).toBeGreaterThanOrEqual(3)

    const kehu = notes.filter((n) => n.group_id === '顧客')
    expect(kehu.length).toBe(3)
    for (const n of kehu) {
      expect(n.kind).toBe('content')
      // v2.0 核心：資料模型只剩 kind + group_id，無任何「連線」欄位
      expect(n).not.toHaveProperty('relation')
      expect(n).not.toHaveProperty('derived_from_id')
      expect(n).not.toHaveProperty('lineage_id')
    }
  })

  test('#4 標籤便條：kind=label 全鏈路', async () => {
    await seedNote(projectId, { content: '顧客（主題群）', color: 'blue', x: 100, y: 40, kind: 'label', group_id: '顧客' })
    const resp = await apiCall<{ notes: CanvasNote[] }>(
      'GET', `/api/projects/${projectId}/canvas-state`, undefined, token,
    )
    const label = resp.body.notes.find((n) => n.content === '顧客（主題群）')
    expect(label).toBeTruthy()
    expect(label?.kind).toBe('label')
  })

  test('#6 擺放像人：auto 落點帶 organic jitter（非整齊網格）', async () => {
    // 連續 6 張不帶座標 → sidecar auto organic 落點
    const autoPid = `${projectId}-auto`
    for (let i = 0; i < 6; i++) {
      await seedNote(autoPid, { content: `auto-${i}`, color: 'yellow', group_id: '測試' })
    }
    const res = await fetch(`${SIDECAR}/api/projects/${autoPid}/state`)
    const state = (await res.json()) as { notes: { id: string }[] }
    const full = await fetch(`${SIDECAR}/api/projects/${autoPid}/canvas-state/full`)
    const shapes = (await full.json()) as { x: number; y: number }[]
    expect(shapes.length).toBe(6)
    // organic：同一欄的 x 不應全部相同整數（jitter 讓座標有偏移）
    const xs = shapes.map((s) => Math.round(s.x))
    const uniqueXs = new Set(xs)
    expect(uniqueXs.size).toBeGreaterThan(1)
  })

  test('#11 前端：workspace 載入、無概念演進線 Overlay', async ({ page }) => {
    await suppressFirstRunModals(page)
    await loginViaUi(page, EMAIL, PASSWORD)
    await page.goto(`/projects/${projectId}/workspace`, { waitUntil: 'networkidle' })
    // 畫布（tldraw）容器已掛載（workspace 正常載入，無 build/render 崩潰）
    await expect(page.locator('.tl-container').first()).toBeAttached({ timeout: 20_000 })
    // v2.0：不得有概念演進線 SVG 疊層（ConceptEvolutionOverlay 已移除）
    const overlay = page.locator('[data-concept-evolution-overlay], .concept-evolution-line, svg.concept-evolution')
    await expect(overlay).toHaveCount(0)
    await page.screenshot({ path: 'e2e/phase36-v2-workspace.png', fullPage: true })
  })
})

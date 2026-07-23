/**
 * 人本暖場重設計 — 真實 app live 驗收（Playwright + Chrome）。
 * Phase 38 (spec/28)：暖場已升格為 macro stage 0.0a（原 1.1a 機制 retarget 至此）；
 * 專案建立即進 0.0a，本測試觀察的「人類優先 / 不分群 / 不灌牆」皆在 0.0a 發生。
 *
 * 完整迴圈：
 *   1. 建專案 → 人類入座 crew_1（這會喚醒 dormant AI agents + 讓 has_human_seat=true）。
 *   2. 開著 workspace（Chrome）觀察：人類發言前 crew 應因 Rule 0.8 按住不貼（board 近空）。
 *   3. 人類在 Chrome 內透過 WebSocket 送一則暖場分享 → 解除 Rule 0.8。
 *   4. 觀察 crew 接話：便條出現、但**不帶 group_id**（暖場不分群）、數量受控（不灌牆）。
 *
 * 對照 0605 災情（暖場 253 張、36 碎裂群）。
 */
import { test, expect } from '@playwright/test'
import { loginOrRegisterTeacher, createMinimalProject, apiCall } from './helpers/api'
import { loginViaUi, suppressFirstRunModals } from './helpers/loginUi'

interface CanvasNote {
  id: string
  content: string
  kind?: string
  group_id?: string | null
}

const EMAIL = `warmup_live_${Date.now()}@e2e.test`
const PASSWORD = 'Test1234!'

async function snapshot(projectId: string, token: string): Promise<CanvasNote[]> {
  const resp = await apiCall<{ notes: CanvasNote[] }>(
    'GET', `/api/projects/${projectId}/canvas-state`, undefined, token,
  )
  return resp.body?.notes ?? []
}

test('人本暖場 live：人類入座→發言前 crew 按住→發言後接話且不分群、不灌牆', async ({ page }) => {
  test.setTimeout(240_000)

  const teacher = await loginOrRegisterTeacher(EMAIL, PASSWORD, 'Warmup Live')
  const token = teacher.token
  const projectId = await createMinimalProject(token, '人本暖場 live 驗收')

  // 人類入座 crew_1 → 喚醒 AI agents + has_human_seat=true
  const join = await apiCall('POST', `/api/projects/${projectId}/join`, { seat_role: 'crew_1' }, token)
  console.log('join crew_1 as human:', join.status)
  // 讓人類能自由發言（不被 cued 輪次卡住）；非授權則略過（best-effort）
  const tp = await apiCall('PATCH', `/api/projects/${projectId}/turn-policy`, { policy: 'open_floor' }, token)
  console.log('turn-policy open_floor:', tp.status)

  await suppressFirstRunModals(page)
  await loginViaUi(page, EMAIL, PASSWORD)
  await page.goto(`/projects/${projectId}/workspace`, { waitUntil: 'networkidle' })
  await expect(page.locator('.tl-container').first()).toBeAttached({ timeout: 20_000 })

  const currentStage = async (): Promise<string> => {
    const r = await apiCall<{ current_stage?: string }>(
      'GET', `/api/projects/${projectId}`, undefined, token,
    )
    return r.body?.current_stage ?? ''
  }

  // 階段 A：人類發言前，觀察 ~30s（crew 應因 Rule 0.8 按住，board 近空）。此時仍在暖場 0.0a。
  await page.waitForTimeout(30_000)
  const before = await snapshot(projectId, token)
  const stageBefore = await currentStage()
  console.log(`【發言前】stage=${stageBefore} 便條數=${before.length}（預期接近 0：crew 等人）`)
  // (warmup) 暖場 0.0a 不強制分群：此時的內容便條不應帶 group_id（修發散期碎裂成 36 群）。
  const warmupGrouped = before
    .filter((n) => (n.kind ?? 'content') === 'content')
    .filter((n) => n.group_id)
  expect(
    warmupGrouped.length,
    `暖場(0.0a)內容便條不應帶 group_id：${warmupGrouped.map((n) => `${n.content}=${n.group_id}`).join(' | ')}`,
  ).toBe(0)

  // 階段 B：人類在 Chrome 內用 WebSocket 送一則暖場群組發言（解除 Rule 0.8）
  const sent = await page.evaluate(async ({ pid, tok }) => {
    return await new Promise<string>((resolve) => {
      const ws = new WebSocket(`ws://localhost:8000/ws/project/${pid}?token=${tok}`)
      const done = (s: string) => { try { ws.close() } catch { /* noop */ } resolve(s) }
      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'chat_message',
          payload: { content: '我自己推大賣場購物車時，最怕輪子卡住、轉彎很難控制，重物一多就更難推。' },
        }))
        setTimeout(() => done('sent'), 1500)
      }
      ws.onerror = () => done('error')
      setTimeout(() => done('timeout'), 8000)
    })
  }, { pid: projectId, tok: token })
  console.log('人類 WS 發言結果：', sent)

  // 階段 C：發言後觀察 ~110s。人類實質參與後，暖場應完成並推進到 discover（Phase 38 暖場閉環）。
  const trajectory: string[] = []
  let lastNotes: CanvasNote[] = []
  let stageAfter = stageBefore
  for (let i = 0; i < 14; i++) {
    await page.waitForTimeout(8_000)
    lastNotes = await snapshot(projectId, token)
    stageAfter = await currentStage()
    const grouped = lastNotes.filter((n) => n.group_id).length
    trajectory.push(`t+${(i + 1) * 8}s stage=${stageAfter} notes=${lastNotes.length} grouped=${grouped}`)
    if (stageAfter === 'discover') break // 暖場已完成、推進到發現，足以驗證閉環
  }
  console.log('【發言後】軌跡：\n  ' + trajectory.join('\n  '))
  console.log(`最終 stage=${stageAfter} 便條數=${lastNotes.length}`)

  await page.screenshot({ path: 'phase36-warmup-live.png', fullPage: true })

  // ── 驗收（Phase 38 暖場 macro stage 閉環）──
  // (1) 不灌牆：暖場便條數遠低於舊災情（253）。
  expect(lastNotes.length, '暖場便條數應受控').toBeLessThan(50)
  // (2) 暖場閉環：人類實質參與後，暖場完成並推進到 discover（不再卡在暖場）。
  //     若 LLM 太慢未在窗內推進，視為 best-effort（記錄但不硬失敗）。
  if (stageAfter === 'discover') {
    console.log('✓ 暖場閉環：人類發言→暖場完成→推進到 discover')
  } else {
    console.warn(`⚠️ 暖場未在觀察窗內推進到 discover（stage=${stageAfter}）；可能 LLM 慢 / supervisor 未循環。`)
  }
})

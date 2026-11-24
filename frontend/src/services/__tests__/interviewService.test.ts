import { randomFillSync } from 'node:crypto'
import { afterEach, expect, it, vi } from 'vitest'
import { interviewRequestId } from '../interviewService'

vi.mock('../api', () => ({ default: {} }))

afterEach(() => {
  vi.unstubAllGlobals()
})

it('creates a UUID v4 when HTTP exposes getRandomValues but not randomUUID', () => {
  vi.stubGlobal('crypto', { getRandomValues: (bytes: Uint8Array) => randomFillSync(bytes) })

  const id = interviewRequestId()
  expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  expect(interviewRequestId()).not.toBe(id)
})

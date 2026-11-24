import { expect, it } from 'vitest'
import { displayPersonaName, mergeDefinitions, searchDefinitions } from '../personaNames'

it('ranks exact names before partial names and aliases across languages', () => {
  const occupation = { label: '職業／身分', name_en: 'Occupation / Role', aliases: ['工作', 'job'] }
  const exact = { label: '工作' }
  const partial = { label: '工作時間' }
  expect(searchDefinitions([occupation, partial, exact], '工作')).toEqual([exact, partial, occupation])
  expect(searchDefinitions([occupation], 'ＪＯＢ')).toEqual([occupation])
  expect(searchDefinitions([occupation], 'occup')).toEqual([occupation])
})

it('uses the current interface language, falling back to the original name', () => {
  const field = { label: '原名稱', name_zh: '中文', name_en: 'English' }
  expect(displayPersonaName(field, 'zh-Hant')).toBe('中文')
  expect(displayPersonaName(field, 'en-GB')).toBe('English')
  expect(displayPersonaName({ ...field, name_en: null }, 'en')).toBe('原名稱')
  expect(field).toEqual({ label: '原名稱', name_zh: '中文', name_en: 'English' })
})

it('retains searchable default aliases when a legacy definition has the same stable ID', () => {
  const base = { id: 'occupation', label: '職業', name_en: 'Occupation', aliases: ['job'] }
  const legacy = { id: 'occupation', label: '職業／身分', aliases: [] }
  const [item] = mergeDefinitions([base, legacy], value => value.id)
  expect(searchDefinitions([item], 'job')).toEqual([item])
  expect(item.id).toBe('occupation')
})

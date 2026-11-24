import { useSyncExternalStore } from 'react'

export interface DefinitionName {
  label: string
  name_zh?: string | null
  name_en?: string | null
  aliases?: string[]
}

export const normalizeName = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[\s\p{P}]+/gu, '')

export function displayPersonaName(item: DefinitionName, locale: string) {
  return (/^en(?:-|$)/i.test(locale) ? item.name_en : item.name_zh) || item.label
}

const readLocale = () => document.documentElement.lang || 'zh-Hant'
function watchLocale(listener: () => void) {
  const observer = new MutationObserver(listener)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] })
  return () => observer.disconnect()
}

export function useInterfaceLocale() {
  return useSyncExternalStore(watchLocale, readLocale, () => 'zh-Hant')
}

export function searchDefinitions<T extends DefinitionName>(items: T[], text: string): T[] {
  const query = normalizeName(text)
  if (!query) return []
  return items.flatMap(item => {
    const names = [item.label, item.name_zh, item.name_en].map(name => normalizeName(name ?? ''))
    const rank = names.includes(query) ? 0
      : names.some(name => name.includes(query)) ? 1
      : item.aliases?.some(alias => normalizeName(alias).includes(query)) ? 2 : -1
    return rank < 0 ? [] : [{ item, rank }]
  }).sort((a, b) => a.rank - b.rank).map(({ item }) => item)
}

export function parseAliases(value: string) {
  return [...new Set(value.split(/[,，]/u).map(alias => alias.trim()).filter(Boolean))]
}


export function mergeAliases(original: DefinitionName | undefined, item: DefinitionName) {
  return [...new Set([...(item.aliases ?? []), ...(original?.aliases ?? [])])].slice(0, 24)
}

export function mergeDefinitions<T extends DefinitionName>(items: T[], id: (item: T) => string): T[] {
  const result = new Map<string, T>()
  for (const item of items) {
    const prior = result.get(id(item))
    result.set(id(item), {
      ...item,
      name_zh: item.name_zh ?? prior?.name_zh,
      name_en: item.name_en ?? prior?.name_en,
      aliases: mergeAliases(prior, item),
    })
  }
  return [...result.values()]
}

import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  interviewError, interviewRequestId, interviewService,
  type Interview, type InterviewSummary, type PersonaCatalog,
  type PersonaDraft, type PersonaField, type PersonaGroup, type SourceRef,
} from '../../services/interviewService'
import { displayPersonaName, mergeAliases, mergeDefinitions, normalizeName, parseAliases, searchDefinitions, useInterfaceLocale, type DefinitionName } from './personaNames'
import { dateFormat, input, panel, primary, secondary } from './styles'

const types = { short: '短文字', long: '長文字', list: '清單' } as const
const sourceKey = (ref: SourceRef) => `${ref.session_id}:${ref.sequence}:${ref.speaker}`

function sessionLabel(session: InterviewSummary) {
  return `${session.scenario.title} · ${session.stakeholder.name} · ${dateFormat.format(new Date(session.started_at))}`
}

export function PersonaWorkspace({ sessions }: { sessions: InterviewSummary[] }) {
  const [catalog, setCatalog] = useState<PersonaCatalog>()
  const [draft, setDraft] = useState<PersonaDraft>()
  const [personaId, setPersonaId] = useState('')
  const [pending, setPending] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [load, setLoad] = useState(0)
  const [label, setLabel] = useState('')
  const [type, setType] = useState<PersonaField['type']>('short')
  const [sourceSession, setSourceSession] = useState('')
  const [selectedRef, setSelectedRef] = useState<string>()
  const [targetField, setTargetField] = useState('')
  const locale = useInterfaceLocale()
  const [editingField, setEditingField] = useState('')
  const [editingGroup, setEditingGroup] = useState('')
  const [addGroupId, setAddGroupId] = useState('')
  const [groupName, setGroupName] = useState('')
  const [focused, setFocused] = useState('')
  const [showSources, setShowSources] = useState(false)

  const displayName = (item: DefinitionName) => displayPersonaName(item, locale)

  function focusField(id: string) {
    setFocused(id)
    const target = document.getElementById(`persona-value-${id}`)
    const section = target?.closest('details')
    if (section) section.open = true
    target?.focus()
  }

  useEffect(() => {
    if (!focused) return
    const target = document.getElementById(`persona-value-${focused}`)
    const section = target?.closest('details')
    if (section) section.open = true
    target?.focus()
  }, [focused])

  useEffect(() => {
    if (!editingGroup) return
    const section = document.getElementById(`persona-group-${editingGroup}`)
    if (section instanceof HTMLDetailsElement) section.open = true
    section?.querySelector<HTMLInputElement>('[data-definition-name]')?.focus()
  }, [editingGroup])

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.personas(controller.signal).then(next => {
      if (!controller.signal.aborted) setCatalog(next)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [load])

  function edit(next: PersonaDraft) {
    setDraft(next)
    setDirty(true)
    setNotice('')
  }

  function updateField(id: string, patch: Partial<PersonaField>) {
    if (!draft) return
    edit({ ...draft, fields: draft.fields.map(field => field.field_id === id ? { ...field, ...patch } : field) })
  }

  async function open(id: string) {
    if (!catalog || pending) return
    if (dirty && !window.confirm('這份 Persona 有未儲存變更。確定要切換嗎？')) return
    setError('')
    setNotice('')
    setEditingField('')
    setEditingGroup('')
    setAddGroupId('')
    setFocused('')
    if (!id) {
      setDraft({ title: '', groups: catalog.groups.map(({ fields: _, ...group }) => group), fields: catalog.groups.flatMap(group => group.fields) })
      setPersonaId('')
      setTargetField('')
      setDirty(false)
      return
    }
    setPending(true)
    try {
      const next = await interviewService.persona(id)
      const defaultGroups = catalog.groups.map(({ fields: _, ...group }) => group)
      const groups = next.groups?.map(group => {
        const original = defaultGroups.find(item => item.id === group.id)
        return { ...group, aliases: mergeAliases(original, group), name_en: group.name_en ?? original?.name_en }
      }) ?? defaultGroups
      const defaults = new Map(catalog.groups.flatMap(group => group.fields.map(field => [field.field_id, field] as const)))
      const groupIds = new Set(groups.map(group => group.id))
      const groupFor = (field: PersonaField) => {
        const groupId = field.group_id ?? defaults.get(field.field_id)?.group_id
        return groupId && groupIds.has(groupId) ? groupId : 'custom'
      }
      const needsCustomGroup = !groupIds.has('custom') && next.fields.some(field => groupFor(field) === 'custom')
      const allGroups = needsCustomGroup ? [...groups, { id: 'custom', label: '自訂欄位', name_en: 'Custom fields' }] : groups
      setDraft({
        ...next, groups: allGroups, fields: next.fields.map(field => ({
          ...field,
          name_zh: field.name_zh ?? defaults.get(field.field_id)?.name_zh,
          name_en: field.name_en ?? defaults.get(field.field_id)?.name_en,
          aliases: mergeAliases(defaults.get(field.field_id), field),
          group_id: groupFor(field),
        })),
      })
      setPersonaId(next.id)
      setTargetField('')
      setDirty(false)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setPending(false)
    }
  }

  async function save() {
    if (!draft?.title.trim() || pending) return
    setPending(true)
    setError('')
    try {
      const next = await interviewService.savePersona({ title: draft.title, fields: draft.fields, groups: draft.groups }, personaId || undefined)
      setPersonaId(next.id)
      setDraft(next)
      setDirty(false)
      setNotice('Persona 已儲存。')
      setCatalog(current => current && {
        ...current,
        definitions: [...next.fields, ...current.definitions.filter(field => !next.fields.some(item => item.field_id === field.field_id))]
          .map(field => ({ ...field, value: field.type === 'list' ? [] : '', source_refs: [] })),
        personas: [next, ...current.personas.filter(item => item.id !== next.id)],
      })
      setLoad(value => value + 1)
    } catch (err) {
      setError(interviewError(err))
    } finally {
      setPending(false)
    }
  }

  const groups: PersonaGroup[] = draft?.groups ?? []
  const target = draft?.fields.find(field => field.field_id === targetField)
  const choices = mergeDefinitions([
    ...catalog?.groups.flatMap(group => group.fields) ?? [],
    ...catalog?.definitions ?? [],
    ...draft?.fields ?? [],
  ], field => field.field_id)
  const groupChoices = mergeDefinitions([
    ...catalog?.groups.map(({ fields: _, ...group }) => group) ?? [],
    ...catalog?.group_definitions ?? [],
    ...groups,
  ], group => group.id)
  const suggestions = searchDefinitions(choices, label).slice(0, 8)
  const groupSuggestions = searchDefinitions(groupChoices, groupName).slice(0, 8)
  const exact = (items: DefinitionName[], text: string) => items.some(item =>
    [item.label, item.name_zh, item.name_en, ...item.aliases ?? []].some(name =>
      normalizeName(name ?? '') === normalizeName(text)))

  function addField(definition?: PersonaField) {
    if (!draft || (!definition && (!normalizeName(label) || exact(choices, label)))) return
    const field: PersonaField = {
      field_id: definition?.field_id ?? interviewRequestId(),
      label: definition?.label ?? label.trim(),
      name_zh: definition?.name_zh, name_en: definition?.name_en, aliases: definition?.aliases,
      group_id: addGroupId, type: definition?.type ?? type,
      value: (definition?.type ?? type) === 'list' ? [] : '', source_refs: [],
    }
    if (draft.fields.some(item => item.field_id === field.field_id)) {
      setAddGroupId('')
      focusField(field.field_id)
      return
    }
    if (draft.fields.length >= 64) return
    edit({ ...draft, fields: [...draft.fields, field] })
    setLabel('')
    setAddGroupId('')
    focusField(field.field_id)
  }

  function addGroup(definition?: PersonaGroup) {
    if (!draft || (!definition && (!normalizeName(groupName) || exact(groupChoices, groupName)))) return
    const group = definition ?? { id: interviewRequestId(), label: groupName.trim() }
    if (!groups.some(item => item.id === group.id)) {
      if (groups.length >= 64) return
      edit({ ...draft, groups: [...groups, group] })
    }
    setEditingGroup(group.id)
    setGroupName('')
  }

  function move(id: string, offset: number, groupId?: string | null) {
    if (!draft) return
    if (!groupId) {
      const index = groups.findIndex(group => group.id === id)
      if (!groups[index + offset]) return
      const ordered = [...groups]
      ;[ordered[index], ordered[index + offset]] = [ordered[index + offset], ordered[index]]
      edit({ ...draft, groups: ordered })
      return
    }
    const peers = draft.fields.filter(field => field.group_id === groupId)
    const neighbor = peers[peers.findIndex(field => field.field_id === id) + offset]
    if (!neighbor) return
    const fields = [...draft.fields]
    const from = fields.findIndex(field => field.field_id === id)
    const to = fields.indexOf(neighbor)
    ;[fields[from], fields[to]] = [fields[to], fields[from]]
    edit({ ...draft, fields })
  }

  function remove(field: PersonaField) {
    if (!draft) return
    const filled = Array.isArray(field.value) ? field.value.some(value => value.trim()) : Boolean(field.value.trim())
    if ((filled || field.source_refs.length) && !window.confirm(`移除「${field.label}」及其內容和引用？`)) return
    edit({ ...draft, fields: draft.fields.filter(item => item.field_id !== field.field_id) })
    if (targetField === field.field_id) setTargetField('')
  }

  function renderField(field: PersonaField) {
    const text = Array.isArray(field.value) ? field.value.join('\n') : field.value
    return (
      <div key={field.field_id} className="grid min-w-0 gap-2 border-t border-border px-3 py-2 sm:grid-cols-[minmax(8rem,1fr)_minmax(0,2fr)] sm:gap-3">
        <div className="min-w-0 space-y-2">
          <button type="button" className="break-words text-left text-sm font-medium text-text hover:underline"
            aria-label={`編輯欄位名稱 ${displayName(field)}`} aria-expanded={editingField === field.field_id}
            onClick={() => setEditingField(editingField === field.field_id ? '' : field.field_id)}>
            {displayName(field)}
          </button>
          {editingField === field.field_id && <DefinitionEditor item={field} choices={choices.filter(item => item.field_id !== field.field_id)}
            locale={locale} onApply={name => { updateField(field.field_id, name); setEditingField(''); focusField(field.field_id) }} />}
        </div>
        <div className="min-w-0 space-y-2">
          <label className="block text-sm text-text">
            <span className="sr-only">{displayName(field)}{field.type === 'list' && '（每行一項）'}</span>
            {field.type === 'short'
              ? <input id={`persona-value-${field.field_id}`} onFocus={() => {
                  setTargetField(field.field_id)
                }} className={input} maxLength={280} value={text} onChange={event => updateField(field.field_id, { value: event.target.value })} />
              : <textarea id={`persona-value-${field.field_id}`} onFocus={() => {
                  setTargetField(field.field_id)
                }} rows={3} className={input} maxLength={12000} value={text}
                  placeholder={field.type === 'list' ? '每行一項' : undefined}
                  onChange={event => updateField(field.field_id, { value: field.type === 'list' ? event.target.value.split('\n', 101) : event.target.value })} />}
          </label>
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer">欄位操作</summary>
            <div className="flex flex-wrap items-end gap-2 pt-2">
              <label>所屬群組
                <select className={input} value={field.group_id ?? ''} onChange={event => updateField(field.field_id, { group_id: event.target.value })}>
                  {groups.map(group => <option key={group.id} value={group.id}>{displayName(group)}</option>)}
                </select>
              </label>
              <button type="button" className={secondary} onClick={() => move(field.field_id, -1, field.group_id)}>上移</button>
              <button type="button" className={secondary} onClick={() => move(field.field_id, 1, field.group_id)}>下移</button>
              <button type="button" className={secondary} onClick={() => remove(field)}>移除此欄位</button>
            </div>
          </details>
          {field.source_refs.length > 0 && <ul className="space-y-2">
            {field.source_refs.map(ref => {
              const session = sessions.find(item => item.id === ref.session_id)
              const key = sourceKey(ref)
              return <li key={key} className="flex flex-wrap items-center gap-2 text-sm">
                <button type="button" className={secondary} onClick={() => {
                  setShowSources(true)
                  setSourceSession(ref.session_id)
                  setSelectedRef(key)
                  setTargetField(field.field_id)
                  document.getElementById('persona-interview-source')?.scrollIntoView({ block: 'nearest' })
                }}>{session?.scenario.title ?? '訪談'} · 第 {ref.sequence} 題 · {ref.speaker === 'student' ? '提問' : '回答'}</button>
                <button type="button" className={secondary} aria-label={`移除第 ${ref.sequence} 題的引用`} onClick={() => updateField(field.field_id, {
                  source_refs: field.source_refs.filter(item => sourceKey(item) !== key),
                })}>移除引用</button>
              </li>
            })}
          </ul>}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <section className={cn(panel, 'space-y-3 p-4')}>
        <h2 className="text-xl font-semibold text-text">我的 Persona</h2>
        {error && !draft && <p role="alert" className="text-sm text-error">{error}</p>}
        {catalog ? (
          <div className="flex flex-wrap items-end gap-3">
            <button type="button" className={primary} disabled={pending} onClick={() => void open('')}>建立空白 Persona</button>
            <label className="min-w-48 text-sm text-text">開啟已儲存 Persona
              <select className={input} value={personaId} disabled={pending || !catalog.personas.length} onChange={event => void open(event.target.value)}>
                {!personaId && <option value="" disabled>選擇 Persona</option>}
                {catalog.personas.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
              </select>
            </label>
          </div>
        ) : error
          ? <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入</button>
          : <p role="status" className="text-sm text-text-muted">載入 Persona 清單中…</p>}
      </section>

      {draft && (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
          <form className={cn(panel, 'min-w-0 p-4')} onSubmit={event => { event.preventDefault(); void save() }}>
            <fieldset className="space-y-5" disabled={pending}>
              <label className="block text-sm font-semibold text-text">Persona 標題
                <input className={cn(input, 'min-h-14 text-2xl font-semibold')} placeholder="例如：通勤型學習者" required value={draft.title} maxLength={120} onChange={event => edit({ ...draft, title: event.target.value })} />
              </label>
              {groups.map((group, index) => (
                <section key={group.id} className="relative rounded-lg border border-border">
                  <details id={`persona-group-${group.id}`} open>
                    <summary className="cursor-pointer break-words py-3 pl-3 pr-24 text-lg font-semibold text-text">{displayName(group)}</summary>
                    <div className="space-y-2">
                      <div className="px-3">
                        <button type="button" className="text-sm text-text-muted hover:underline"
                          aria-expanded={editingGroup === group.id}
                          onClick={() => setEditingGroup(editingGroup === group.id ? '' : group.id)}>編輯群組名稱</button>
                        {editingGroup === group.id && <DefinitionEditor item={group} choices={groupChoices.filter(item => item.id !== group.id)}
                          locale={locale} onApply={name => {
                            edit({ ...draft, groups: groups.map(item => item.id === group.id ? { ...item, ...name } : item) })
                            setEditingGroup('')
                          }} />}
                      </div>
                      <div aria-hidden="true" className="hidden grid-cols-[minmax(8rem,1fr)_minmax(0,2fr)] gap-3 bg-bg px-3 py-2 text-sm font-medium text-text-muted sm:grid">
                        <span>欄位名稱</span><span>內容</span>
                      </div>
                      {draft.fields.filter(field => field.group_id === group.id).map(renderField)}
                      <div className="space-y-2 border-t border-border p-3">
                        <button type="button" className={secondary} onClick={() => { setAddGroupId(addGroupId === group.id ? '' : group.id); setLabel('') }}>＋ 新增欄位</button>
                        {addGroupId === group.id && <div className="space-y-2">
                          <label className="block text-sm">搜尋或建立欄位
                            <input autoFocus className={input} maxLength={120} value={label} onChange={event => setLabel(event.target.value)} onKeyDown={stopEnter} />
                          </label>
                          <ul className="space-y-1">
                            {suggestions.map(field => <li key={field.field_id}>
                              <button type="button" className={secondary} onClick={() => addField(field)}>{displayName(field)}{draft.fields.some(item => item.field_id === field.field_id) ? '（已使用）' : ''}</button>
                            </li>)}
                          </ul>
                          {normalizeName(label) && !exact(choices, label) && <>
                            <select aria-label="新欄位型別" className={input} value={type} onChange={event => setType(event.target.value as PersonaField['type'])}>
                              <option value="short">{types.short}</option><option value="long">{types.long}</option><option value="list">{types.list}</option>
                            </select>
                            <button type="button" className={secondary} onClick={() => addField()}>＋ 建立新欄位：{label.trim()}</button>
                          </>}
                        </div>}
                      </div>
                    </div>
                  </details>
                  <div className="absolute right-3 top-2 flex gap-1">
                    <button type="button" className={secondary} disabled={!index} aria-label="群組上移" title="群組上移" onClick={() => move(group.id, -1)}><ArrowUp size={16} /></button>
                    <button type="button" className={secondary} disabled={index === groups.length - 1} aria-label="群組下移" title="群組下移" onClick={() => move(group.id, 1)}><ArrowDown size={16} /></button>
                  </div>
                </section>
              ))}
              <div className="space-y-2">
                <label className="block text-sm">搜尋或建立群組
                  <input className={input} maxLength={120} value={groupName} onChange={event => setGroupName(event.target.value)} onKeyDown={stopEnter} />
                </label>
                {groupSuggestions.map(group => <button key={group.id} type="button" className={secondary} onClick={() => addGroup(group)}>{displayName(group)}</button>)}
                {normalizeName(groupName) && !exact(groupChoices, groupName) && <button type="button" className={secondary} onClick={() => addGroup()}>＋ 建立群組：{groupName.trim()}</button>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button type="submit" className={primary} disabled={!draft.title.trim()}>{pending ? '處理中…' : '儲存 Persona'}</button>
                <span role="status" className="text-sm text-text-muted">{dirty ? '有未儲存變更' : notice}</span>
              </div>
            </fieldset>
            {error && <p role="alert" className="mt-2 text-sm text-error">{error}</p>}
          </form>
          <section id="persona-interview-source" className={cn(panel, 'min-w-0 space-y-3 p-4 lg:sticky lg:top-24')}>
            <button type="button" aria-expanded={showSources} className={secondary} onClick={() => setShowSources(!showSources)}>參考訪談原文</button>
            {showSources && <>
            <label className="block text-sm text-text">訪談場次
              <select className={input} value={sourceSession} disabled={!sessions.length} onChange={event => { setSourceSession(event.target.value); setSelectedRef(undefined) }}>
                <option value="">{sessions.length ? '選擇自己的訪談' : '尚無訪談場次'}</option>
                {sessions.map(session => <option key={session.id} value={session.id}>{sessionLabel(session)}</option>)}
              </select>
            </label>
            {sourceSession && <>
              <label className="block text-sm text-text">引用到欄位
                <select className={input} value={targetField} disabled={pending} onChange={event => setTargetField(event.target.value)}>
                  <option value="">選擇要連結的欄位</option>
                  {draft.fields.map(field => <option key={field.field_id} value={field.field_id}>{displayName(field)}</option>)}
                </select>
              </label>
              <SourceTranscript key={sourceSession} id={sourceSession} selectedRef={selectedRef} target={target}
                disabled={pending}
                onAttach={ref => {
                  if (target && !target.source_refs.some(item => sourceKey(item) === sourceKey(ref))) {
                    updateField(target.field_id, { source_refs: [...target.source_refs, ref] })
                  }
                }}
              />
            </>}
            </>}
          </section>
        </div>
      )}
    </div>
  )
}

function stopEnter(event: React.KeyboardEvent<HTMLInputElement>) {
  if (event.key === 'Enter' && !event.nativeEvent.isComposing) event.preventDefault()
}

function DefinitionEditor({ item, choices, locale, onApply }: {
  item: DefinitionName
  choices: DefinitionName[]
  locale: string
  onApply: (name: DefinitionName) => void
}) {
  const [label, setLabel] = useState(item.label)
  const [search, setSearch] = useState(false)
  const [zh, setZh] = useState(item.name_zh ?? '')
  const [en, setEn] = useState(item.name_en ?? '')
  const [aliases, setAliases] = useState(item.aliases?.join('，') ?? '')
  const parsedAliases = parseAliases(aliases)
  const aliasesInvalid = parsedAliases.length > 24 || parsedAliases.some(alias => [...alias].length > 120)
  return (
    <div className="space-y-2 rounded border border-border p-2">
      <label className="block text-sm">名稱
        <input autoFocus data-definition-name className={input} maxLength={120} value={label} onKeyDown={stopEnter}
          onChange={event => { setLabel(event.target.value); setSearch(true) }} />
      </label>
      {search && searchDefinitions(choices, label).slice(0, 8).map((definition, index) => (
        <button key={index} type="button" className={secondary} onClick={() => onApply({
          label: definition.label, name_zh: definition.name_zh ?? null,
          name_en: definition.name_en ?? null, aliases: definition.aliases ?? [],
        })}>{displayPersonaName(definition, locale)}</button>
      ))}
      <details className="space-y-2 text-sm">
        <summary className="cursor-pointer">進階名稱設定</summary>
        <label className="block">中文名稱<input className={input} maxLength={120} value={zh} onKeyDown={stopEnter} onChange={event => setZh(event.target.value)} /></label>
        <label className="block">英文名稱<input className={input} maxLength={120} value={en} onKeyDown={stopEnter} onChange={event => setEn(event.target.value)} /></label>
        <label className="block">搜尋別名（逗號分隔）<input className={input} maxLength={2900} value={aliases} onKeyDown={stopEnter} onChange={event => setAliases(event.target.value)} /></label>
      </details>
      {aliasesInvalid && <p role="alert" className="text-xs text-error">最多 24 個別名，每個最多 120 字。</p>}
      <button type="button" className={secondary} disabled={!normalizeName(label) || aliasesInvalid} onClick={() => onApply({
        label: label.trim(),
        name_zh: (zh !== (item.name_zh ?? '') ? zh : item.name_zh === item.label ? label : zh).trim() || null,
        name_en: (en !== (item.name_en ?? '') ? en : item.name_en === item.label ? label : en).trim() || null,
        aliases: parsedAliases,
      })}>套用名稱</button>
    </div>
  )
}

function SourceTranscript({ id, selectedRef, target, disabled, onAttach }: {
  id: string
  selectedRef?: string
  target?: PersonaField
  disabled: boolean
  onAttach: (ref: SourceRef) => void
}) {
  const [session, setSession] = useState<Interview>()
  const [error, setError] = useState('')
  const [load, setLoad] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void interviewService.get(id, controller.signal).then(next => {
      if (!controller.signal.aborted) setSession(next)
    }).catch(err => {
      if (!controller.signal.aborted) setError(interviewError(err))
    })
    return () => controller.abort()
  }, [id, load])

  useEffect(() => {
    if (selectedRef && session) document.getElementById(`persona-source-${selectedRef}`)?.scrollIntoView({ block: 'nearest' })
  }, [selectedRef, session])

  function message(sequence: number, speaker: SourceRef['speaker'], text: string) {
    const ref = { session_id: id, sequence, speaker }
    const key = sourceKey(ref)
    const attached = target?.source_refs.some(item => sourceKey(item) === key)
    return (
      <div id={`persona-source-${key}`} className={cn('space-y-2 rounded-lg border p-2', selectedRef === key ? 'border-primary bg-primary/10' : 'border-border')}>
        <p className="text-xs font-medium text-text-muted">第 {sequence} 題 · {speaker === 'student' ? '訪談者' : session?.stakeholder.name}</p>
        <p className="whitespace-pre-wrap break-words text-sm text-text">{text}</p>
        <button type="button" className={secondary} disabled={disabled || !target || attached || target.source_refs.length >= 80} onClick={() => onAttach(ref)}>
          {attached ? '已引用' : '加入 Persona 欄位的參考證據'}
        </button>
      </div>
    )
  }

  if (error) return <div className="space-y-2"><p role="alert" className="text-sm text-error">{error}</p>
    <button type="button" className={secondary} onClick={() => { setError(''); setLoad(value => value + 1) }}>重新載入原文</button>
  </div>
  if (!session) return <p role="status" className="text-sm text-text-muted">載入原文中…</p>
  return (
    <div className="max-h-[55vh] space-y-3 overflow-auto">
      {!session.exchanges.length && <p className="text-sm text-text-muted">這場訪談尚無訊息。</p>}
      {session.exchanges.map(exchange => (
        <div key={exchange.id} className="space-y-2">
          {message(exchange.sequence, 'student', exchange.question)}
          {exchange.answer !== null && message(exchange.sequence, 'stakeholder', exchange.answer)}
        </div>
      ))}
    </div>
  )
}

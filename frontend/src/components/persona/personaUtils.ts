import type { Persona } from '../../types/models'

export function emptyPersona(): Persona {
  return {
    name: '',
    // Phase 22：UI 已不再讓使用者編輯 role，但後端 schema 仍要 min_length=1。
    // 給一個安全的預設值，避免「手動新增」persona 時送出空 role 觸發 422。
    role: '成員',
    expertise: '',
    personality_axis: 'balanced',
    personality_desc: '',
    backstory: '',
    lens_affinities: {
      empathy: 0.5,
      structure: 0.5,
      creativity: 0.5,
      feasibility: 0.5,
    },
  }
}

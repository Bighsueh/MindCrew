import type { Persona } from '../../types/models'

export function emptyPersona(): Persona {
  return {
    name: '',
    role: '',
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

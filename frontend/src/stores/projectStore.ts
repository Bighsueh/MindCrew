import { create } from 'zustand'
import type { Project, ProjectListItem } from '../types/models'
import { listProjects, getProject, deleteProject as deleteProjectApi } from '../services/projectService'

interface ProjectState {
  projects: ProjectListItem[]
  currentProject: Project | null
  isLoading: boolean
  error: string | null

  fetchProjects: () => Promise<void>
  fetchProject: (id: string) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  setCurrentProject: (project: Project | null) => void
  updateCurrentProject: (updates: Partial<Project>) => void
  clearError: () => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  error: null,

  fetchProjects: async () => {
    set({ isLoading: true, error: null })
    try {
      const projects = await listProjects()
      set({ projects, isLoading: false })
    } catch {
      set({ error: '載入專案列表失敗', isLoading: false })
    }
  },

  fetchProject: async (id: string) => {
    set({ isLoading: true, error: null })
    try {
      const project = await getProject(id)
      set({ currentProject: project, isLoading: false })
    } catch {
      set({ error: '載入專案失敗', isLoading: false })
    }
  },

  deleteProject: async (id: string) => {
    await deleteProjectApi(id)
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== id),
    }))
  },

  setCurrentProject: (project: Project | null) => {
    set({ currentProject: project })
  },

  updateCurrentProject: (updates: Partial<Project>) => {
    set((state) => ({
      currentProject: state.currentProject
        ? { ...state.currentProject, ...updates }
        : null,
    }))
  },

  clearError: () => set({ error: null }),
}))

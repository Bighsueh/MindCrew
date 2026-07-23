import { create } from 'zustand'
import type { Project, ProjectListItem, TurnPolicy, TurnState } from '../types/models'
import type { RoomPauseReason } from '../types/ws'
import {
  listProjects,
  getProject,
  deleteProject as deleteProjectApi,
  updateTurnPolicy as updateTurnPolicyApi,
} from '../services/projectService'

interface ProjectState {
  projects: ProjectListItem[]
  currentProject: Project | null
  isLoading: boolean
  error: string | null
  /** 最近一次 fetchProject 失敗的 HTTP 狀態碼（403/404/…）；成功為 null。 */
  errorStatus: number | null
  /** Phase 28：當前回合狀態 (由 WS turn_state event 推送，RR 模式下最有意義)。 */
  turnState: TurnState | null
  /** Phase 42 D5：全房暫停原因（room_paused/room_resumed WS 事件驅動）；null＝未暫停。 */
  roomPauseReason: RoomPauseReason | null

  fetchProjects: () => Promise<void>
  fetchProject: (id: string) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  setCurrentProject: (project: Project | null) => void
  updateCurrentProject: (updates: Partial<Project>) => void
  /** Phase 28：教師 / admin 觸發 PATCH 切換 turn_policy。 */
  setTurnPolicy: (projectId: string, policy: TurnPolicy) => Promise<void>
  setTurnState: (state: TurnState | null) => void
  /** Phase 42 D5：LLM fail-stop 全房暫停／恢復。 */
  setRoomPaused: (reason: RoomPauseReason) => void
  setRoomResumed: () => void
  clearError: () => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  error: null,
  errorStatus: null,
  turnState: null,
  roomPauseReason: null,

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
    set({ isLoading: true, error: null, errorStatus: null })
    try {
      const project = await getProject(id)
      set({ currentProject: project, isLoading: false, error: null, errorStatus: null })
    } catch (err: unknown) {
      // 失敗時清掉 currentProject，避免切換專案時殘留前一個專案的資料；
      // 一併記錄 HTTP 狀態碼，供呼叫端（lobby）依 403/404 做導向與提示。
      const status =
        (err as { response?: { status?: number } })?.response?.status ?? null
      set({
        currentProject: null,
        isLoading: false,
        error: '載入專案失敗',
        errorStatus: status,
      })
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
      // 同步更新 projects list 內對應項目的 turn_policy
      projects:
        updates.turn_policy !== undefined && state.currentProject
          ? state.projects.map((p) =>
              p.id === state.currentProject!.id
                ? { ...p, turn_policy: updates.turn_policy }
                : p,
            )
          : state.projects,
    }))
  },

  setTurnPolicy: async (projectId: string, policy: TurnPolicy) => {
    await updateTurnPolicyApi(projectId, policy)
    set((state) => ({
      currentProject:
        state.currentProject?.id === projectId
          ? { ...state.currentProject, turn_policy: policy }
          : state.currentProject,
      projects: state.projects.map((p) =>
        p.id === projectId ? { ...p, turn_policy: policy } : p,
      ),
    }))
  },

  setTurnState: (turnState: TurnState | null) => {
    set({ turnState })
  },

  setRoomPaused: (reason: RoomPauseReason) => set({ roomPauseReason: reason }),
  setRoomResumed: () => set({ roomPauseReason: null }),

  clearError: () => set({ error: null }),
}))

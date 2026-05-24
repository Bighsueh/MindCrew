// /projects 頁面 driver.js spotlight 漫遊
// 老師與學生各一套步驟；元素以 data-tour 屬性選擇

import { driver, type DriveStep } from 'driver.js'
import 'driver.js/dist/driver.css'

const COMMON_OPTIONS = {
  showProgress: true,
  allowClose: true,
  doneBtnText: '我懂了',
  nextBtnText: '下一步 →',
  prevBtnText: '← 上一步',
  progressText: '{{current}} / {{total}}',
  showButtons: ['next', 'previous', 'close'] as ('next' | 'previous' | 'close')[],
  overlayOpacity: 0.55,
  stagePadding: 6,
  stageRadius: 12,
  smoothScroll: true,
}

const TEACHER_STEPS: DriveStep[] = [
  {
    element: '[data-tour="projects-hero"]',
    popover: {
      title: '歡迎來到設計專案列表',
      description:
        '這裡管理你所有的設計思考活動。每個設計專案會走完雙鑽石的四個階段，從訪談到原型一氣呵成。',
    },
  },
  {
    element: '[data-tour="projects-create"]',
    popover: {
      title: '建立新設計專案',
      description:
        '點這顆按鈕開啟新的設計思考活動，可以設定主題、限制條件、AI 貢獻度。',
      side: 'left',
      align: 'start',
    },
  },
  {
    element: '[data-tour="projects-stats"]',
    popover: {
      title: '設計專案總覽',
      description: '一眼看出全部設計專案數、進行中、已完成的數量。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="projects-filters"]',
    popover: {
      title: '依階段篩選',
      description:
        '依雙鑽石階段（Discover / Define / Develop / Deliver）過濾，快速找到還沒收斂的設計專案。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="projects-search"]',
    popover: {
      title: '搜尋設計專案',
      description: '用名稱或描述關鍵字搜尋你關心的設計專案。',
      side: 'bottom',
      align: 'end',
    },
  },
  {
    element: '[data-tour="projects-card"]',
    popover: {
      title: '進入工作區',
      description: '點任一張卡片進入工作區，開始你的設計思考之旅。',
      side: 'top',
    },
  },
]

const STUDENT_STEPS: DriveStep[] = [
  {
    element: '[data-tour="projects-hero"]',
    popover: {
      title: '歡迎',
      description: '這裡是你被邀請加入的設計思考設計專案。',
    },
  },
  {
    element: '[data-tour="projects-stats"]',
    popover: {
      title: '設計專案總覽',
      description: '看看目前進行中與已完成的設計專案數量。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="projects-filters"]',
    popover: {
      title: '篩選與搜尋',
      description: '依雙鑽石階段過濾，或用關鍵字找你要進去的設計專案。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="projects-card"]',
    popover: {
      title: '進入工作區',
      description: '點任一張卡片進入工作區，與團隊一起推進。',
      side: 'top',
    },
  },
]

export type ProjectsTourRole = 'teacher' | 'student'

const SESSION_FLAG_KEY = 'mindcrew.projectsTour.shown'

/**
 * 啟動 /projects 頁面的 spotlight 漫遊。
 * 老師看 6 步、學生看 4 步。若 anchor 元素不存在，driver.js 會跳過該步。
 */
export function startProjectsTour(role: ProjectsTourRole): void {
  const allSteps = role === 'teacher' ? TEACHER_STEPS : STUDENT_STEPS

  // 過濾掉找不到 anchor 的步驟，避免 driver.js 卡住（例：學生無 [data-tour="projects-create"]、無設計專案無 card）
  const steps = allSteps.filter((step) => {
    const selector = step.element as string | undefined
    if (!selector) return true
    return document.querySelector(selector) !== null
  })

  if (steps.length === 0) return

  const tour = driver({
    ...COMMON_OPTIONS,
    steps,
    onDestroyed: () => {
      try {
        window.sessionStorage.setItem(SESSION_FLAG_KEY, '1')
      } catch {
        /* sessionStorage 不可用時靜默 */
      }
    },
  })
  tour.drive()
}

/** 檢查是否已在本 session 看過導覽。 */
export function hasShownProjectsTour(): boolean {
  try {
    return window.sessionStorage.getItem(SESSION_FLAG_KEY) === '1'
  } catch {
    return false
  }
}

/** 清掉 session flag，讓自動啟動可以再跑一次。 */
export function clearProjectsTourFlag(): void {
  try {
    window.sessionStorage.removeItem(SESSION_FLAG_KEY)
  } catch {
    /* silent */
  }
}

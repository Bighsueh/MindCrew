// 教師儀表板 driver.js spotlight 漫遊
// 元素以 data-tour 屬性選擇；runtime 過濾掉找不到 anchor 的步驟

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

const STEPS: DriveStep[] = [
  {
    element: '[data-tour="teacher-hero"]',
    popover: {
      title: '教師儀表板',
      description:
        '這裡是你的指揮中心：監控所有課堂設計專案、管理學生帳號、掌握每組設計思考進度。',
    },
  },
  {
    element: '[data-tour="teacher-create"]',
    popover: {
      title: '建立新設計專案',
      description: '點這顆按鈕開啟新課堂設計專案，設定主題與限制條件後分配給學生。',
      side: 'left',
      align: 'start',
    },
  },
  {
    element: '[data-tour="teacher-tabs"]',
    popover: {
      title: '兩大功能分頁',
      description: '「設計專案監控」追蹤所有課堂進度；「學生管理」可新增帳號、開放設計專案建立權限。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="teacher-stage-distribution"]',
    popover: {
      title: '階段分布總覽',
      description: '一眼看出全班設計專案散落在雙鑽石的哪些階段，誰收斂太慢、誰還在發散都看得出來。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="teacher-alerts"]',
    popover: {
      title: '異常警示',
      description: '系統會抓出進度停滯或團隊狀態異常的設計專案，主動提示你介入。',
      side: 'bottom',
    },
  },
  {
    element: '[data-tour="teacher-monitor-card"]',
    popover: {
      title: '單一設計專案監控卡',
      description: '每張卡顯示一組的當前階段、micro-phase、團隊組成；點進去即可加入該組工作區。',
      side: 'top',
    },
  },
  {
    element: '[data-tour="teacher-empty-cta"]',
    popover: {
      title: '建立第一個設計專案',
      description: '尚未有設計專案？從這裡開始。',
      side: 'top',
    },
  },
]

const SESSION_FLAG_KEY = 'mindcrew.teacherDashboardTour.shown'

/** 啟動教師儀表板漫遊；找不到 anchor 的步驟會自動略過。 */
export function startTeacherDashboardTour(): void {
  const steps = STEPS.filter((step) => {
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
        /* silent */
      }
    },
  })
  tour.drive()
}

export function hasShownTeacherDashboardTour(): boolean {
  try {
    return window.sessionStorage.getItem(SESSION_FLAG_KEY) === '1'
  } catch {
    return false
  }
}

export function clearTeacherDashboardTourFlag(): void {
  try {
    window.sessionStorage.removeItem(SESSION_FLAG_KEY)
  } catch {
    /* silent */
  }
}

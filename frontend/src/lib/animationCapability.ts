/**
 * Animation capability detection — Spec 13 §2.5.
 *
 * 三級：
 *   - full      正常播放
 *   - reduced   時長砍半、stagger 停用（低階裝置）
 *   - off       直接跳到 to-state（prefers-reduced-motion）
 */

export type AnimationLevel = 'full' | 'reduced' | 'off';

let cachedLevel: AnimationLevel | null = null;

export function getAnimationLevel(): AnimationLevel {
  if (cachedLevel !== null) return cachedLevel;
  if (typeof window === 'undefined') {
    cachedLevel = 'full';
    return cachedLevel;
  }

  // 1. prefers-reduced-motion
  try {
    const prefersReduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduce) {
      cachedLevel = 'off';
      return cachedLevel;
    }
  } catch {
    /* ignore */
  }

  // 2. 低階裝置偵測（CPU / RAM）
  const nav = navigator as Navigator & { deviceMemory?: number };
  const cores = nav.hardwareConcurrency ?? 8;
  const memGB = nav.deviceMemory ?? 8;
  if (cores < 4 || memGB < 4) {
    cachedLevel = 'reduced';
    return cachedLevel;
  }

  cachedLevel = 'full';
  return cachedLevel;
}

export function applyAnimationLevel(root?: HTMLElement | null): void {
  const target = root ?? document.documentElement;
  target.dataset.anim = getAnimationLevel();
}

export function isReducedMotion(): boolean {
  return getAnimationLevel() !== 'full';
}

/** Returns staggered delay in ms (0 if stagger disabled by capability). */
export function staggerDelay(index: number, baseMs = 50): number {
  if (getAnimationLevel() !== 'full') return 0;
  return index * baseMs;
}

/** Returns animation duration adjusted for current capability. */
export function adjustedDuration(fullDurationMs: number): number {
  const level = getAnimationLevel();
  if (level === 'off') return 0;
  if (level === 'reduced') return Math.round(fullDurationMs / 2);
  return fullDurationMs;
}

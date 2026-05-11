/**
 * HMW tabs store — Spec 13 §2.4.
 *
 * 多 HMW 並行：每個 tab 對應獨立的 sub-canvas state。
 */

import { create } from 'zustand';

export interface HmwTab {
  hmwId: string;
  label: string; // Blue HMW headline 截短
  noteIds: string[]; // 此 tab 包含的便條 id
}

interface HmwTabsStore {
  tabs: HmwTab[];
  activeHmwId: string | null;
  setTabs: (tabs: HmwTab[]) => void;
  setActive: (hmwId: string | null) => void;
  addTab: (tab: HmwTab) => void;
}

export const useHmwTabsStore = create<HmwTabsStore>((set) => ({
  tabs: [],
  activeHmwId: null,
  setTabs: (tabs) =>
    set((s) => ({
      tabs,
      activeHmwId: s.activeHmwId ?? tabs[0]?.hmwId ?? null,
    })),
  setActive: (hmwId) => set({ activeHmwId: hmwId }),
  addTab: (tab) =>
    set((s) => ({
      tabs: [...s.tabs, tab],
      activeHmwId: s.activeHmwId ?? tab.hmwId,
    })),
}));

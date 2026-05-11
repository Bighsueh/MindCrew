/**
 * Zone store — Spec 13 §2.
 *
 * 後端透過 WebSocket 廣播 zone bounds，前端 ZoneOverlay 訂閱 active zones。
 */

import { create } from 'zustand';

export interface ZoneBounds {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ZoneVisual {
  frame_shape: 'rectangle' | 'quadrant' | 'swimlane' | 'sidebar';
  border_color: string;
  fill_pattern: 'dotted' | 'solid';
  title_sticky: string;
}

export interface ZoneState {
  id: string;
  bounds: ZoneBounds;
  visual: ZoneVisual;
  active: boolean;
  drawnAt: number; // unix ms — for animation trigger
}

interface ZonesStore {
  zones: Record<string, ZoneState>;
  currentSubPhase: string | null;
  setCurrentSubPhase: (sub: string | null) => void;
  upsertZone: (zone: ZoneState) => void;
  removeZone: (zoneId: string) => void;
  markZoneInactive: (zoneId: string) => void;
  clear: () => void;
}

export const useZonesStore = create<ZonesStore>((set) => ({
  zones: {},
  currentSubPhase: null,
  setCurrentSubPhase: (sub) => set({ currentSubPhase: sub }),
  upsertZone: (zone) =>
    set((s) => ({ zones: { ...s.zones, [zone.id]: zone } })),
  removeZone: (zoneId) =>
    set((s) => {
      const next = { ...s.zones };
      delete next[zoneId];
      return { zones: next };
    }),
  markZoneInactive: (zoneId) =>
    set((s) => {
      const z = s.zones[zoneId];
      if (!z) return s;
      return { zones: { ...s.zones, [zoneId]: { ...z, active: false } } };
    }),
  clear: () => set({ zones: {} }),
}));

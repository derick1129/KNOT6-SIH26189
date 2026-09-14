import { create } from "zustand";

/**
 * Raw per-frame scroll progress (0..1), written every animation frame by
 * `ScrollDriver` (inside the Canvas). Deliberately a plain mutable object,
 * not React state -- every 3D object's position depends on this, and
 * routing it through React state would mean a full component re-render
 * 60 times a second. `useFrame` consumers read `scrollProgress.value`
 * directly instead.
 */
export const scrollProgress = { value: 0 };

export const CHAPTER_COUNT = 8;

export const CHAPTER_TITLES = [
  "Fragmented Intelligence",
  "AI Fusion",
  "Entity Resolution",
  "Relationship Discovery",
  "Graph Reveal",
  "Investigation Intelligence",
  "Evidence Integrity",
  "KNOT6",
] as const;

export const CHAPTER_SUBTITLES = [
  "Multiple sources. Disconnected insights.",
  "Fragments converge. The first relationships begin to form.",
  "Variant records resolve into single, confirmed entities.",
  "Connections multiply between people, places, and accounts.",
  "The complete network — every connection, revealed.",
  "Signal surfaces from the noise — for a human to verify.",
  "Every inference traces back to a hash-verified source.",
  "Enter the platform.",
] as const;

/**
 * Coarse chapter index (0..7) -- this *is* real React state, but only
 * changes 8 times across the whole scroll, so it's cheap. Drives the HTML
 * text overlay; the 3D scene reads `scrollProgress.value` directly instead.
 */
interface ChapterState {
  chapter: number;
  localProgress: number; // 0..1 within the current chapter
  setFromProgress: (p: number) => void;
}

export const useChapterStore = create<ChapterState>((set, get) => ({
  chapter: 0,
  localProgress: 0,
  setFromProgress: (p: number) => {
    const clamped = Math.min(0.999999, Math.max(0, p));
    const chapter = Math.min(CHAPTER_COUNT - 1, Math.floor(clamped * CHAPTER_COUNT));
    const localProgress = clamped * CHAPTER_COUNT - chapter;
    const prev = get();
    if (prev.chapter !== chapter || Math.abs(prev.localProgress - localProgress) > 0.02) {
      set({ chapter, localProgress });
    }
  },
}));

/** Smoothstep easing, used throughout the scene for non-linear chapter blends. */
export function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

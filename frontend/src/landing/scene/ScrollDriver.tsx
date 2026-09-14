import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { scrollProgress, useChapterStore } from "../scrollProgress";

/**
 * Renders nothing -- reads the real page scroll position once per frame and
 * writes it into the shared mutable `scrollProgress` value every 3D object
 * reads from. Kept out of React's render cycle deliberately (see
 * scrollProgress.ts); only the coarse chapter index round-trips through
 * real state, and only when it actually changes.
 */
export default function ScrollDriver({ totalHeightPx }: { totalHeightPx: number }) {
  const setFromProgress = useChapterStore((s) => s.setFromProgress);
  const last = useRef(-1);

  useFrame(() => {
    const max = Math.max(1, totalHeightPx - window.innerHeight);
    const p = Math.min(1, Math.max(0, window.scrollY / max));
    scrollProgress.value = p;
    if (Math.abs(p - last.current) > 0.001) {
      last.current = p;
      setFromProgress(p);
    }
  });

  return null;
}

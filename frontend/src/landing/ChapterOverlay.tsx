import { AnimatePresence, motion } from "framer-motion";
import { CHAPTER_SUBTITLES, CHAPTER_TITLES, useChapterStore } from "./scrollProgress";

/**
 * The minimal HTML typography layer -- one eyebrow number, one title, one
 * line of subtitle, swapping per chapter. Deliberately sparse: the 3D scene
 * carries the story, this just labels it (per the brief: "let the 3D
 * visualization do most of the storytelling").
 */
export default function ChapterOverlay() {
  const chapter = useChapterStore((s) => s.chapter);
  const isLast = chapter === CHAPTER_TITLES.length - 1;

  return (
    <div className="fixed inset-0 z-20 flex items-center pointer-events-none">
      <div className="px-[clamp(20px,6vw,88px)] max-w-2xl">
        <AnimatePresence mode="wait">
          <motion.div
            key={chapter}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="eyebrow mb-3">
              {String(chapter + 1).padStart(2, "0")} / {String(CHAPTER_TITLES.length).padStart(2, "0")}
            </div>
            <h1 className="text-[clamp(32px,5.4vw,64px)] font-display font-semibold text-slate-50 leading-[1.03]">
              {CHAPTER_TITLES[chapter]}
            </h1>
            <p className="text-[clamp(14px,1.3vw,18px)] text-muted mt-4 max-w-md">
              {CHAPTER_SUBTITLES[chapter]}
            </p>
            {isLast && (
              <motion.a
                href="/login"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35, duration: 0.5 }}
                className="pointer-events-auto inline-flex items-center gap-2 mt-9 knot-btn-primary px-6 py-3 text-[13px] tracking-wide uppercase"
              >
                Enter KNOT6
                <span aria-hidden>→</span>
              </motion.a>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

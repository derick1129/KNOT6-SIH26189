import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Link } from "react-router-dom";
import ChapterOverlay from "./ChapterOverlay";
import TelemetryOverlay from "./TelemetryOverlay";
import "./landing.css";
import { CHAPTER_TITLES, useChapterStore } from "./scrollProgress";
import { useAuth } from "../store/auth";

// Three.js + postprocessing is the single heaviest dependency in the app --
// code-split so /login and the app shell never pay for it, only the
// landing route does.
const IntelligenceWorld = lazy(() => import("./scene/IntelligenceWorld"));

const PACE_VH_PER_CHAPTER = 118; // > 100vh per chapter so the story doesn't feel rushed

export default function LandingPage() {
  const { token } = useAuth();
  const chapter = useChapterStore((s) => s.chapter);
  const [heightPx, setHeightPx] = useState(0);

  useEffect(() => {
    const compute = () =>
      setHeightPx((window.innerHeight * PACE_VH_PER_CHAPTER * CHAPTER_TITLES.length) / 100);
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, []);

  // Returning, already-authenticated visitors skip straight to the app --
  // the cinematic intro is a first-impression tool, not a gate.
  if (token) return <Navigate to="/overview" replace />;

  return (
    <div className="relative bg-ink">
      <nav className="knot-landing-nav">
        <div className="font-display font-semibold text-lg tracking-wide text-slate-100">
          KNOT6
        </div>
        <Link to="/login" className="knot-btn-ghost">
          Sign in
        </Link>
      </nav>

      <div className="fixed inset-0 z-0">
        {heightPx > 0 && (
          <Suspense fallback={<div className="w-full h-full bg-ink" />}>
            <IntelligenceWorld totalHeightPx={heightPx} />
          </Suspense>
        )}
      </div>

      <ChapterOverlay />
      <TelemetryOverlay />

      <div className="knot-progress-rail" aria-hidden>
        {CHAPTER_TITLES.map((_, i) => (
          <div key={i} className={`knot-progress-dot ${i === chapter ? "active" : ""}`} />
        ))}
      </div>

      {chapter < CHAPTER_TITLES.length - 1 && (
        <div className="knot-scroll-hint">
          <span>Scroll</span>
          <div className="line" />
        </div>
      )}

      {/* Real page height so native scroll drives the experience -- see
          scrollProgress.ts / ScrollDriver.tsx. */}
      <div style={{ height: heightPx || "800vh" }} />
    </div>
  );
}

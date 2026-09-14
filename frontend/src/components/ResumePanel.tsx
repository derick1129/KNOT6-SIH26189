import { useEffect, useState } from "react";
import { api, ResumePoint } from "../api/client";
import { useCopilotNavigation } from "./copilotActions";
import { useInvestigation } from "../store/investigation";

/**
 * KNOT6 Case Intelligence 2.0: "Continue where you left off" -- backed by
 * real recorded activity (see backend/app/services/activity.py), never
 * invented. `GET /investigations/{id}/resume` returns `available: false`
 * until this user has actually viewed an entity/path/evidence item in this
 * investigation (via copilotActions.ts), in which case this honestly shows
 * the "START INVESTIGATING" state instead.
 */
export default function ResumePanel() {
  const { currentId } = useInvestigation();
  const nav = useCopilotNavigation();
  const [resume, setResume] = useState<ResumePoint | null>(null);

  useEffect(() => {
    if (!currentId) return;
    setResume(null);
    api.get(`/investigations/${currentId}/resume`).then((res) => setResume(res.data));
  }, [currentId]);

  if (!resume) return null;

  return (
    <div className="card-elevated flex items-center justify-between gap-4 flex-wrap">
      {resume.available ? (
        <>
          <div className="min-w-0">
            <div className="eyebrow mb-1">Continue where you left off</div>
            <div className="text-sm text-slate-100">{resume.description}</div>
          </div>
          <button
            className="knot-btn-primary shrink-0"
            onClick={() => resume.action && nav.runAction(resume.action)}
          >
            Continue
          </button>
        </>
      ) : (
        <div>
          <div className="eyebrow mb-1">Start investigating</div>
          <div className="text-sm text-slate-100">KNOT6 is ready to help you explore this investigation.</div>
        </div>
      )}
    </div>
  );
}

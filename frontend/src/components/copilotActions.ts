import { useNavigate } from "react-router-dom";
import { api, CopilotAction, CopilotCitation } from "../api/client";
import { useInvestigation } from "../store/investigation";

/**
 * Shared navigation for every "quick action" the Case Intelligence page and
 * the AI Copilot can offer -- both compose the same underlying screens
 * (Network Explorer's `?focus=` deep link, Path Finder's `?source=&target=`
 * deep link, Evidence Vault's `?evidence=` highlight), so an action here is
 * never a dead button per the KNOT6 Case Intelligence brief.
 *
 * KNOT6 Case Intelligence 2.0: this is also the ONE place that records real
 * investigation activity (`POST /investigations/{id}/activity`) for
 * "Continue where you left off" -- deliberately, not scattered across every
 * page (see backend/app/db/models.py's InvestigationActivity docstring for
 * the scope rationale). Fire-and-forget: a failed activity POST never
 * blocks navigation.
 */
export function useCopilotNavigation() {
  const navigate = useNavigate();
  const { currentId } = useInvestigation();

  const record = (
    activity_type: string,
    target_type?: string,
    target_id?: string,
    target_label?: string,
    extra?: Record<string, any>
  ) => {
    if (!currentId) return;
    api
      .post(`/investigations/${currentId}/activity`, { activity_type, target_type, target_id, target_label, extra })
      .catch(() => {});
  };

  const openEntity = (entityId: string, label?: string) => {
    record("ENTITY_VIEWED", "ENTITY", entityId, label);
    navigate(`/network?focus=${entityId}`);
  };

  const openPath = (sourceId: string, targetId: string, sourceLabel?: string, targetLabel?: string) => {
    record("PATH_VIEWED", "PATH", sourceId, sourceLabel, { target_entity_id: targetId, target_label: targetLabel });
    navigate(`/path?source=${sourceId}&target=${targetId}`);
  };

  const openEvidence = (evidenceId?: string, label?: string) => {
    if (evidenceId) record("EVIDENCE_VIEWED", "EVIDENCE", evidenceId, label);
    navigate(evidenceId ? `/evidence?evidence=${evidenceId}` : "/evidence");
  };

  const recordSearch = (query: string) => record("SEARCH_PERFORMED", "SEARCH", undefined, query);

  const runAction = (action: CopilotAction) => {
    // `action.label` (e.g. "Open Suresh Yadav") is already a
    // human-readable description of the target -- reused as the activity's
    // target_label so "Continue where you left off" never falls back to a
    // generic "an entity" when an action came from a CopilotAction rather
    // than a direct openEntity/openPath call with its own label.
    switch (action.type) {
      case "OPEN_ENTITY":
        if (action.entity_id) openEntity(action.entity_id, action.label);
        break;
      case "OPEN_GRAPH":
        if (action.entity_id) {
          record("NETWORK_FOCUSED", "ENTITY", action.entity_id, action.label);
          navigate(`/network?focus=${action.entity_id}`);
        }
        break;
      case "SHOW_PATH":
        if (action.entity_id && action.target_entity_id) {
          openPath(action.entity_id, action.target_entity_id, action.label);
        }
        break;
      case "VIEW_EVIDENCE":
        openEvidence(action.evidence_id ?? undefined);
        break;
      case "VIEW_TIMELINE":
        navigate("/timeline");
        break;
      case "OPEN_HYPOTHESIS":
        // Deliberately not recorded as ENTITY_VIEWED activity: that type's
        // resume action always reopens via OPEN_ENTITY/`?focus=<id>` on the
        // Network Explorer (see backend/app/services/activity.py's
        // _resume_action), which would silently break "Continue where you
        // left off" for a hypothesis id (not a graph entity id). Hypothesis
        // Lab has its own saved-list persistence as the way back to it.
        if (action.hypothesis_id) navigate(`/hypothesis?open=${action.hypothesis_id}`);
        break;
      case "OPEN_FINANCIAL":
        navigate("/financial");
        break;
      case "OPEN_GEO":
        navigate("/geo");
        break;
    }
  };

  const openCitation = (citation: CopilotCitation) => {
    openEvidence(citation.evidence_id, citation.label);
  };

  return { runAction, openCitation, openEntity, openPath, openEvidence, recordSearch };
}

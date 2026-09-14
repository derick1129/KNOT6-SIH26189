/**
 * Human-readable relationship context for graph link hover/click.
 *
 * The `/graph` API's `Relation.attributes` is empty for event-driven
 * relations (CALLED, TRANSACTED_WITH) on the current backend -- per-call
 * timestamps/durations and per-transaction amounts are recorded internally
 * (see backend/app/db/graph_store.py's `record_edge_event`) but not yet
 * surfaced through this endpoint. `weight`, however, genuinely IS an event
 * count for those two types (it increments once per recorded call/transfer),
 * so it's real, honest signal -- used here. Nothing else is invented: per
 * the brief, if the API doesn't expose enough metadata, the description
 * stays simple rather than fabricating an amount or a timestamp.
 */
const RELATION_VERB: Record<string, string> = {
  CALLED: "Called",
  TRANSACTED_WITH: "Transacted with",
  ASSOCIATED_WITH: "Associated with",
  OWNS: "Owns",
  PRESENT_AT: "Present at",
  MEMBER_OF: "Member of",
  MENTIONED_WITH: "Co-mentioned with",
};

export function describeRelation(type: string, weight: number): string {
  const verb = RELATION_VERB[type] ?? type.replace(/_/g, " ").toLowerCase();
  const count = Math.max(1, Math.round(weight));
  if (type === "CALLED") return `${verb} · ${count} call${count === 1 ? "" : "s"} recorded`;
  if (type === "TRANSACTED_WITH") return `${verb} · ${count} transaction${count === 1 ? "" : "s"} recorded`;
  return verb;
}

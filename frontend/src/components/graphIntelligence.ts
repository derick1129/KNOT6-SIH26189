import { Community, Entity, GraphData, InfluencerScore } from "../api/client";

/**
 * Pure data-derivation for the Overview dashboard's "understandable
 * snapshot" graph mode. Every number here comes from data the backend
 * already computes (`/analytics/influencers`, `/analytics/communities`) or
 * from the graph's own edges (degree) -- nothing invented. This is what
 * lets the graph show hierarchy (important vs. peripheral) and community
 * structure (spatial clustering + a label) instead of 59 equally-weighted
 * dots in a tangle.
 */

export interface EnrichedNode {
  entity: Entity;
  degree: number;
  /** 0..1. Real backend composite_score when this entity is ranked among
   * the investigation's influencers; otherwise a normalized-degree floor
   * scaled down so it can never outrank an actually-ranked influencer. */
  importance: number;
  communityId: number | null;
}

export interface CommunitySummary {
  id: number;
  /** Heuristic label from the real majority entity type among this
   * community's actual members -- e.g. mostly PHONE entities -> "Communication". */
  label: string;
  size: number;
  memberIds: Set<string>;
  /** The single highest-importance member -- carries the community's
   * label sprite in the 3D scene so there's one legible landmark per
   * cluster, not a separate floating object to keep positioned. */
  hubId: string;
}

export interface EnrichedGraph {
  nodes: Map<string, EnrichedNode>;
  communities: CommunitySummary[];
  /** Nodes that get a persistent glyph + label in the 3D scene: the
   * highest-importance entities overall, plus every community's hub (so
   * every cluster has at least one identifiable landmark). Deliberately a
   * small set -- everything else stays a plain, subtle colored marker,
   * readable via hover, never all labeled at once. */
  importantIds: Set<string>;
  /**
   * The next band of moderately-important entities, just below
   * `importantIds` -- real estate for a middle label tier: always a glyph,
   * and (see NetworkGraph3D's camera-distance check) a compact name label
   * once the investigator is zoomed in close enough, rather than either
   * "always labeled" or "hover only". Disjoint from `importantIds`.
   */
  mediumIds: Set<string>;
  /**
   * The Overview's actual "investigation map" node set -- a curated subset
   * of the full graph, NOT every entity. "Show fewer, more relevant
   * entities" only works if fewer entities are actually rendered, not just
   * rendered smaller/dimmer; showing all 59 nodes (even mostly-subdued
   * ones) with all their edges is exactly the dense hairball the KNOT6
   * visual-identity brief calls unacceptable. A superset of `importantIds`
   * (same top-importance + community-hub selection, just a larger K) so
   * every labeled node is guaranteed part of the shown map, plus enough
   * additional context nodes that the curated map still reads as a real,
   * connected piece of the investigation rather than 8 isolated dots.
   * NetworkGraph3D filters both nodes and edges to this set when
   * `simplified` -- Network Explorer (unaffected) still gets the full graph.
   */
  curatedIds: Set<string>;
}

const DOMINANT_TYPE_LABEL: Record<string, string> = {
  PERSON: "People",
  ORGANIZATION: "Organizations",
  PHONE: "Communication",
  FINANCIAL_ACCOUNT: "Financial",
  LOCATION: "Location",
  VEHICLE: "Vehicles",
  EVENT: "Events",
  CASE: "Events",
};

export function enrichGraph(graph: GraphData, influencers: InfluencerScore[], communities: Community[]): EnrichedGraph {
  const degree = new Map<string, number>();
  for (const e of graph.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const maxDegree = Math.max(1, ...Array.from(degree.values(), (v) => v));

  const scoreById = new Map(influencers.map((i) => [i.entity.id, i.composite_score]));
  const maxScore = Math.max(0, ...influencers.map((i) => i.composite_score));

  const communityByNode = new Map<string, number>();
  communities.forEach((c, idx) => c.members.forEach((m) => communityByNode.set(m.id, idx)));

  const nodes = new Map<string, EnrichedNode>();
  for (const entity of graph.nodes) {
    const d = degree.get(entity.id) ?? 0;
    const rankedScore = scoreById.get(entity.id);
    // A ranked influencer's real composite score, normalized against the
    // strongest one in this investigation; otherwise a degree-based floor
    // capped below the weakest possible ranked score's usual range, so
    // "not independently ranked" entities never visually outrank one that is.
    const importance =
      rankedScore != null && maxScore > 0 ? rankedScore / maxScore : Math.min(0.5, (d / maxDegree) * 0.5);
    nodes.set(entity.id, { entity, degree: d, importance, communityId: communityByNode.get(entity.id) ?? null });
  }

  const communitySummaries: CommunitySummary[] = communities.map((c, idx) => {
    const typeCounts = new Map<string, number>();
    c.members.forEach((m) => typeCounts.set(m.type, (typeCounts.get(m.type) ?? 0) + 1));
    let dominantType = c.members[0]?.type ?? "PERSON";
    let bestCount = -1;
    typeCounts.forEach((count, type) => {
      if (count > bestCount) {
        bestCount = count;
        dominantType = type;
      }
    });

    let hubId = c.members[0]?.id ?? "";
    let hubImportance = -1;
    c.members.forEach((m) => {
      const importance = nodes.get(m.id)?.importance ?? 0;
      if (importance > hubImportance) {
        hubImportance = importance;
        hubId = m.id;
      }
    });

    return {
      id: idx,
      label: DOMINANT_TYPE_LABEL[dominantType] ?? "Mixed",
      size: c.size,
      memberIds: new Set(c.members.map((m) => m.id)),
      hubId,
    };
  });

  const byImportance = Array.from(nodes.values()).sort((a, b) => b.importance - a.importance);

  const K = Math.min(8, graph.nodes.length);
  const importantIds = new Set(byImportance.slice(0, K).map((n) => n.entity.id));
  communitySummaries.forEach((c) => {
    if (c.hubId) importantIds.add(c.hubId);
  });

  // Medium tier: the next band by real importance, excluding whatever's
  // already in the high tier above.
  const MEDIUM_BAND = Math.min(18, graph.nodes.length);
  const mediumIds = new Set(byImportance.slice(0, MEDIUM_BAND).map((n) => n.entity.id));
  importantIds.forEach((id) => mediumIds.delete(id));

  // The curated "investigation map" set: a larger K (still a small
  // fraction of a real investigation's full graph), same
  // importance-ranked + hub-union selection as importantIds above. Bumped
  // from 22 -> 30: at 22 the map (tuned for a strong, roomy spread) read as
  // mostly empty space around a handful of nodes -- 30 gives the graph
  // enough real structure to actually fill the panel while staying far
  // below the full 59-node graph Network Explorer shows.
  const CURATED_K = Math.min(30, graph.nodes.length);
  const curatedIds = new Set(byImportance.slice(0, CURATED_K).map((n) => n.entity.id));
  importantIds.forEach((id) => curatedIds.add(id));
  mediumIds.forEach((id) => curatedIds.add(id));

  return { nodes, communities: communitySummaries, importantIds, mediumIds, curatedIds };
}

/**
 * A standard d3-force "cluster" force: each tick, nudges every node toward
 * the live centroid of its own community's current positions. Runs
 * alongside three-forcegraph's default link/charge/center forces (added
 * under its own name via `.d3Force('cluster', ...)`, nothing removed) --
 * real spatial separation driven by real community membership, not a
 * hand-placed layout.
 */
export function createClusterForce(getCommunityId: (nodeId: string) => number | null, strength = 0.055) {
  let simulationNodes: any[] = [];

  function force(alpha: number) {
    const sums = new Map<number, { x: number; y: number; z: number; n: number }>();
    for (const node of simulationNodes) {
      const c = getCommunityId(node.id);
      if (c == null) continue;
      const acc = sums.get(c) ?? { x: 0, y: 0, z: 0, n: 0 };
      acc.x += node.x ?? 0;
      acc.y += node.y ?? 0;
      acc.z += node.z ?? 0;
      acc.n += 1;
      sums.set(c, acc);
    }
    const centroids = new Map<number, { x: number; y: number; z: number }>();
    sums.forEach((acc, c) => centroids.set(c, { x: acc.x / acc.n, y: acc.y / acc.n, z: acc.z / acc.n }));

    for (const node of simulationNodes) {
      const c = getCommunityId(node.id);
      if (c == null) continue;
      const centroid = centroids.get(c);
      if (!centroid) continue;
      node.vx = (node.vx ?? 0) + (centroid.x - (node.x ?? 0)) * strength * alpha;
      node.vy = (node.vy ?? 0) + (centroid.y - (node.y ?? 0)) * strength * alpha;
      node.vz = (node.vz ?? 0) + (centroid.z - (node.z ?? 0)) * strength * alpha;
    }
  }

  force.initialize = (nodes: any[]) => {
    simulationNodes = nodes;
  };

  return force;
}

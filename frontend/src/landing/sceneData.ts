import * as THREE from "three";

/**
 * KNOT6 landing scene: a deterministic (seeded) dataset representing the
 * "one continuous 3D world" the scroll narrative moves through -- the same
 * ~54 nodes exist for the whole experience; only their position/opacity/
 * connections change across chapters. Nothing here is random-per-render
 * (a fixed seed), so the layout is stable across re-mounts and resizes.
 *
 * Deliberately procedural rather than loaded 3D models/document textures --
 * consistent with the "premium institutional software" direction (abstract,
 * restrained) and avoids depending on external art assets.
 */

// Minimal seeded PRNG (mulberry32) so the layout is stable, not Math.random().
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type FragmentKind = "document" | "phone" | "vehicle" | "location" | "financial" | "social";

export interface SceneNode {
  id: string;
  kind: FragmentKind;
  label: string;
  community: number;
  importance: number; // 0..1 -- drives size/glow of "hub" nodes in later chapters
  fragmentPos: THREE.Vector3; // chaotic starting position (ch. 1)
  graphPos: THREE.Vector3; // resolved knowledge-graph position (ch. 5+)
}

export interface SceneEdge {
  a: string;
  b: string;
  bridge: boolean; // crosses two communities -- the "bridge person" visual motif
  weight: number; // 0..1 relationship strength -- drives line brightness/thickness hierarchy
}

const KIND_LABELS: Record<FragmentKind, string[]> = {
  document: ["FIR-2031", "Surveillance Rpt.", "Intel Summary", "Witness Stmt.", "Case File"],
  phone: ["CDR Record", "+91 9•••• ••210", "Call Log", "Tower Ping"],
  vehicle: ["MP09 •• 1234", "Vehicle Log", "ANPR Hit"],
  location: ["Central Market", "Highway Dhaba", "Rau, Indore", "Rajwada"],
  financial: ["TXN-4471", "ACC •••1002", "UPI Transfer", "Bank Record"],
  social: ["Social Post", "Handle @•••", "Platform Msg."],
};

export const COMMUNITY_COUNT = 5;
const NODES_PER_COMMUNITY = 10;

function buildCommunityCentroids(rng: () => number): THREE.Vector3[] {
  const centroids: THREE.Vector3[] = [];
  const radius = 5.6;
  for (let i = 0; i < COMMUNITY_COUNT; i++) {
    const angle = (i / COMMUNITY_COUNT) * Math.PI * 2 + rng() * 0.3;
    const elevation = (rng() - 0.5) * 2.4;
    centroids.push(
      new THREE.Vector3(Math.cos(angle) * radius, elevation, Math.sin(angle) * radius)
    );
  }
  return centroids;
}

function makeScene() {
  const rng = mulberry32(20260911);
  const centroids = buildCommunityCentroids(rng);
  const kinds: FragmentKind[] = ["document", "phone", "vehicle", "location", "financial", "social"];

  const nodes: SceneNode[] = [];
  let idx = 0;
  for (let c = 0; c < COMMUNITY_COUNT; c++) {
    const centroid = centroids[c];
    for (let n = 0; n < NODES_PER_COMMUNITY; n++) {
      const kind = kinds[Math.floor(rng() * kinds.length)];
      const labels = KIND_LABELS[kind];
      const label = labels[Math.floor(rng() * labels.length)];

      // Fragmented (chapter 1) position: scattered widely and randomly,
      // no relationship to final cluster -- true disconnection.
      const fragmentPos = new THREE.Vector3(
        (rng() - 0.5) * 26,
        (rng() - 0.5) * 14,
        (rng() - 0.5) * 26
      );

      // Resolved graph (chapter 5+) position: clustered around this node's
      // community centroid, small local jitter so it doesn't look gridded.
      const local = new THREE.Vector3(
        (rng() - 0.5) * 2.6,
        (rng() - 0.5) * 2.2,
        (rng() - 0.5) * 2.6
      );
      const graphPos = centroid.clone().add(local);

      nodes.push({
        id: `n${idx}`,
        kind,
        label,
        community: c,
        importance: n === 0 ? 0.85 + rng() * 0.15 : rng() * 0.5, // one clear hub per community
        fragmentPos,
        graphPos,
      });
      idx++;
    }
  }

  // Edges: dense-ish within a community, a handful of deliberate
  // cross-community "bridge" edges (the investigative bridge-person motif).
  // `weight` gives the render layer a real hierarchy signal -- hub spokes
  // read stronger than incidental chain links, bridges strongest of all.
  const edges: SceneEdge[] = [];
  for (let c = 0; c < COMMUNITY_COUNT; c++) {
    const members = nodes.filter((n) => n.community === c);
    const hub = members[0];
    for (let i = 1; i < members.length; i++) {
      if (rng() < 0.62) {
        edges.push({ a: hub.id, b: members[i].id, bridge: false, weight: 0.55 + rng() * 0.3 });
      }
      if (i > 1 && rng() < 0.22) {
        edges.push({
          a: members[i - 1].id,
          b: members[i].id,
          bridge: false,
          weight: 0.15 + rng() * 0.2,
        });
      }
    }
  }
  // Bridge edges: hub-to-hub across a couple of community pairs.
  for (let c = 0; c < COMMUNITY_COUNT; c++) {
    const next = (c + 1) % COMMUNITY_COUNT;
    if (rng() < 0.7) {
      const a = nodes.find((n) => n.community === c && n.importance > 0.8);
      const b = nodes.find((n) => n.community === next && n.importance > 0.8);
      if (a && b) edges.push({ a: a.id, b: b.id, bridge: true, weight: 1 });
    }
  }

  return { nodes, edges };
}

export const SCENE = makeScene();

export function nodeById(id: string): SceneNode | undefined {
  return SCENE.nodes.find((n) => n.id === id);
}

// The single highest-importance, most-bridged node -- used as the ch.6/7
// "investigative lead" focal point so the narrative has one consistent
// through-line rather than an arbitrary node each time.
export const FOCAL_NODE: SceneNode =
  SCENE.nodes
    .slice()
    .sort((a, b) => {
      const bridgesA = SCENE.edges.filter((e) => e.bridge && (e.a === a.id || e.b === a.id)).length;
      const bridgesB = SCENE.edges.filter((e) => e.bridge && (e.a === b.id || e.b === b.id)).length;
      return bridgesB - bridgesA || b.importance - a.importance;
    })[0];

export const EVIDENCE_NODE: SceneNode | undefined = SCENE.nodes.find(
  (n) => n.community === FOCAL_NODE.community && n.kind === "document" && n.id !== FOCAL_NODE.id
);

/**
 * Entity-resolution pairs: two ordinary (non-hub, non-focal, non-evidence)
 * records per pair that visually converge into one during chapter 3 --
 * the concrete "Rahul Kumar / R. Kumar become one resolved entity" moment.
 * `keep` is the survivor (stays at its graphPos); `merge` slides into it
 * and shrinks, rather than being destroyed -- the node count never
 * changes, only its state, matching "nodes can merge, not disappear".
 */
function pickDuplicatePair(community: number): [string, string] | null {
  const candidates = SCENE.nodes.filter(
    (n) =>
      n.community === community &&
      n.importance <= 0.5 &&
      n.id !== FOCAL_NODE.id &&
      n.id !== EVIDENCE_NODE?.id
  );
  if (candidates.length < 2) return null;
  return [candidates[0].id, candidates[1].id];
}

export const DUPLICATE_PAIRS: { keep: string; merge: string }[] = [0, 2]
  .map(pickDuplicatePair)
  .filter((p): p is [string, string] => p !== null)
  .map(([keep, merge]) => ({ keep, merge }));

/** Average resolved position of every member of a community -- used by the
 * camera path to drift toward/look at a specific cluster instead of always
 * re-centering on the world origin. */
export function communityCentroid(community: number): THREE.Vector3 {
  const members = SCENE.nodes.filter((n) => n.community === community);
  const sum = members.reduce((acc, n) => acc.add(n.graphPos), new THREE.Vector3());
  return sum.multiplyScalar(1 / Math.max(1, members.length));
}

/** Center + radius of the fully-resolved graph -- lets the finale camera
 * keyframe frame the *whole* network regardless of future dataset tuning,
 * rather than a hardcoded distance. */
export const GRAPH_BOUNDS = (() => {
  const center = SCENE.nodes
    .reduce((acc, n) => acc.add(n.graphPos), new THREE.Vector3())
    .multiplyScalar(1 / SCENE.nodes.length);
  const radius = SCENE.nodes.reduce((max, n) => Math.max(max, n.graphPos.distanceTo(center)), 0);
  return { center, radius };
})();

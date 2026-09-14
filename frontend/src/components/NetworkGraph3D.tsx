import { useCallback, useEffect, useMemo, useRef, useState } from "react";
// react-force-graph-3d ships no bundled types; the existing 2D GraphView
// follows the same loose-typing pattern for this package family.
// @ts-ignore
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import { Community, Entity, GraphData, InfluencerScore, Relation } from "../api/client";
import { TYPE_COLOR } from "./graphColors";
import { createClusterForce, enrichGraph } from "./graphIntelligence";
import { describeRelation } from "./relationshipMeaning";

interface Props {
  data: GraphData;
  focusId?: string | null;
  onNodeClick?: (entity: Entity) => void;
  height?: number;
  /** Adds small +/- dolly buttons (bottom-right) -- off by default so the
   * existing Network Explorer surface is pixel-identical unless it opts in. */
  showZoomControls?: boolean;
  /** Real backend analytics (`/analytics/influencers`, `/analytics/communities`)
   * -- optional. When provided together with `simplified`, they drive which
   * entities get a readable glyph+label and how communities cluster. */
  influencers?: InfluencerScore[];
  communities?: Community[];
  /**
   * "Understandable snapshot" mode for the Overview dashboard: importance-
   * scaled node size, glyph+label on the important entities and one hub per
   * community, community spatial clustering, and a smarter initial camera
   * fit. Off by default -- Network Explorer's existing detailed-inspection
   * surface (every node an equal plain sphere, full manual pan/zoom/filter)
   * is completely unchanged unless a caller opts in.
   */
  simplified?: boolean;
  /**
   * Overview's fullscreen presentation of the same simplified graph -- more
   * canvas real estate, so the medium-importance label tier (see
   * `mediumIds`) is shown outright instead of only once the investigator
   * zooms in close. No effect when `simplified` is false.
   */
  expanded?: boolean;
}

const FALLBACK_TYPE_COLOR = "#8A9A91"; // muted sage-grey, for a type not in TYPE_COLOR

function titleCaseType(type: string): string {
  return type.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function truncateLabel(label: string, max: number): string {
  if (label.length <= max) return label;
  return `${label.slice(0, max - 1).trimEnd()}…`;
}

/** 0..1 real importance (backend composite_score, or a degree floor -- see
 * graphIntelligence.ts) into the plain-language tier the hover panel shows.
 * Deliberately "investigation relevance" / never "criminal probability". */
function relevanceLabel(importance: number): string {
  if (importance >= 0.6) return "High";
  if (importance >= 0.3) return "Medium";
  return "Low";
}

/**
 * The signature 3D Network Explorer surface -- react-force-graph-3d
 * (same author/prop family as the pre-existing 2D `GraphView`, which stays
 * in place for the contexts 2D is still clearer for; see
 * KNOT6_KEEP_MODIFY_ADD.md). Wraps force-directed layout + WebGL rendering
 * rather than a hand-rolled physics simulation, given the time box --
 * still real 3D, real rotate/zoom/pan, real per-node/per-link data.
 */
export default function NetworkGraph3D({
  data,
  focusId,
  onNodeClick,
  height = 640,
  showZoomControls = false,
  influencers = [],
  communities = [],
  simplified = false,
  expanded = false,
}: Props) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  // Set on click (simplified mode only): drives one visible "selected" frame
  // -- brighter node, highlighted neighborhood, dimmed rest -- before the
  // existing navigation actually fires (see the delayed onNodeClick below).
  const [clickedId, setClickedId] = useState<string | null>(null);
  // Every medium-tier node's decoration group, so the camera-distance
  // effect below can toggle just their label sprites without touching
  // react-force-graph's own per-node objects. Rebuilt whenever the
  // decoration function itself is (`[simplified, enriched, expanded]`).
  const mediumLabelGroupsRef = useRef<THREE.Object3D[]>([]);
  // The most recent camera-fit distance, so "zoomed in enough to show a
  // medium-tier label" scales to this investigation's actual graph size
  // instead of one fixed magic number.
  const lastFitDistanceRef = useRef(300);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setSize({ width: el.clientWidth, height });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [height]);

  // Real-data derivation (importance, community membership, community
  // labels/hubs) -- see graphIntelligence.ts. Cheap at this scale (tens of
  // nodes), so always computed; only consulted when `simplified` is on.
  const enriched = useMemo(() => enrichGraph(data, influencers, communities), [data, influencers, communities]);

  const graphData = useMemo(() => {
    // Overview mode renders a CURATED subset (see graphIntelligence.ts's
    // curatedIds), not the full graph -- "show the most relevant entities
    // initially, the full graph belongs in Network Explorer" only holds if
    // fewer nodes are actually in the scene, not just smaller/dimmer.
    // Explorer (!simplified) is completely unaffected -- full node/edge set.
    const sourceNodes = simplified ? data.nodes.filter((n) => enriched.curatedIds.has(n.id)) : data.nodes;
    const shownIds = new Set(sourceNodes.map((n) => n.id));
    const nodes = sourceNodes.map((n) => ({
      ...n,
      // Explorer mode: unchanged sizing (uniform-ish, by source count).
      // Overview mode: size is the real investigative-importance signal --
      // a wider range and a super-linear curve than before so a genuinely
      // important entity visibly dominates a peripheral one, with a floor
      // that keeps low-importance nodes from shrinking to near-invisible.
      val: simplified
        ? 2.6 + Math.pow(enriched.nodes.get(n.id)?.importance ?? 0, 1.35) * 8.6
        : 1.2 + Math.min(n.source_count, 6) * 0.6,
    }));
    const links = data.edges
      .filter((e) => !simplified || (shownIds.has(e.source) && shownIds.has(e.target)))
      .map((e: Relation) => ({ id: e.id, source: e.source, target: e.target, type: e.type, weight: e.weight }));
    return { nodes, links };
  }, [data, simplified, enriched]);

  // Selection OR (in simplified mode) hover drives the same "focus this
  // entity's neighborhood, dim the rest" treatment -- hovering any node
  // immediately shows what it connects to, not just after a click. A click
  // takes over from hover (see `clickedId`) so the pre-navigation "selected"
  // frame doesn't get immediately overwritten by whatever's under the
  // cursor a moment later.
  const activeId = focusId ?? (simplified ? clickedId ?? hoveredId : null);
  const highlightIds = useMemo(() => {
    if (!activeId) return null;
    const ids = new Set<string>([activeId]);
    data.edges.forEach((e) => {
      if (e.source === activeId) ids.add(e.target);
      if (e.target === activeId) ids.add(e.source);
    });
    return ids;
  }, [activeId, data.edges]);

  const activeInfo = simplified && activeId ? enriched.nodes.get(activeId) : undefined;

  // Dolly the existing orbit camera in/out along its current line of sight
  // -- the same public `cameraPosition()` API already used above for
  // focus-follow, just moving toward/away from wherever it's currently
  // looking rather than at a specific node.
  const dolly = (factor: number) => {
    const fg = fgRef.current;
    if (!fg) return;
    const { x, y, z } = fg.cameraPosition();
    fg.cameraPosition({ x: x * factor, y: y * factor, z: z * factor }, undefined, 260);
  };

  // Re-frames the camera to whatever the graph's actual current bounds
  // are -- used both for the automatic post-layout fit below and for the
  // investigator-facing "Reset View" control, which just re-runs the exact
  // same real-bbox fit on demand rather than a separate hand-picked shot.
  const fitCamera = useCallback((duration = 500) => {
    const fg = fgRef.current;
    const bbox = fg?.getGraphBbox();
    if (!fg || !bbox) return;
    const cx = (bbox.x[0] + bbox.x[1]) / 2;
    const cy = (bbox.y[0] + bbox.y[1]) / 2;
    const cz = (bbox.z[0] + bbox.z[1]) / 2;
    const radius = Math.max(bbox.x[1] - bbox.x[0], bbox.y[1] - bbox.y[0], bbox.z[1] - bbox.z[0], 20) / 2;
    const distance = (radius * 1.06) / Math.tan((25 * Math.PI) / 180); // ~50deg vertical FOV, +6% breathing room
    lastFitDistanceRef.current = distance;
    fg.cameraPosition({ x: cx, y: cy, z: cz + distance }, { x: cx, y: cy, z: cz }, duration);
  }, []);

  useEffect(() => {
    if (!focusId || !fgRef.current) return;
    const node = graphData.nodes.find((n: any) => n.id === focusId) as any;
    if (!node || node.x == null) return;
    const distance = 90;
    const ratio = 1 + distance / Math.hypot(node.x, node.y, node.z || 1);
    fgRef.current.cameraPosition(
      { x: node.x * ratio, y: node.y * ratio, z: (node.z || 1) * ratio },
      node,
      900
    );
  }, [focusId, graphData.nodes]);

  // Community clustering: a real physics force (see graphIntelligence.ts)
  // pulling each node toward its own detected community's live centroid --
  // spatial separation driven by real membership data, not a fixed layout.
  // Depends on `size.width` too: the graph (and thus `fgRef.current`) only
  // mounts once ResizeObserver reports a real container width, which can
  // happen after `simplified`/`enriched` have already "settled" -- without
  // this, the effect could fire once against a still-null ref and then
  // never fire again.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    if (simplified && enriched.communities.length > 0) {
      fg.d3Force("cluster", createClusterForce((id) => enriched.nodes.get(id)?.communityId ?? null));
    } else {
      fg.d3Force("cluster", null);
    }
    // "Readable investigation map" spacing (Overview only): enough node
    // repulsion and link rest-length to keep individual entities legible
    // and separate communities visually apart, but tightened from the
    // original pass -- that config (charge -130 / link 65 over a ~20-node
    // set) left the panel mostly empty once the curated set grew to 30
    // nodes to actually show real structure. Network Explorer's existing
    // force config (and thus its familiar density/feel) is completely
    // untouched.
    if (simplified) {
      const charge = fg.d3Force("charge");
      if (charge) charge.strength(-105).distanceMax(460);
      const link = fg.d3Force("link");
      if (link) link.distance(52);
    }
  }, [simplified, enriched, size.width]);

  // Fit the camera to whatever the graph's actual bounds turn out to be
  // once the layout settles, instead of a fixed default distance -- fixes
  // the graph rendering tiny-and-off-center in a mostly-empty canvas.
  // Overview-only (`simplified`): Network Explorer's existing default
  // camera framing was never part of what needed fixing here and stays
  // completely untouched.
  //
  // Deliberately fixed real-time delays rather than the library's own
  // `onEngineStop` event: this library only treats a simulation as
  // "stopped" once `d3ForceLayout.alpha()` actually crosses `d3AlphaMin`
  // (0 by default, i.e. disabled) or a 15-second wall-clock fallback
  // elapses (`cooldownTime`) -- confirmed by reading three-forcegraph's
  // source. Even with `d3AlphaMin` re-enabled below, the exact tick where
  // that threshold is crossed varies enough run to run (seeded initial
  // layout, the added cluster + spacing forces) that it wasn't a reliable
  // trigger in practice.
  //
  // Fits THREE TIMES (not once) at increasing delays, all using the same
  // real bbox each time: a single fit at a fixed delay undersized the
  // frame whenever the layout was still visibly expanding at that moment
  // (exactly what strong repulsion does -- it keeps pushing nodes apart
  // for longer than a graph this size used to need), leaving the camera
  // fit to a bbox smaller than what the nodes drifted to afterward --
  // nodes ending up small, off-frame, in a mostly-empty canvas. Re-fitting
  // later corrects itself as the simulation actually settles.
  useEffect(() => {
    if (!simplified) return;
    const timers = [900, 2000, 3400].map((delay) => window.setTimeout(() => fitCamera(500), delay));
    return () => timers.forEach(window.clearTimeout);
  }, [data, size.width, simplified, fitCamera]);

  // Medium-tier labels (see graphIntelligence.ts's `mediumIds`): a compact
  // name label that only becomes visible once the investigator is actually
  // zoomed in close to that node, instead of either "always on" (reserved
  // for the small high-importance tier) or "hover only" (everything else).
  // A cheap 400ms poll over ~10 groups' world position vs. the camera --
  // not a per-frame hook -- so this stays negligible at this graph's scale.
  // Fullscreen (`expanded`) skips the poll entirely and just always shows
  // them, since there's enough room.
  useEffect(() => {
    if (!simplified || expanded) return;
    const worldPos = new THREE.Vector3();
    const id = window.setInterval(() => {
      const fg = fgRef.current;
      const groups = mediumLabelGroupsRef.current;
      if (!fg || groups.length === 0) return;
      const cam = fg.camera?.();
      if (!cam) return;
      const threshold = Math.max(70, lastFitDistanceRef.current * 0.5);
      for (const group of groups) {
        const sprite = (group.userData as any).labelSprite as THREE.Sprite | undefined;
        if (!sprite) continue;
        group.getWorldPosition(worldPos);
        const dist = cam.position.distanceTo(worldPos);
        sprite.visible = dist < threshold;
      }
    }, 400);
    return () => window.clearInterval(id);
  }, [simplified, expanded]);

  const nodeThreeObject = useMemo(() => {
    if (!simplified) return undefined;
    const mediumGroups: THREE.Object3D[] = [];
    mediumLabelGroupsRef.current = mediumGroups;
    return (node: any) => {
      const group = buildNodeDecoration(node, enriched, expanded);
      if (enriched.mediumIds.has(node.id)) mediumGroups.push(group);
      return group;
    };
  }, [simplified, enriched, expanded]);

  return (
    <div ref={containerRef} className="card p-0 overflow-hidden relative w-full min-w-0" style={{ height }}>
      {size.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          width={size.width}
          height={size.height}
          backgroundColor="#0B0F0D"
          showNavInfo={false}
          nodeLabel={(n: any) => `${n.label} · ${titleCaseType(n.type)}`}
          // Overview's "investigation map" (simplified) now colors by real
          // entity type (TYPE_COLOR) same as Explorer -- type is the
          // primary visual cue everywhere, not just in the dense view.
          // Selection state is layered on TOP of type color (brighten the
          // exact active node, dim whatever's outside its neighborhood)
          // rather than replacing type color outright, so "what type is
          // this" never stops being answerable at a glance, focused or not.
          nodeColor={(n: any) => {
            const base = TYPE_COLOR[n.type] ?? FALLBACK_TYPE_COLOR;
            if (simplified) {
              if (!highlightIds) return base;
              if (n.id === activeId) return mixHex(base, "#FFFFFF", 0.45); // the exact selected/hovered node pops
              if (highlightIds.has(n.id)) return base; // its direct neighborhood stays at full, true type color
              return mixHex(base, "#0B0F0D", 0.72); // everything else recedes toward the background
            }
            return highlightIds && !highlightIds.has(n.id) ? "#29352F" : base;
          }}
          nodeOpacity={0.94}
          nodeResolution={12}
          {...(nodeThreeObject ? { nodeThreeObject, nodeThreeObjectExtend: true } : {})}
          linkColor={(l: any) => {
            if (!highlightIds) return simplified ? "rgba(180,188,182,0.32)" : "rgba(167,176,170,0.16)";
            const connected = highlightIds.has(l.source?.id ?? l.source) && highlightIds.has(l.target?.id ?? l.target);
            return connected ? "rgba(224,107,60,0.78)" : "rgba(167,176,170,0.05)";
          }}
          linkWidth={(l: any) => Math.min(0.6 + (l.weight ?? 1) * 0.35, 3)}
          linkOpacity={simplified ? 0.75 : 0.55}
          linkLabel={(l: any) => describeRelation(l.type, l.weight ?? 1)}
          linkDirectionalParticles={0}
          onNodeClick={(n: any) => {
            if (simplified) {
              // One visible "selected" frame -- brighter node, highlighted
              // neighborhood, dimmed rest -- before the existing navigation
              // actually fires, so a click reads as "select, then go" rather
              // than an instant jump away with no visual acknowledgment.
              setClickedId(n.id);
              window.setTimeout(() => onNodeClick?.(n), 220);
            } else {
              onNodeClick?.(n);
            }
          }}
          onNodeHover={(n: any) => setHoveredId(n ? n.id : null)}
          // This library ships `d3AlphaMin: 0`, which disables the normal
          // "the simulation has actually converged" check entirely. Overview-
          // only: Explorer's existing settle/drag feel stays exactly as it
          // was, since it was never part of what needed fixing here.
          d3AlphaMin={simplified ? 0.01 : 0}
          // Overview's snapshot graph isn't a rearrange-by-hand tool (that's
          // Network Explorer's job, unaffected) -- disabling drag there also
          // means a click can never be misread as a micro-drag.
          enableNodeDrag={!simplified}
          controlType="orbit"
          rendererConfig={{ antialias: false, alpha: false, powerPreference: "default" }}
        />
      )}
      <div className="absolute bottom-3 left-3 text-[10px] text-muted font-mono pointer-events-none">
        drag to rotate · scroll to zoom · {simplified ? "hover to identify · " : ""}click a node to focus
      </div>

      {/* Compact intelligence readout for whatever's hovered/selected --
          only in Overview's simplified mode; Explorer has its own dedicated
          entity panel elsewhere and is unaffected. */}
      {activeInfo && (
        <div className="absolute top-3 left-3 max-w-[230px] bg-panel/95 border border-border rounded-lg px-3 py-2.5 pointer-events-none backdrop-blur-sm">
          <div className="text-[10px] uppercase tracking-wide text-muted font-semibold">
            {titleCaseType(activeInfo.entity.type)}
          </div>
          <div className="text-sm text-slate-100 font-medium mt-0.5 truncate" title={activeInfo.entity.label}>
            {activeInfo.entity.label}
          </div>
          <div className="text-[11px] text-muted mt-1">
            {activeInfo.degree} connection{activeInfo.degree === 1 ? "" : "s"} ·{" "}
            {relevanceLabel(activeInfo.importance)} investigation relevance
          </div>
        </div>
      )}

      {/* Compact type legend -- only the types actually present in what's
          rendered, never a fabricated full 8-entry list. */}
      {simplified && graphData.nodes.length > 0 && (
        <GraphLegend types={Array.from(new Set(graphData.nodes.map((n: any) => n.type))).sort()} />
      )}

      {showZoomControls && (
        <div className="absolute bottom-3 right-3 flex flex-col gap-1">
          <button
            onClick={() => dolly(0.8)}
            aria-label="Zoom in"
            className="w-8 h-8 rounded-lg bg-panel/90 border border-border text-slate-300 hover:text-accent hover:border-accent/50 flex items-center justify-center text-base leading-none transition-colors"
          >
            +
          </button>
          <button
            onClick={() => dolly(1.25)}
            aria-label="Zoom out"
            className="w-8 h-8 rounded-lg bg-panel/90 border border-border text-slate-300 hover:text-accent hover:border-accent/50 flex items-center justify-center text-base leading-none transition-colors"
          >
            −
          </button>
          {simplified && (
            <button
              onClick={() => fitCamera(600)}
              aria-label="Reset view"
              title="Reset View"
              className="w-8 h-8 rounded-lg bg-panel/90 border border-border text-slate-300 hover:text-accent hover:border-accent/50 flex items-center justify-center text-sm leading-none transition-colors"
            >
              ⟲
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function GraphLegend({ types }: { types: string[] }) {
  return (
    <div className="absolute top-3 right-3 bg-panel/90 border border-border rounded-lg px-2.5 py-2 space-y-1 pointer-events-none">
      {types.map((t) => (
        <div key={t} className="flex items-center gap-1.5 text-[10px] text-slate-300 leading-none">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: TYPE_COLOR[t] ?? FALLBACK_TYPE_COLOR }}
          />
          {titleCaseType(t)}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Color helpers -- plain sRGB channel blending (not perceptual color space;
// unnecessary precision for a UI accent tint), used only to derive the
// "selected" (brightened) and "dimmed" (toward-background) node color
// variants above from each entity type's real base color, and for the
// importance-halo glow.
// ---------------------------------------------------------------------------

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function mixHex(from: string, to: string, amount: number): string {
  const [r1, g1, b1] = hexToRgb(from);
  const [r2, g2, b2] = hexToRgb(to);
  const r = Math.round(r1 + (r2 - r1) * amount);
  const g = Math.round(g1 + (g2 - g1) * amount);
  const b = Math.round(b1 + (b2 - b1) * amount);
  return `rgb(${r}, ${g}, ${b})`;
}

function hexToRgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ---------------------------------------------------------------------------
// Simplified-mode node decoration: a small canvas-drawn glyph (identity that
// doesn't depend on memorizing a color) on every rendered node, escalating
// to a name label for the medium-importance tier and a full name+type+degree
// label plus a soft "important" halo for the high tier -- see
// graphIntelligence.ts's `importantIds`/`mediumIds`. Attached via
// `nodeThreeObjectExtend`, so the existing type-colored sphere
// (nodeColor/nodeVal) is never replaced, just supplemented -- color stays
// the primary at-a-glance cue, glyph+label the identity confirmation.
// ---------------------------------------------------------------------------

const GLYPH_DRAW: Record<string, (ctx: CanvasRenderingContext2D) => void> = {
  PERSON: (ctx) => {
    ctx.beginPath();
    ctx.arc(32, 22, 9, 0, Math.PI * 2);
    ctx.moveTo(32 + 15, 48);
    ctx.arc(32, 48, 15, 0, Math.PI, true);
    ctx.stroke();
  },
  ORGANIZATION: (ctx) => {
    ctx.strokeRect(16, 18, 32, 30);
    ctx.beginPath();
    ctx.moveTo(24, 26); ctx.lineTo(24, 40);
    ctx.moveTo(32, 26); ctx.lineTo(32, 40);
    ctx.moveTo(40, 26); ctx.lineTo(40, 40);
    ctx.moveTo(12, 48); ctx.lineTo(52, 48);
    ctx.stroke();
  },
  PHONE: (ctx) => {
    ctx.beginPath();
    ctx.moveTo(22, 14);
    ctx.arcTo(20, 14, 20, 16, 3);
    ctx.lineTo(20, 46);
    ctx.arcTo(20, 50, 24, 50, 3);
    ctx.lineTo(40, 50);
    ctx.arcTo(44, 50, 44, 46, 3);
    ctx.lineTo(44, 16);
    ctx.arcTo(44, 14, 40, 14, 3);
    ctx.closePath();
    ctx.moveTo(28, 44); ctx.lineTo(36, 44);
    ctx.stroke();
  },
  FINANCIAL_ACCOUNT: (ctx) => {
    ctx.beginPath();
    ctx.moveTo(14, 24); ctx.lineTo(32, 12); ctx.lineTo(50, 24);
    ctx.stroke();
    ctx.strokeRect(16, 26, 32, 20);
    ctx.beginPath();
    ctx.moveTo(10, 50); ctx.lineTo(54, 50);
    ctx.moveTo(22, 30); ctx.lineTo(22, 42);
    ctx.moveTo(32, 30); ctx.lineTo(32, 42);
    ctx.moveTo(42, 30); ctx.lineTo(42, 42);
    ctx.stroke();
  },
  LOCATION: (ctx) => {
    ctx.beginPath();
    ctx.moveTo(32, 52);
    ctx.bezierCurveTo(32, 52, 16, 34, 16, 24);
    ctx.arc(32, 24, 16, Math.PI, 0, false);
    ctx.bezierCurveTo(48, 34, 32, 52, 32, 52);
    ctx.closePath();
    ctx.moveTo(38, 24);
    ctx.arc(32, 24, 6, 0, Math.PI * 2);
    ctx.stroke();
  },
  VEHICLE: (ctx) => {
    ctx.beginPath();
    ctx.moveTo(12, 38);
    ctx.lineTo(16, 24);
    ctx.lineTo(48, 24);
    ctx.lineTo(52, 38);
    ctx.lineTo(12, 38);
    ctx.closePath();
    ctx.moveTo(10, 38); ctx.lineTo(54, 38);
    ctx.stroke();
    ctx.beginPath(); ctx.arc(20, 42, 4, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(44, 42, 4, 0, Math.PI * 2); ctx.stroke();
  },
  EVENT: (ctx) => {
    ctx.strokeRect(18, 12, 28, 38);
    ctx.beginPath();
    ctx.moveTo(24, 22); ctx.lineTo(40, 22);
    ctx.moveTo(24, 30); ctx.lineTo(40, 30);
    ctx.moveTo(24, 38); ctx.lineTo(34, 38);
    ctx.stroke();
  },
};
GLYPH_DRAW.CASE = GLYPH_DRAW.EVENT;

const glyphTextureCache = new Map<string, THREE.CanvasTexture>();

function glyphTexture(type: string, color: string): THREE.CanvasTexture {
  const key = `${type}:${color}`;
  const cached = glyphTextureCache.get(key);
  if (cached) return cached;

  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  // A small "map pin" badge, one shade lighter than the graph canvas so
  // it still reads as a distinct UI element against the dark background,
  // ringed in the entity's (now-legible-on-dark) type color.
  ctx.fillStyle = "rgba(21, 30, 26, 0.95)";
  ctx.beginPath();
  ctx.arc(32, 32, 30, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(32, 32, 29, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = "#F1F0E9";
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  (GLYPH_DRAW[type] ?? GLYPH_DRAW.EVENT)(ctx);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  glyphTextureCache.set(key, texture);
  return texture;
}

const haloTextureCache = new Map<string, THREE.CanvasTexture>();

/** A soft radial glow, used only behind the high-importance tier's glyph --
 * a static "this one matters" cue independent of hover/click state (so it
 * never needs recomputing on every mouse move), never applied to every node. */
function haloTexture(color: string): THREE.CanvasTexture {
  const cached = haloTextureCache.get(color);
  if (cached) return cached;

  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, hexToRgba(color, 0.5));
  grad.addColorStop(0.55, hexToRgba(color, 0.16));
  grad.addColorStop(1, hexToRgba(color, 0));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  haloTextureCache.set(color, texture);
  return texture;
}

function labelTexture(lines: { text: string; color: string; size: number }[]): { texture: THREE.CanvasTexture; ratio: number } {
  const canvas = document.createElement("canvas");
  const scale = 3;
  const paddingX = 14 * scale;
  const lineGap = 4 * scale;
  const ctx0 = canvas.getContext("2d")!;
  const measured = lines.map((l) => {
    ctx0.font = `${l.size * scale}px 'Inter', sans-serif`;
    return { ...l, width: ctx0.measureText(l.text).width };
  });
  const width = Math.max(...measured.map((l) => l.width)) + paddingX * 2;
  const lineHeight = (Math.max(...lines.map((l) => l.size)) + 6) * scale;
  const height = lineHeight * lines.length + lineGap;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;

  const r = 10 * scale;
  ctx.fillStyle = "rgba(21, 30, 26, 0.94)";
  ctx.beginPath();
  ctx.moveTo(r, 0);
  ctx.arcTo(width, 0, width, height, r);
  ctx.arcTo(width, height, 0, height, r);
  ctx.arcTo(0, height, 0, 0, r);
  ctx.arcTo(0, 0, width, 0, r);
  ctx.closePath();
  ctx.fill();

  measured.forEach((l, i) => {
    ctx.font = `${l.size * scale}px 'Inter', sans-serif`;
    ctx.fillStyle = l.color;
    ctx.textBaseline = "middle";
    ctx.fillText(l.text, paddingX, lineHeight * i + lineHeight / 2 + lineGap / 2);
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return { texture, ratio: width / height };
}

function buildNodeDecoration(node: any, enriched: ReturnType<typeof enrichGraph>, expanded: boolean): THREE.Group {
  const group = new THREE.Group();
  const tierHigh = enriched.importantIds.has(node.id);
  const tierMedium = !tierHigh && enriched.mediumIds.has(node.id);
  // Low tier: a plain type-colored sphere (from nodeColor/nodeVal above),
  // no persistent glyph -- identity is one hover away via `nodeLabel` and
  // the intel panel. Keeping this tier undecorated is deliberate: giving
  // every one of ~30 curated nodes a glyph+label is exactly the labeled-
  // mess the brief warns against.
  if (!tierHigh && !tierMedium) return group;

  const color = TYPE_COLOR[node.type] ?? FALLBACK_TYPE_COLOR;
  const radius = Math.cbrt(Math.max(node.val ?? 1, 0.5)) * 4;

  if (tierHigh) {
    const haloMat = new THREE.SpriteMaterial({ map: haloTexture(color), transparent: true, depthWrite: false });
    const halo = new THREE.Sprite(haloMat);
    const haloSize = radius * 2.6;
    halo.scale.set(haloSize, haloSize, 1);
    group.add(halo);
  }

  const glyphMat = new THREE.SpriteMaterial({ map: glyphTexture(node.type, color), transparent: true, depthWrite: false });
  const glyphSprite = new THREE.Sprite(glyphMat);
  const glyphSize = radius * (tierHigh ? 0.95 : 0.75);
  glyphSprite.scale.set(glyphSize, glyphSize, 1);
  glyphSprite.position.set(0, radius + glyphSize * 0.5, 0);
  group.add(glyphSprite);

  const degree = enriched.nodes.get(node.id)?.degree ?? 0;
  const community = enriched.communities.find((c) => c.hubId === node.id);
  const name = truncateLabel(node.label, tierHigh ? 30 : 22);

  let lines: { text: string; color: string; size: number }[];
  if (tierHigh) {
    const typeLine = `${titleCaseType(node.type)} · ${degree} connection${degree === 1 ? "" : "s"}`;
    lines = community
      ? [
          { text: community.label.toUpperCase(), color: "#C98267", size: 12 },
          { text: name, color: "#F1F0E9", size: 16 },
          { text: typeLine, color: "#A7B0AA", size: 12 },
        ]
      : [
          { text: name, color: "#F1F0E9", size: 16 },
          { text: typeLine, color: "#A7B0AA", size: 12 },
        ];
  } else if (expanded) {
    // Fullscreen has the room to give the medium tier the same detail the
    // high tier always gets, not just the bare name.
    lines = [
      { text: name, color: "#E7E5DC", size: 14 },
      { text: `${degree} connection${degree === 1 ? "" : "s"}`, color: "#A7B0AA", size: 11 },
    ];
  } else {
    lines = [{ text: name, color: "#D8D6CE", size: 13 }];
  }

  const { texture, ratio } = labelTexture(lines);
  const labelMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const labelSprite = new THREE.Sprite(labelMat);
  const labelHeight = radius * (tierHigh ? 0.7 : 0.55);
  labelSprite.scale.set(labelHeight * ratio, labelHeight, 1);
  labelSprite.position.set(0, radius + glyphSize * 0.85 + labelHeight * 0.5, 0);
  // High tier: always on. Medium tier: on in fullscreen (`expanded`), and
  // otherwise toggled by the camera-distance poll above -- starts hidden.
  labelSprite.visible = tierHigh || expanded;
  group.add(labelSprite);
  (group.userData as any).labelSprite = labelSprite;

  return group;
}

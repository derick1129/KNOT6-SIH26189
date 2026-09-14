import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { DUPLICATE_PAIRS, FOCAL_NODE, nodeById, SCENE } from "../sceneData";
import { scrollProgress, smoothstep } from "../scrollProgress";

const COUNT = SCENE.nodes.length;
const HUB_NODES = SCENE.nodes.filter((n) => n.importance > 0.8);

// merge id -> keep id: the entity-resolution motif (ch2, "Rahul Kumar / R.
// Kumar become one resolved entity") -- the merge node slides into the
// keep node's position and shrinks, rather than being destroyed.
const MERGE_INTO = new Map(DUPLICATE_PAIRS.map(({ keep, merge }) => [merge, keep]));
const DUPLICATE_KEEP_IDS = new Set(DUPLICATE_PAIRS.map(({ keep }) => keep));

// Restrained, institutional palette -- the same tokens the rest of the app
// uses (tailwind.config.js), so the cinematic intro and the product it leads
// into read as one design system rather than a separate "trailer" look.
const BASE_COLOR = new THREE.Color("#5b6c8f"); // ordinary entity, dim/precise
const RESOLVED_COLOR = new THREE.Color("#9fb0d1"); // ordinary entity once resolved into the graph
const HUB_COLOR = new THREE.Color("#5b8def"); // important entity (accent2)
const FOCAL_COLOR = new THREE.Color("#22d3ee"); // the one investigative lead (accent)

const _matrix = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _keepPos = new THREE.Vector3();
const _scale = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _euler = new THREE.Euler();
const _color = new THREE.Color();

/**
 * The entity field. Design intent: a forensic/instrument aesthetic, not a
 * "glowing orb" one -- small faceted markers sized strictly by importance,
 * with a second, sparser instanced mesh of thin reticle rings that gives
 * hub/bridge entities real hierarchy (a mark of emphasis, not just "bigger
 * and brighter"). The whole field is always fully opaque: it never fades
 * out, because it has to still be there -- complete -- at chapter 8.
 */
export default function NodeField() {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const ringRef = useRef<THREE.InstancedMesh>(null);

  const geometry = useMemo(() => new THREE.OctahedronGeometry(0.075, 0), []);
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#ffffff",
        emissive: "#0a2530",
        emissiveIntensity: 0.5,
        roughness: 0.4,
        metalness: 0.25,
      }),
    []
  );

  const ringGeometry = useMemo(() => new THREE.RingGeometry(0.14, 0.155, 48), []);
  const ringMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: "#5b8def",
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
        toneMapped: false,
      }),
    []
  );

  useFrame(() => {
    const mesh = meshRef.current;
    const rings = ringRef.current;
    if (!mesh) return;
    const p = scrollProgress.value;
    const now = performance.now();

    // Fragments converge into their resolved knowledge-graph layout across
    // ch0-ch3 (Fragmented -> Fusion -> Entity Resolution -> Relationship
    // Discovery) -- still visibly *emerging* through most of ch3, so the
    // ch4 Graph Reveal shows an already-alive network arriving at
    // completeness, never a graph that suddenly appears from nothing. This
    // is the one and only formation motion -- it never reverses.
    const formation = smoothstep(0.0, 0.46, p);
    // ch5-ch6 investigative highlight window (dolly-in on the lead, then
    // the close pass toward its evidence).
    const highlightWindow = smoothstep(0.6, 0.66, p) * (1 - smoothstep(0.84, 0.9, p));
    // Finale launch + arrival (0.92 -> 1.0): a quiet "coming online" polish
    // -- a touch brighter and a touch larger, never dimmer. This is the
    // payoff, not a fade-out.
    const finalize = smoothstep(0.92, 1.0, p);
    // Entity resolution (ch2): the merge node visibly slides into the keep
    // node and shrinks -- a converging pair, not a scene reset.
    const mergeWindow = smoothstep(0.24, 0.34, p);
    const pulse = 0.5 + 0.5 * Math.sin(now * 0.0028);
    const awaken = 0.5 + 0.5 * Math.sin(now * 0.0009);

    let ringIdx = 0;
    for (let i = 0; i < COUNT; i++) {
      const n = SCENE.nodes[i];
      _pos.lerpVectors(n.fragmentPos, n.graphPos, formation);

      const isFocal = n.id === FOCAL_NODE.id;
      const isHub = n.importance > 0.8;

      // Entity resolution: this specific record is a duplicate/variant of
      // another -- it converges into the surviving entity's position and
      // shrinks to a residual mark, rather than vanishing outright.
      const keepId = MERGE_INTO.get(n.id);
      let mergeShrink = 0;
      if (keepId) {
        const keep = nodeById(keepId);
        if (keep) {
          _keepPos.lerpVectors(keep.fragmentPos, keep.graphPos, formation);
          _pos.lerp(_keepPos, mergeWindow);
          mergeShrink = mergeWindow * 0.78;
        }
      }

      const baseScale = 0.55 + n.importance * 0.6;
      const highlightBoost = isFocal ? highlightWindow * (0.4 + pulse * 0.4) : isHub ? highlightWindow * 0.18 : 0;
      // The keep node of a resolution pair gets a brief pulse right as its
      // duplicate arrives -- the visible "confirmed" moment.
      const resolvedPulse = DUPLICATE_KEEP_IDS.has(n.id)
        ? smoothstep(0.26, 0.3, p) * (1 - smoothstep(0.36, 0.44, p)) * 0.3
        : 0;
      const s = (baseScale + highlightBoost + resolvedPulse + finalize * 0.12) * (1 - mergeShrink);
      _scale.setScalar(s);

      // A faint, slow tumble on faceted markers reads as "precision
      // instrument" rather than "static bead" -- deliberately tiny.
      _euler.set(now * 0.00004 + i, now * 0.00003 + i * 0.7, 0);
      _quat.setFromEuler(_euler);

      _matrix.compose(_pos, _quat, _scale);
      mesh.setMatrixAt(i, _matrix);

      const resolved = BASE_COLOR.clone().lerp(RESOLVED_COLOR, formation);
      _color.copy(isHub || isFocal ? HUB_COLOR : resolved);
      if (isFocal) _color.lerp(FOCAL_COLOR, Math.max(highlightWindow, finalize * 0.6));
      if (finalize > 0) _color.lerp(FOCAL_COLOR, finalize * 0.15 * (isHub || isFocal ? 1 : 0.3));
      mesh.setColorAt(i, _color);

      // Sparse reticle rings: only hub entities get one -- a slow, steady
      // spin of its own (not the marker's tumble) so it reads as a fixed
      // instrument reticle rather than debris, gently breathing in scale.
      if (isHub && rings) {
        const ringScale = 1 + Math.sin(now * 0.0015 + i) * 0.06;
        _scale.setScalar(ringScale);
        _euler.set(0.3, 0, now * 0.00012 + i);
        _quat.setFromEuler(_euler);
        _matrix.compose(_pos, _quat, _scale);
        rings.setMatrixAt(ringIdx, _matrix);
        ringIdx++;
      }
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    // Fully opaque, always -- the network is the constant; only its
    // formation and emphasis change across the scroll, never its presence.
    (mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.5 + finalize * 0.35;

    if (rings) {
      rings.instanceMatrix.needsUpdate = true;
      const ringReveal = smoothstep(0.3, 0.45, p);
      (rings.material as THREE.MeshBasicMaterial).opacity = ringReveal * (0.35 + awaken * 0.15 + finalize * 0.25);
    }
  });

  return (
    <>
      <instancedMesh ref={meshRef} args={[geometry, material, COUNT]} frustumCulled={false} />
      <instancedMesh ref={ringRef} args={[ringGeometry, ringMaterial, HUB_NODES.length]} frustumCulled={false} />
    </>
  );
}

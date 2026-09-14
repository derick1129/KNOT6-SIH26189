import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { nodeById, SCENE, type SceneEdge } from "../sceneData";
import { scrollProgress, smoothstep } from "../scrollProgress";

const TIER_COUNT = 2;
// Each tier reveals slightly after the last -- "connections progressively
// emerge" rather than all at once. Deliberately starts in ch1 (Fusion,
// [0.125, 0.25)) -- the first faint relationships must already be visible
// well before the ch4 Graph Reveal, so the reveal is a pull-back onto an
// already-forming network, never a graph that appears from nothing.
const TIER_WINDOWS: [number, number][] = [
  [0.16, 0.34],
  [0.26, 0.46],
];
// Dim -> bright as weight increases -- weak links stay close to the
// background, strong ones read as deliberate structure, not decoration.
// (Bridges -- the strongest links of all -- get their own solid geometry
// below, not a line tier.)
const TIER_COLORS = ["#28345a", "#3d5aa8"];
const TIER_OPACITY: [number, number] = [0.32, 0.55];

interface Tier {
  edges: { a: THREE.Vector3; b: THREE.Vector3; af: THREE.Vector3; bf: THREE.Vector3 }[];
  geometry: THREE.BufferGeometry;
  positions: Float32Array;
  material: THREE.LineBasicMaterial;
}

const _start = new THREE.Vector3();
const _end = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _mid = new THREE.Vector3();
const _tracePos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _identity = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _traceScale = new THREE.Vector3();
const _matrix = new THREE.Matrix4();
const _up = new THREE.Vector3(0, 1, 0);

/**
 * Non-bridge relationships: thin additive line segments, bucketed by actual
 * weight into a dim tier (incidental chain links) and a brighter tier (hub
 * spokes). Bridges -- the strongest relationships -- are handled separately
 * below as solid cylinder geometry, since "stronger relationship" deserves
 * real visual weight a 1px line can't give it.
 */
export default function EdgeField() {
  const bridgeRef = useRef<THREE.InstancedMesh>(null);
  const traceRef = useRef<THREE.InstancedMesh>(null);

  const { tiers, bridges } = useMemo(() => {
    const buckets: Tier[] = Array.from({ length: TIER_COUNT }, (_, i) => ({
      edges: [],
      geometry: new THREE.BufferGeometry(),
      positions: new Float32Array(0),
      material: new THREE.LineBasicMaterial({
        color: TIER_COLORS[i],
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    }));

    const bridgeList: SceneEdge[] = [];

    SCENE.edges.forEach((e) => {
      if (e.bridge) {
        bridgeList.push(e);
        return;
      }
      const a = nodeById(e.a);
      const b = nodeById(e.b);
      if (!a || !b) return;
      // Bucketed by actual relationship strength, not position in the
      // array -- this is the "weak/dim vs strong/bright" hierarchy.
      const tier = e.weight > 0.45 ? 1 : 0;
      buckets[tier].edges.push({ a: a.graphPos, b: b.graphPos, af: a.fragmentPos, bf: b.fragmentPos });
    });

    buckets.forEach((t) => {
      t.positions = new Float32Array(t.edges.length * 2 * 3);
      t.geometry.setAttribute("position", new THREE.BufferAttribute(t.positions, 3));
    });

    return { tiers: buckets, bridges: bridgeList };
  }, []);

  const bridgeGeometry = useMemo(() => new THREE.CylinderGeometry(1, 1, 1, 6, 1, true), []);
  const bridgeMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: "#22d3ee",
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    []
  );

  // Signal traces: one small pulse of light per bridge relationship,
  // continuously travelling along it -- the "data is actively moving
  // through this system" read the JARVIS-layer brief asks for. Deliberately
  // just one per bridge (a handful, total), not a particle system.
  const traceGeometry = useMemo(() => new THREE.SphereGeometry(0.03, 8, 8), []);
  const traceMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: "#bff4ff",
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    []
  );

  useFrame(() => {
    const p = scrollProgress.value;
    const formation = smoothstep(0.0, 0.46, p);
    const finalize = smoothstep(0.92, 1.0, p);
    // ch5 Investigation Intelligence: the lead's own relationships (mostly
    // landing in the brighter hub-spoke tier, since it's a community hub)
    // read a touch stronger while the camera holds on it -- graph structure
    // itself reorganizing emphasis, not a separate highlight overlay.
    const investigationBoost = smoothstep(0.6, 0.66, p) * (1 - smoothstep(0.84, 0.9, p));

    tiers.forEach((tier, tierIdx) => {
      const [start, end] = TIER_WINDOWS[tierIdx];
      const reveal = smoothstep(start, end, p);
      const arr = tier.positions;
      for (let i = 0; i < tier.edges.length; i++) {
        const { a, b, af, bf } = tier.edges[i];
        const ax = THREE.MathUtils.lerp(af.x, a.x, formation);
        const ay = THREE.MathUtils.lerp(af.y, a.y, formation);
        const az = THREE.MathUtils.lerp(af.z, a.z, formation);
        const bx = THREE.MathUtils.lerp(bf.x, b.x, formation);
        const by = THREE.MathUtils.lerp(bf.y, b.y, formation);
        const bz = THREE.MathUtils.lerp(bf.z, b.z, formation);
        const o = i * 6;
        arr[o] = ax;
        arr[o + 1] = ay;
        arr[o + 2] = az;
        arr[o + 3] = bx;
        arr[o + 4] = by;
        arr[o + 5] = bz;
      }
      tier.geometry.attributes.position.needsUpdate = true;
      tier.geometry.computeBoundingSphere();
      // Always present once revealed -- no end-of-scroll dissolve. The
      // finale only ever adds a touch of brightness, the completed
      // network's "coming online" moment.
      const boost = tierIdx === 1 ? investigationBoost * 0.2 : 0;
      tier.material.opacity = reveal * (TIER_OPACITY[tierIdx] + finalize * 0.2 + boost);
    });

    // Bridge relationships: solid, thin cylinders -- the "strong
    // relationship" / "bridge entity" visual weight a line can't carry --
    // plus one travelling signal trace each.
    const mesh = bridgeRef.current;
    const trace = traceRef.current;
    const now = performance.now();
    if (mesh) {
      // Bridges -- the strongest, structure-defining relationships -- are
      // still completing as ch4's reveal launches (0.4-0.56 spans
      // Relationship Discovery into Graph Reveal), so the pull-back lands
      // on a network that is *finishing* forming, not one already static.
      const reveal = smoothstep(0.4, 0.56, p);
      for (let i = 0; i < bridges.length; i++) {
        const e = bridges[i];
        const a = nodeById(e.a);
        const b = nodeById(e.b);
        if (!a || !b) continue;
        _start.lerpVectors(a.fragmentPos, a.graphPos, formation);
        _end.lerpVectors(b.fragmentPos, b.graphPos, formation);
        const length = _start.distanceTo(_end);
        _mid.copy(_start).add(_end).multiplyScalar(0.5);
        _dir.copy(_end).sub(_start).normalize();
        _quat.setFromUnitVectors(_up, _dir);
        _scale.set(0.007, length, 0.007);
        _matrix.compose(_mid, _quat, _scale);
        mesh.setMatrixAt(i, _matrix);

        if (trace) {
          const travel = (now * 0.00012 + i * 0.37) % 1;
          _tracePos.lerpVectors(_start, _end, travel);
          const flicker = 0.7 + 0.3 * Math.sin(now * 0.01 + i * 2.1);
          _traceScale.setScalar(flicker);
          _matrix.compose(_tracePos, _identity, _traceScale);
          trace.setMatrixAt(i, _matrix);
        }
      }
      mesh.instanceMatrix.needsUpdate = true;
      const pulse = 0.6 + 0.4 * Math.sin(now * 0.0018);
      (mesh.material as THREE.MeshBasicMaterial).opacity = reveal * (0.55 + pulse * 0.2 + finalize * 0.25);
    }
    if (trace) {
      trace.instanceMatrix.needsUpdate = true;
      const reveal = smoothstep(0.44, 0.58, p);
      (trace.material as THREE.MeshBasicMaterial).opacity = reveal * 0.8;
    }
  });

  return (
    <group>
      {tiers.map((t, i) => (
        <lineSegments key={i} geometry={t.geometry} material={t.material} frustumCulled={false} />
      ))}
      <instancedMesh
        ref={bridgeRef}
        args={[bridgeGeometry, bridgeMaterial, Math.max(1, bridges.length)]}
        frustumCulled={false}
      />
      <instancedMesh
        ref={traceRef}
        args={[traceGeometry, traceMaterial, Math.max(1, bridges.length)]}
        frustumCulled={false}
      />
    </group>
  );
}

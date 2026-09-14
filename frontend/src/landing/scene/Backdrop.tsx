import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { scrollProgress, smoothstep } from "../scrollProgress";

/**
 * Ambient scene dressing: a sparse, dim, static starfield for depth, a
 * faint horizontal ops-floor grid beneath the network (the "institutional
 * intelligence platform" ground plane -- Palantir/Bloomberg, not gaming
 * HUD), and one slow rotating scan sweep through the network. Everything
 * here is intentionally restrained -- low opacity, low contrast, no
 * per-frame motion on the stars themselves.
 */
export default function Backdrop() {
  const sweepRef = useRef<THREE.Mesh>(null);
  const gridMaterialRef = useRef<THREE.LineBasicMaterial>(null);

  const starGeometry = useMemo(() => {
    const count = 900;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 30 + Math.random() * 60;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geo;
  }, []);

  const gridGeometry = useMemo(() => {
    const size = 46;
    const divisions = 22;
    const step = size / divisions;
    const half = size / 2;
    const positions: number[] = [];
    for (let i = 0; i <= divisions; i++) {
      const v = -half + i * step;
      positions.push(-half, 0, v, half, 0, v);
      positions.push(v, 0, -half, v, 0, half);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(positions), 3));
    return geo;
  }, []);

  const sweepGeometry = useMemo(() => new THREE.RingGeometry(0.02, 9, 64, 1, 0, Math.PI * 0.32), []);

  useFrame(() => {
    const p = scrollProgress.value;
    // The floor grid only makes sense once the world has a real "ground" to
    // it -- it fades in alongside the ch4 Graph Reveal, then stays,
    // reinforcing scale during the finale rather than competing early on.
    const gridVisible = smoothstep(0.44, 0.58, p) * (0.4 + smoothstep(0.92, 1.0, p) * 0.5);
    if (gridMaterialRef.current) gridMaterialRef.current.opacity = gridVisible * 0.18;

    const sweep = sweepRef.current;
    if (sweep) {
      const active = smoothstep(0.44, 0.56, p);
      sweep.rotation.y = performance.now() * 0.00018;
      (sweep.material as THREE.MeshBasicMaterial).opacity = active * 0.05;
    }
  });

  return (
    <group>
      <points geometry={starGeometry} frustumCulled={false}>
        <pointsMaterial color="#4b5a7d" size={0.05} transparent opacity={0.5} sizeAttenuation />
      </points>

      {/* Ops-floor grid -- deep below the network, near-invisible except as
          a faint sense of a real, measured space beneath the data. */}
      <lineSegments geometry={gridGeometry} position={[0, -7.5, 0]} frustumCulled={false}>
        <lineBasicMaterial ref={gridMaterialRef} color="#3d5aa8" transparent opacity={0} />
      </lineSegments>

      {/* One slow scanning sweep through the network -- a restrained radar
          motif, not a spinning HUD element: barely-there, additive, thin. */}
      <mesh ref={sweepRef} geometry={sweepGeometry} rotation={[-Math.PI / 2, 0, 0]}>
        <meshBasicMaterial
          color="#22d3ee"
          transparent
          opacity={0}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

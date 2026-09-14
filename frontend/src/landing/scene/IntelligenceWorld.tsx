import { Canvas } from "@react-three/fiber";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { Suspense } from "react";
import * as THREE from "three";
import Backdrop from "./Backdrop";
import CameraRig from "./CameraRig";
import EdgeField from "./EdgeField";
import EntityTags from "./EntityTags";
import FocusHighlights from "./FocusHighlights";
import NodeField from "./NodeField";
import ScrollDriver from "./ScrollDriver";

/**
 * Canvas root for the KNOT6 landing scene. One continuous R3F world: no
 * chapter ever mounts/unmounts its own subtree, every component above just
 * reads `scrollProgress.value` and animates continuously -- see
 * scrollProgress.ts for why that matters for "one world, not eight slides".
 */
export default function IntelligenceWorld({ totalHeightPx }: { totalHeightPx: number }) {
  return (
    <Canvas
      dpr={[1, 1.75]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      camera={{ fov: 62, near: 0.1, far: 200, position: [0, 2, 22] }}
      onCreated={({ scene }) => {
        scene.fog = new THREE.FogExp2("#05070c", 0.028);
      }}
    >
      <color attach="background" args={["#05070c"]} />
      <ambientLight intensity={0.35} />
      <pointLight position={[8, 10, 6]} intensity={40} color="#7fd8ff" distance={60} decay={2} />
      <pointLight position={[-10, -4, -8]} intensity={20} color="#3d5aef" distance={60} decay={2} />

      <Suspense fallback={null}>
        <Backdrop />
        <NodeField />
        <EdgeField />
        <FocusHighlights />
        <EntityTags />
      </Suspense>

      <ScrollDriver totalHeightPx={totalHeightPx} />
      <CameraRig />

      {/* Controlled bloom, not excessive glow: a higher threshold so only
          genuinely bright emissive surfaces catch it (hub markers, bridge
          links, the focal ring) -- the ordinary entity field stays crisp
          and precise rather than hazy. */}
      <EffectComposer multisampling={0}>
        <Bloom intensity={0.4} luminanceThreshold={0.3} luminanceSmoothing={0.3} mipmapBlur radius={0.45} />
        <Vignette eskil={false} offset={0.18} darkness={0.75} />
      </EffectComposer>
    </Canvas>
  );
}

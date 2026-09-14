import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import { FOCAL_NODE, SCENE } from "../sceneData";
import { scrollProgress, smoothstep } from "../scrollProgress";

// Hub entities other than the one narrative "investigative lead" (which
// already gets its own richer callout in FocusHighlights) -- a handful of
// small, ambient identifier tags, the ongoing "this is a real tracked
// entity" telemetry the JARVIS-layer brief asks for. Real scene labels, not
// invented placeholder text.
const TAGGED = SCENE.nodes.filter((n) => n.importance > 0.8 && n.id !== FOCAL_NODE.id);

/**
 * Small monospace entity-identifier tags floating beside a few hub nodes.
 * Deliberately sparse (4, not 54) and deliberately dim -- ambient telemetry,
 * not a label on every node. Fades in once the graph has resolved and
 * stays lit through the finale, quietly reinforcing "these are tracked,
 * named entities" for the entire back half of the experience.
 */
export default function EntityTags() {
  const [opacity, setOpacity] = useState(0);
  const last = useRef(0);

  useFrame(() => {
    const p = scrollProgress.value;
    // Dim during the close investigative dolly so they don't compete with
    // the focal callout, back up to full for the wide finale reveal.
    const base = smoothstep(0.44, 0.56, p);
    const recede = smoothstep(0.6, 0.68, p) * (1 - smoothstep(0.87, 0.93, p));
    const next = base * (1 - recede * 0.65);
    if (Math.abs(next - last.current) > 0.02) {
      last.current = next;
      setOpacity(next);
    }
  });

  return (
    <group>
      {TAGGED.map((n) => (
        <Html key={n.id} position={n.graphPos} distanceFactor={10} style={{ pointerEvents: "none" }}>
          <div className="knot-entity-tag" style={{ opacity }}>
            <span className="knot-entity-tag-id">{n.label}</span>
            <span className="knot-entity-tag-meta">CLUSTER {n.community + 1}</span>
          </div>
        </Html>
      ))}
    </group>
  );
}

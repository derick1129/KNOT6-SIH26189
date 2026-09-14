import { useEffect, useState } from "react";
import { SCENE, COMMUNITY_COUNT } from "./sceneData";
import { scrollProgress } from "./scrollProgress";

/**
 * The restrained "JARVIS-layer" chrome: two small corner telemetry blocks
 * that persist across the whole scroll, independent of chapter. Every
 * number shown is real (the scene's actual node/edge/cluster counts, and
 * the real scroll depth) -- this is flavor typography over real state, not
 * fabricated analytics. Polls at a throttled interval rather than every
 * frame: this is deliberately not part of the `useFrame` render loop, since
 * it is DOM text, not a 3D object.
 */
export default function TelemetryOverlay() {
  const [fusion, setFusion] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setFusion(Math.round(scrollProgress.value * 100));
    }, 120);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="knot-telemetry" aria-hidden>
      <div className="knot-telemetry-block knot-telemetry-tl">
        <div className="knot-telemetry-line knot-telemetry-strong">KNOT6 // INTELLIGENCE FUSION ENGINE</div>
        <div className="knot-telemetry-line">CASE REF · OPERATION NEXUS</div>
        <div className="knot-telemetry-row">
          <span>ENTITIES</span>
          <span>{SCENE.nodes.length}</span>
        </div>
        <div className="knot-telemetry-row">
          <span>LINKS</span>
          <span>{SCENE.edges.length}</span>
        </div>
        <div className="knot-telemetry-row">
          <span>CLUSTERS</span>
          <span>{COMMUNITY_COUNT}</span>
        </div>
      </div>

      <div className="knot-telemetry-block knot-telemetry-tr">
        <div className="knot-telemetry-row">
          <span>FUSION</span>
          <span>{fusion}%</span>
        </div>
        <div className="knot-telemetry-bar">
          <div className="knot-telemetry-bar-fill" style={{ width: `${fusion}%` }} />
        </div>
        <div className="knot-telemetry-line knot-telemetry-dim">SYS STATUS · NOMINAL</div>
      </div>
    </div>
  );
}

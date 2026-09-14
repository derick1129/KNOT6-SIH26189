import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import * as THREE from "three";
import { EVIDENCE_NODE, FOCAL_NODE } from "../sceneData";
import { scrollProgress, smoothstep } from "../scrollProgress";

/**
 * Chapters 5-6 (Investigation Intelligence -> Evidence Integrity): a
 * pulsing focus ring on the one consistent "lead" node, a data-annotation
 * callout, and a forensic evidence-verification card. Uses PS-safe
 * language throughout -- "Investigative Lead" / "Requires Investigator
 * Verification", never a guilt/probability claim (see
 * KNOT6_PROJECT_SPECIFICATION.pdf §9/§20 non-goals).
 *
 * Opacity for the two HTML callouts is real React state (unlike the node/
 * edge fields), but updates are threshold-gated in useFrame so it only
 * re-renders a handful of times across the whole scroll, not every frame.
 */
export default function FocusHighlights() {
  const ringRef = useRef<THREE.Mesh>(null);
  const [labelOpacity, setLabelOpacity] = useState(0);
  const [evidenceOpacity, setEvidenceOpacity] = useState(0);
  const lastLabel = useRef(0);
  const lastEvidence = useRef(0);

  useFrame(() => {
    const p = scrollProgress.value;
    const ring = ringRef.current;
    if (ring) {
      // Ch5 (Investigation Intelligence, [0.625, 0.75)) dive onto the lead
      // through ch6 (Evidence Integrity)'s close pass -- retreats before
      // the evidence card takes over, well before the finale launch, so
      // the ring never has to "fight" the reveal.
      const visible = smoothstep(0.6, 0.66, p) * (1 - smoothstep(0.78, 0.84, p));
      const scale = 0.34 + Math.sin(performance.now() * 0.0022) * 0.04;
      ring.scale.setScalar(scale);
      (ring.material as THREE.MeshBasicMaterial).opacity = visible * 0.85;
      ring.position.copy(FOCAL_NODE.graphPos);
    }

    const nextLabel = smoothstep(0.6, 0.67, p) * (1 - smoothstep(0.74, 0.8, p));
    if (Math.abs(nextLabel - lastLabel.current) > 0.015) {
      lastLabel.current = nextLabel;
      setLabelOpacity(nextLabel);
    }
    const nextEvidence = smoothstep(0.74, 0.8, p) * (1 - smoothstep(0.87, 0.92, p));
    if (Math.abs(nextEvidence - lastEvidence.current) > 0.015) {
      lastEvidence.current = nextEvidence;
      setEvidenceOpacity(nextEvidence);
    }
  });

  const evidencePos = (EVIDENCE_NODE ?? FOCAL_NODE).graphPos;

  return (
    <group>
      <mesh ref={ringRef}>
        <torusGeometry args={[1, 0.02, 16, 64]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0} toneMapped={false} />
      </mesh>

      <Html
        position={FOCAL_NODE.graphPos.clone().add(new THREE.Vector3(0.55, 0.3, 0))}
        distanceFactor={8}
        style={{ pointerEvents: "none" }}
      >
        <div style={{ opacity: labelOpacity }} className="knot-callout">
          <div className="knot-callout-title">Investigative Lead</div>
          <div className="knot-callout-sub">Bridges 2 communities · Requires investigator verification</div>
        </div>
      </Html>

      <Html
        position={evidencePos.clone().add(new THREE.Vector3(0.5, 0.25, 0))}
        distanceFactor={7}
        style={{ pointerEvents: "none" }}
      >
        <div style={{ opacity: evidenceOpacity }} className="knot-evidence-card">
          <div className="knot-evidence-row"><span>Evidence ID</span><span>EV-2031-004</span></div>
          <div className="knot-evidence-row"><span>SHA-256</span><span>7f3a…c81e</span></div>
          <div className="knot-evidence-row"><span>Timestamp</span><span>2031-08-14 09:41 IST</span></div>
          <div className="knot-evidence-verified">✓ INTEGRITY VERIFIED</div>
        </div>
      </Html>
    </group>
  );
}

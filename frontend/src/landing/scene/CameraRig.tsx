import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { sampleCameraPath } from "../cameraPath";
import { scrollProgress, smoothstep } from "../scrollProgress";

const WORLD_UP = new THREE.Vector3(0, 1, 0);

/**
 * Drives the camera along the continuous flight path (cameraPath.ts), but
 * deliberately does NOT just interpolate to the sampled position/lookAt.
 * Three things are layered on top so the motion reads as exploring a real
 * space rather than sliding between slides:
 *
 * 1. A helical weave around the path's tangent -- an actual orbital arc
 *    through the network, strongest while "travelling" (ch0-3), quieter
 *    during the reveal orbit, near-still during close investigation holds,
 *    and back for the finale launch.
 * 2. A forward look-ahead gaze blended with the authored lookAt -- the
 *    camera looks where it's flying during travel, and holds the authored
 *    fixed gaze only during deliberate inspection beats.
 * 3. A bank/roll into the weave, tied to the same rotation -- turns feel
 *    physical, not a flat pan.
 */
export default function CameraRig() {
  const { camera } = useThree();
  const targetPos = useRef(new THREE.Vector3());
  const targetLook = useRef(new THREE.Vector3());
  const currentLook = useRef(new THREE.Vector3(0, 0, 0));
  const tangentN = useRef(new THREE.Vector3());
  const right = useRef(new THREE.Vector3());
  const up2 = useRef(new THREE.Vector3());
  const weaveOffset = useRef(new THREE.Vector3());
  const lookAhead = useRef(new THREE.Vector3());

  useFrame((_, delta) => {
    const p = scrollProgress.value;
    const { position, lookAt, tangent } = sampleCameraPath(p);
    targetPos.current.copy(position);
    targetLook.current.copy(lookAt);
    tangentN.current.copy(tangent).normalize();

    // Stable perpendicular basis around the direction of travel -- guards
    // against the degenerate case where tangent is (near) parallel to
    // world-up (straight vertical launches), which would zero out `right`.
    right.current.crossVectors(tangentN.current, WORLD_UP);
    if (right.current.lengthSq() < 1e-4) right.current.set(1, 0, 0);
    right.current.normalize();
    up2.current.crossVectors(right.current, tangentN.current).normalize();

    // Helical weave radius: strong through the ch0-3 travel/dive segments,
    // moderate through the reveal's establishing orbit, quiet during the
    // ch6/ch7 close investigation holds (a steady instrument, not a sway),
    // and back for the finale launch -- an arc, not a straight interpolation.
    const travelPhase = 1 - smoothstep(0.46, 0.5, p);
    const revealPhase = smoothstep(0.5, 0.56, p) * (1 - smoothstep(0.68, 0.75, p));
    const finalePhase = smoothstep(0.9, 0.96, p);
    const weaveRadius = 0.85 * travelPhase + 0.45 * revealPhase + 0.6 * finalePhase;
    const helixAngle = p * Math.PI * 2 * 3.2 + performance.now() * 0.00004;

    if (weaveRadius > 0.001) {
      weaveOffset.current
        .copy(right.current)
        .multiplyScalar(Math.cos(helixAngle) * weaveRadius)
        .addScaledVector(up2.current, Math.sin(helixAngle) * weaveRadius);
      targetPos.current.add(weaveOffset.current);
    }

    // Look-ahead: blend the authored lookAt with a point further along the
    // flight path, so the camera appears to be piloting toward where it's
    // going. Drops out during the two deliberate "hold and inspect" beats
    // (investigative lead, evidence) so those read as fixed examination,
    // not a pass-by.
    const holdInvestigation = smoothstep(0.66, 0.72, p) * (1 - smoothstep(0.75, 0.8, p));
    const holdEvidence = smoothstep(0.8, 0.84, p) * (1 - smoothstep(0.87, 0.9, p));
    const lookAheadWeight = 0.32 * (1 - Math.max(holdInvestigation, holdEvidence));
    if (lookAheadWeight > 0.001) {
      lookAhead.current.copy(position).addScaledVector(tangentN.current, 3.2);
      targetLook.current.lerp(lookAhead.current, lookAheadWeight);
    }

    // Slight drift so the world never feels perfectly static even while
    // scroll is paused -- restrained, not "constant particle motion".
    // Scaled by distance-to-subject so it reads the same whether the camera
    // is inches from one entity or pulled back to frame the whole network.
    const dist = targetPos.current.distanceTo(targetLook.current);
    const driftScale = Math.max(0.15, dist * 0.012);
    const t = performance.now() * 0.00006;
    targetPos.current.x += Math.sin(t) * driftScale;
    targetPos.current.y += Math.cos(t * 0.8) * driftScale * 0.55;

    // At the very end of the scroll the story stops advancing but the world
    // should keep feeling alive: a slow orbit around the completed network
    // instead of a frozen frame, blended in only once the pull-back finale
    // has fully arrived.
    const restingOrbit = smoothstep(0.96, 1.0, p);
    if (restingOrbit > 0) {
      const angle = performance.now() * 0.00004;
      const orbitPoint = targetLook.current
        .clone()
        .add(new THREE.Vector3(Math.cos(angle) * dist, 0, Math.sin(angle) * dist));
      targetPos.current.lerp(orbitPoint, restingOrbit * 0.35);
    }

    const damp = 1 - Math.pow(0.0015, delta);
    camera.position.lerp(targetPos.current, damp);
    currentLook.current.lerp(targetLook.current, damp);
    camera.lookAt(currentLook.current);

    // Bank into the weave -- `lookAt` resets roll to zero every frame (it
    // orients relative to camera.up, which we never touch), so a fresh
    // rotateZ here each frame is a one-shot roll, not a cumulative spin.
    const bankAngle = Math.sin(helixAngle) * weaveRadius * 0.07;
    camera.rotateZ(bankAngle);

    // FOV breathes with the story: a wide punch as the reveal arrives, a
    // long-lens narrow during the close investigative/evidence holds, and
    // the widest frame of all for the finale pull-back -- so the payoff
    // reads as "everything is now visible", not just "camera moved back".
    const wideReveal = smoothstep(0.5, 0.56, p) * (1 - smoothstep(0.6, 0.66, p)) * 10;
    const narrowInspect = smoothstep(0.66, 0.72, p) * (1 - smoothstep(0.86, 0.9, p)) * 14;
    const wideFinale = smoothstep(0.9, 1.0, p) * 16;
    const revealFov = 62 + wideReveal - narrowInspect + wideFinale;
    if (camera instanceof THREE.PerspectiveCamera) {
      camera.fov += (revealFov - camera.fov) * damp;
      camera.updateProjectionMatrix();
    }
  });

  return null;
}

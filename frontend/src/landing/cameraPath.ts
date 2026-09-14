import * as THREE from "three";
import { FOCAL_NODE, EVIDENCE_NODE, GRAPH_BOUNDS, communityCentroid, nodeById, SCENE } from "./sceneData";

/**
 * One continuous camera flight through the whole scroll -- not eight
 * point-to-point cuts. 17 keyframes, evenly spaced in *story* time (every
 * 1/16th of the scroll) but deliberately UNEVEN in world-space distance:
 * close together where the camera should slow into a held, deliberate shot
 * (an orbit, a close inspection), far apart where it should surge through
 * open space. That authored spacing -- not a formula -- is what produces
 * real acceleration/deceleration on a Catmull-Rom spline.
 *
 * Every keyframe targets something that actually exists in the scene
 * (a community centroid, the focal lead, the evidence node, an actual
 * bridge relationship's midpoint) rather than an arbitrary point in space,
 * so the route reads as investigating a real place, not sliding along a
 * decorative curve. CameraRig.tsx layers a helical weave, banking, and a
 * look-ahead gaze on top of this path -- this file only supplies the spine.
 */

const focal = FOCAL_NODE.graphPos;
const evidence = (EVIDENCE_NODE ?? FOCAL_NODE).graphPos;
const clusterA = communityCentroid(0);
const clusterB = communityCentroid(1);
const clusterC = communityCentroid(2);
const { center: graphCenter, radius: graphRadius } = GRAPH_BOUNDS;

const firstBridge = SCENE.edges.find((e) => e.bridge);
const bridgeMid = firstBridge
  ? nodeById(firstBridge.a)!.graphPos.clone().add(nodeById(firstBridge.b)!.graphPos).multiplyScalar(0.5)
  : graphCenter.clone();

// The two "pull back and reveal everything" beats -- ch4's mid-chapter
// reveal arrival, and the finale -- share the same framing language
// (elevated, distant enough to hold the whole graph) so both read
// unmistakably as "here is the complete network", not just "camera moved".
const wideShot = (angle: THREE.Vector3) => graphCenter.clone().add(angle);
const revealPosition = wideShot(new THREE.Vector3(graphRadius * 0.5, graphRadius * 1.1, graphRadius * 1.5));
const orbitPosition = wideShot(new THREE.Vector3(-graphRadius * 0.9, graphRadius * 0.7, graphRadius * 1.1));
const finalePosition = wideShot(new THREE.Vector3(graphRadius * 0.55, graphRadius * 0.62, graphRadius * 1.35));
const finaleLookAt = graphCenter.clone().add(new THREE.Vector3(0, graphRadius * 0.05, 0));

// 17 keyframes at i/16 -- chapter i (of 8) starts at i/8 = keyframe index 2i,
// so every even index lands exactly on a chapter boundary and every odd
// index is a mid-chapter beat (a close pass, a dive, an orbit hold).
const positionKeyframes = [
  new THREE.Vector3(0, 4, 26), // 0.0000 ch0 start -- wide, distant, surveying the chaos
  new THREE.Vector3(9, 3, 20), // 0.0625 ch0 mid -- banking in, camera begins travelling through the data
  new THREE.Vector3(5, 2.6, 17), // 0.1250 ch1 start (Fusion) -- fragments visibly drifting together around us
  clusterB.clone().add(new THREE.Vector3(6, 2.4, 6)), // 0.1875 ch1 mid -- arcing toward a forming cluster
  clusterA.clone().add(new THREE.Vector3(-2.4, 1.1, 2.6)), // 0.2500 ch2 start (Entity Resolution) -- close orbit, watching entities resolve
  clusterA.clone().lerp(clusterB, 0.5).add(new THREE.Vector3(0, 1.6, 3)), // 0.3125 ch2 mid -- corridor pass toward the next cluster
  clusterC.clone().add(new THREE.Vector3(3, 1.8, -2.4)), // 0.3750 ch3 start (Relationship Discovery) -- diving inside the network
  bridgeMid.clone().add(new THREE.Vector3(1.6, 0.65, 1.9)), // 0.4375 ch3 mid -- close pass along a real bridge relationship
  wideShot(new THREE.Vector3(0.4, graphRadius * 0.55, graphRadius * 0.75)), // 0.5000 ch4 start (Graph Reveal) -- launching outward
  revealPosition, // 0.5625 ch4 mid -- THE REVEAL: pulled back, the complete network in frame
  orbitPosition, // 0.6250 ch5 start (Investigation Intelligence) -- orbiting the reveal, beginning to angle back in
  focal.clone().add(new THREE.Vector3(4.5, 2.6, 5.5)), // 0.6875 ch5 mid -- diving back toward the investigative lead
  focal.clone().add(new THREE.Vector3(1.1, 0.45, 1.7)), // 0.7500 ch6 start (Evidence Integrity) -- travelling the relationship corridor
  evidence.clone().add(new THREE.Vector3(1.3, 0.6, 2.0)), // 0.8125 ch6 mid -- closing on the evidence source
  evidence.clone().add(new THREE.Vector3(0.7, 0.35, 1.1)), // 0.8750 ch7 start (KNOT6) -- closest point, integrity metadata
  wideShot(new THREE.Vector3(graphRadius * 0.3, graphRadius * 0.42, graphRadius * 0.95)), // 0.9375 ch7 mid -- the final launch outward begins
  finalePosition, // 1.0000 finale -- pulled all the way back to the complete, living network
];

const lookAtKeyframes = [
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(2, 0, 2),
  new THREE.Vector3(0, 0, 0),
  clusterB,
  clusterA,
  clusterB,
  clusterC,
  bridgeMid,
  graphCenter,
  graphCenter,
  graphCenter,
  focal,
  focal,
  evidence,
  evidence,
  graphCenter,
  finaleLookAt,
];

const positionCurve = new THREE.CatmullRomCurve3(positionKeyframes, false, "catmullrom", 0.5);
const lookAtCurve = new THREE.CatmullRomCurve3(lookAtKeyframes, false, "catmullrom", 0.5);

const _pos = new THREE.Vector3();
const _look = new THREE.Vector3();
const _tangent = new THREE.Vector3();

export function sampleCameraPath(
  t: number
): { position: THREE.Vector3; lookAt: THREE.Vector3; tangent: THREE.Vector3 } {
  const clamped = Math.min(1, Math.max(0, t));
  positionCurve.getPoint(clamped, _pos);
  lookAtCurve.getPoint(clamped, _look);
  // Direction of travel along the spine -- CameraRig uses this for banking
  // and a forward look-ahead gaze, not just this file's own lookAt curve.
  const tangentT = Math.min(0.999, Math.max(0.001, clamped));
  positionCurve.getTangent(tangentT, _tangent);
  if (_tangent.lengthSq() < 1e-6) _tangent.set(0, 0, -1);
  return { position: _pos, lookAt: _look, tangent: _tangent };
}

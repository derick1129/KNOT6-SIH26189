/**
 * Entity-type color palette shared by every graph surface (NetworkGraph3D's
 * Network Explorer / non-simplified mode, plus small type-dots elsewhere:
 * Entities.tsx, Case Intelligence's key-entity list, EntityIntelPanel) --
 * one source of truth, no risk of a hand-copied second palette drifting out
 * of sync. Deliberately dependency-free so importing it never pulls in the
 * heavy 3D rendering library.
 *
 * Muted earth tones, not saturated rainbow hues -- coherent with KNOT6's
 * dark forest/graphite/orange identity while staying mutually
 * distinguishable at a glance, which Network Explorer's dense, unlabeled
 * view genuinely depends on (see NetworkGraph3D.tsx: only `simplified`
 * mode gets glyphs + labels; Explorer's full graph identifies entities by
 * color alone). Bright enough to actually read as small spheres against
 * the near-black graph canvas -- a muted tone tuned for a light canvas
 * (the previous pass's mistake) is often too dark to see at all against
 * near-black. The Overview's `simplified` graph does NOT use this map --
 * it uses a separate state-based (normal/highlighted) color scheme
 * instead, since an airy "investigation map" communicates importance and
 * selection, not type.
 */
// Retuned for stronger hue separation (the original set put PERSON/LOCATION
// both in the same green family, and VEHICLE/ORGANIZATION both in the same
// orange-brown family -- too close to read apart at a glance in a dense or
// small-node view). Same 8 keys, same "muted earth tone, not rainbow" brief;
// each type now sits in a visually distinct hue family (green / teal / blue
// / violet / grey / clay-brown / rust-orange / gold) so color alone can
// still carry type identity even before a glyph is legible.
export const TYPE_COLOR: Record<string, string> = {
  PERSON: "#5FA87C", PHONE: "#5B84B8", VEHICLE: "#A67C5B", LOCATION: "#4FA6A6",
  ORGANIZATION: "#C2632E", FINANCIAL_ACCOUNT: "#D8B23C", EVENT: "#9B8FBF", CASE: "#9C9689",
};

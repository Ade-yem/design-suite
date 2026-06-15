/**
 * @file connectivity.ts
 * @description Derives structural connectivity between members from their
 * plan-space geometry, so the analysis drawer can show "how other members
 * interact with this member" along with the force/reaction each transfers.
 *
 * The backend does not expose an explicit connectivity graph, so we infer it:
 * two members are connected when a node of one (endpoint / centre / polygon
 * vertex) lies within a small world-space tolerance of the other's node or
 * spanning edge. The relationship label is inferred from the member-type pair
 * (a column under a beam end "supports" it; a beam meeting a beam "frames in";
 * a slab over a beam "bears on" it).
 *
 * All coordinates are DXF world space in millimetres (see types/canvas.ts).
 */

import type { GeometricMember, Point } from "@/types/canvas";
import type { MemberFullAnalysisResult } from "@/types/analysis";

/** Connection tolerance in mm — two nodes within this distance are coincident. */
const NODE_TOLERANCE_MM = 250;

export type ConnectionRelation =
  | "supports"
  | "supported_by"
  | "frames_in"
  | "bears_on"
  | "carries"
  | "connected";

export interface MemberConnection {
  member_id: string;
  member_type: GeometricMember["member_type"];
  /** Relationship of the *other* member to the selected member. */
  relation: ConnectionRelation;
  /** Human-readable location hint, e.g. "left end", "midspan", "@ node". */
  location: string;
  /** Force transferred across the joint, if derivable (kN or kNm). */
  force?: { value: number; unit: "kN" | "kNm" | "kN/m" };
}

const RELATION_LABEL: Record<ConnectionRelation, string> = {
  supports: "supports",
  supported_by: "supported by",
  frames_in: "frames in",
  bears_on: "bears on",
  carries: "carries",
  connected: "connected",
};

export function relationLabel(rel: ConnectionRelation): string {
  return RELATION_LABEL[rel];
}

// ── Geometry helpers ──────────────────────────────────────────────────────────

function dist(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** Collect the salient nodes of a member (endpoints, centre, polygon corners). */
function memberNodes(m: GeometricMember): Point[] {
  const nodes: Point[] = [];
  if (m.start_point) nodes.push(m.start_point);
  if (m.end_point) nodes.push(m.end_point);
  if (m.center_point) nodes.push(m.center_point);
  if (m.boundary_polygon) nodes.push(...m.boundary_polygon);
  return nodes;
}

/** Distance from a point to a member's spanning segment (beams/walls). */
function distToSpan(p: Point, m: GeometricMember): number {
  if (!m.start_point || !m.end_point) return Infinity;
  const { x: x1, y: y1 } = m.start_point;
  const { x: x2, y: y2 } = m.end_point;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return dist(p, m.start_point);
  const t = Math.max(
    0,
    Math.min(1, ((p.x - x1) * dx + (p.y - y1) * dy) / lenSq)
  );
  return dist(p, { x: x1 + t * dx, y: y1 + t * dy });
}

/**
 * Classify where, along the selected beam's span, the contact node falls.
 */
function spanLocation(selected: GeometricMember, node: Point): string {
  if (!selected.start_point || !selected.end_point) return "@ node";
  const dStart = dist(node, selected.start_point);
  const dEnd = dist(node, selected.end_point);
  const span = dist(selected.start_point, selected.end_point) || 1;
  if (dStart < span * 0.2) return "left end";
  if (dEnd < span * 0.2) return "right end";
  return "midspan";
}

// ── Relationship inference ────────────────────────────────────────────────────

function inferRelation(
  selected: GeometricMember,
  other: GeometricMember
): ConnectionRelation {
  const s = selected.member_type;
  const o = other.member_type;

  if (s === "beam") {
    if (o === "column" || o === "wall" || o === "footing") return "supported_by";
    if (o === "slab") return "carries";
    if (o === "beam") return "frames_in";
  }
  if (s === "column") {
    if (o === "beam") return "supports";
    if (o === "footing") return "supported_by";
    if (o === "slab") return "supports";
  }
  if (s === "slab") {
    if (o === "beam" || o === "wall") return "bears_on";
    if (o === "column") return "bears_on";
  }
  if (s === "wall") {
    if (o === "beam" || o === "slab") return "supports";
    if (o === "footing") return "supported_by";
  }
  if (s === "footing") {
    if (o === "column" || o === "wall") return "supports";
  }
  return "connected";
}

/**
 * Derive the force transferred across the joint.
 *
 * - When the *other* member supports the selected one (column/wall/footing),
 *   we report the selected member's end reaction.
 * - When the selected member supports the other, we report the other member's
 *   reaction (load it brings down).
 * - Beam–beam framing reports the incoming member's peak shear.
 */
function inferForce(
  relation: ConnectionRelation,
  selectedResult?: MemberFullAnalysisResult,
  otherResult?: MemberFullAnalysisResult,
  location?: string
): MemberConnection["force"] {
  const pickReaction = (
    res: MemberFullAnalysisResult | undefined,
    loc?: string
  ): number | undefined => {
    if (!res?.reactions_kN?.length) return undefined;
    if (loc === "right end" && res.reactions_kN.length > 1)
      return Math.abs(res.reactions_kN[res.reactions_kN.length - 1]);
    return Math.abs(res.reactions_kN[0]);
  };

  switch (relation) {
    case "supported_by": {
      const r = pickReaction(selectedResult, location);
      return r != null ? { value: r, unit: "kN" } : undefined;
    }
    case "supports":
    case "carries": {
      const r = pickReaction(otherResult);
      return r != null ? { value: r, unit: "kN" } : undefined;
    }
    case "frames_in": {
      const v = otherResult?.stress_resultants?.V_max_kN;
      return v != null ? { value: Math.abs(v), unit: "kN" } : undefined;
    }
    case "bears_on": {
      const r = pickReaction(selectedResult);
      return r != null ? { value: r, unit: "kN" } : undefined;
    }
    default:
      return undefined;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Find members structurally connected to the selected member.
 *
 * @param selectedId    - The member being inspected.
 * @param members       - All members in the model (from canvasStore).
 * @param analysisById  - Map of member_id → analysis result (for force values).
 * @returns Connections sorted by transferred force (descending).
 */
export function findConnectedMembers(
  selectedId: string,
  members: GeometricMember[],
  analysisById: Map<string, MemberFullAnalysisResult>
): MemberConnection[] {
  const selected = members.find((m) => m.member_id === selectedId);
  if (!selected) return [];

  const selectedNodes = memberNodes(selected);
  const selectedResult = analysisById.get(selectedId);
  const connections: MemberConnection[] = [];

  for (const other of members) {
    if (other.member_id === selectedId) continue;

    const otherNodes = memberNodes(other);

    // Closest contact between any node pair, plus node-to-span proximity.
    let minDist = Infinity;
    let contact: Point | null = null;
    for (const sn of selectedNodes) {
      for (const on of otherNodes) {
        const d = dist(sn, on);
        if (d < minDist) {
          minDist = d;
          contact = sn;
        }
      }
      const dSpan = distToSpan(sn, other);
      if (dSpan < minDist) {
        minDist = dSpan;
        contact = sn;
      }
    }
    for (const on of otherNodes) {
      const dSpan = distToSpan(on, selected);
      if (dSpan < minDist) {
        minDist = dSpan;
        contact = on;
      }
    }

    if (minDist > NODE_TOLERANCE_MM || !contact) continue;

    const relation = inferRelation(selected, other);
    const location = spanLocation(selected, contact);
    const force = inferForce(
      relation,
      selectedResult,
      analysisById.get(other.member_id),
      location
    );

    connections.push({
      member_id: other.member_id,
      member_type: other.member_type,
      relation,
      location,
      force,
    });
  }

  return connections.sort(
    (a, b) => (b.force?.value ?? 0) - (a.force?.value ?? 0)
  );
}

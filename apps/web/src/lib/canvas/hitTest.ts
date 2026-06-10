/**
 * @file hitTest.ts
 * @description Mouse-to-member hit detection for the interactive canvas.
 *
 * Given a screen-space mouse point, determines which structural member
 * (if any) is under the cursor. Uses type-specific hit regions:
 * - Beams: axis-aligned rectangle with tolerance padding.
 * - Columns: section-size square with tolerance padding.
 * - Slabs/Voids: bounding rectangle.
 * - Walls: line proximity test.
 *
 * @module canvas/hitTest
 */

import type { GeometricMember, Point } from "@/types/canvas";
import { worldToScreen } from "./transform";

/** Hit detection tolerance in screen pixels (for thin elements). */
const HIT_TOLERANCE_PX = 5;

/**
 * Test if a screen-space point falls within a given rectangle
 * (with tolerance padding).
 *
 * @param px - Screen X of the test point.
 * @param py - Screen Y of the test point.
 * @param rx - Rectangle left edge.
 * @param ry - Rectangle top edge.
 * @param rw - Rectangle width.
 * @param rh - Rectangle height.
 * @param tolerance - Extra padding in pixels.
 * @returns True if the point is inside the padded rectangle.
 */
function pointInRect(
  px: number,
  py: number,
  rx: number,
  ry: number,
  rw: number,
  rh: number,
  tolerance: number,
): boolean {
  return (
    px >= rx - tolerance &&
    px <= rx + rw + tolerance &&
    py >= ry - tolerance &&
    py <= ry + rh + tolerance
  );
}

/**
 * Compute the perpendicular distance from a point to a line segment.
 *
 * @param px - Test point X.
 * @param py - Test point Y.
 * @param x1 - Line start X.
 * @param y1 - Line start Y.
 * @param x2 - Line end X.
 * @param y2 - Line end Y.
 * @returns Distance in pixels from the point to the nearest point on the segment.
 */
function pointToLineDistance(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;

  if (lenSq === 0) {
    // Degenerate line segment (zero length)
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  // Project point onto the line, clamped to segment
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
}

/**
 * Get the screen-space hit rectangle for a beam member.
 *
 * @param member       - The beam member.
 * @param zoom         - Current zoom level.
 * @param pan          - Current pan offset.
 * @param canvasHeight - Canvas height in pixels.
 * @returns Hit rectangle {x, y, w, h} in screen pixels.
 */
function beamHitRect(
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
): { x: number; y: number; w: number; h: number } {
  const s = worldToScreen(member.start, zoom, pan, canvasHeight);
  const e = worldToScreen(member.end, zoom, pan, canvasHeight);
  const halfWidth = (member.meta.b_mm * zoom) / 2;

  const dx = Math.abs(e.x - s.x);
  const dy = Math.abs(e.y - s.y);

  if (dx >= dy) {
    const x = Math.min(s.x, e.x);
    const w = Math.abs(e.x - s.x);
    const centerY = (s.y + e.y) / 2;
    return { x, y: centerY - halfWidth, w, h: halfWidth * 2 };
  } else {
    const y = Math.min(s.y, e.y);
    const h = Math.abs(e.y - s.y);
    const centerX = (s.x + e.x) / 2;
    return { x: centerX - halfWidth, y, w: halfWidth * 2, h };
  }
}

/**
 * Test if a screen-space mouse point hits a specific member.
 *
 * @param mouseScreen  - Mouse position in screen pixels.
 * @param member       - The member to test against.
 * @param zoom         - Current zoom level.
 * @param pan          - Current pan offset.
 * @param canvasHeight - Canvas height in pixels.
 * @returns True if the mouse point is within the member's hit region.
 */
function hitTestMember(
  mouseScreen: Point,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
): boolean {
  const { x: mx, y: my } = mouseScreen;

  switch (member.member_type) {
    case "beam": {
      const rect = beamHitRect(member, zoom, pan, canvasHeight);
      return pointInRect(
        mx,
        my,
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        HIT_TOLERANCE_PX,
      );
    }

    case "column":
    case "footing": {
      const center = worldToScreen(member.start, zoom, pan, canvasHeight);
      const w = Math.max(member.meta.b_mm * zoom, 4);
      const h = Math.max(member.meta.h_mm * zoom, 4);
      return pointInRect(
        mx,
        my,
        center.x - w / 2,
        center.y - h / 2,
        w,
        h,
        HIT_TOLERANCE_PX,
      );
    }

    case "slab":
    case "void":
    case "staircase": {
      if (member.boundary_polygon && member.boundary_polygon.length >= 3) {
        const pts = member.boundary_polygon.map((p) =>
          worldToScreen(p, zoom, pan, canvasHeight),
        );
        return pointInCustomPolygon(mx, my, pts);
      }

      // Fallback bounding box logic for generic blocks
      const s = worldToScreen(member.start, zoom, pan, canvasHeight);
      const e = worldToScreen(member.end, zoom, pan, canvasHeight);
      const rx = Math.min(s.x, e.x);
      const ry = Math.min(s.y, e.y);
      const rw = Math.abs(e.x - s.x);
      const rh = Math.abs(e.y - s.y);
      return pointInRect(mx, my, rx, ry, rw, rh, HIT_TOLERANCE_PX);
    }

    case "wall": {
      const s = worldToScreen(member.start, zoom, pan, canvasHeight);
      const e = worldToScreen(member.end, zoom, pan, canvasHeight);
      const thickness = Math.max(member.meta.b_mm * zoom, 3);
      const dist = pointToLineDistance(mx, my, s.x, s.y, e.x, e.y);
      return dist <= thickness / 2 + HIT_TOLERANCE_PX;
    }

    default:
      return false;
  }
}

/**
 * Find the topmost member under the mouse cursor.
 *
 * Members are tested in reverse order (last drawn = topmost) so that
 * visually overlapping members behave intuitively — the one on top
 * is selected first.
 *
 * Priority order when multiple members overlap:
 * 1. Columns (smallest visual footprint, hardest to click)
 * 2. Beams
 * 3. Walls
 * 4. Slabs/Voids (largest visual footprint)
 *
 * @param mouseScreen  - Mouse position in screen pixels.
 * @param members      - Array of parsed structural members.
 * @param zoom         - Current zoom level.
 * @param pan          - Current pan offset.
 * @param canvasHeight - Canvas height in pixels.
 * @returns Member ID of the topmost hit member, or null if no hit.
 */
export function hitTestMembers(
  mouseScreen: Point,
  members: GeometricMember[],
  zoom: number,
  pan: Point,
  canvasHeight: number,
): string | null {
  // Priority buckets: columns first, then beams, walls, then area elements
  const priorityOrder: Record<string, number> = {
    column: 0,
    beam: 1,
    wall: 2,
    footing: 3,
    slab: 4,
    void: 5,
    staircase: 5,
  };

  // Sort by priority (highest priority = lowest number = tested first)
  const sorted = [...members].sort(
    (a, b) =>
      (priorityOrder[a.member_type] ?? 9) - (priorityOrder[b.member_type] ?? 9),
  );

  for (const member of sorted) {
    if (hitTestMember(mouseScreen, member, zoom, pan, canvasHeight)) {
      return member.member_id;
    }
  }

  return null;
}

function pointInCustomPolygon(x: number, y: number, points: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const xi = points[i].x,
      yi = points[i].y;
    const xj = points[j].x,
      yj = points[j].y;

    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

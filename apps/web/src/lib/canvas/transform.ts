/**
 * @file transform.ts
 * @description Pure coordinate-transformation functions for the canvas engine.
 *
 * The canvas uses a Transformation Matrix that converts DXF world coordinates
 * (millimetres, Y-up) to HTML5 Canvas screen coordinates (pixels, Y-down).
 *
 * Transformation pipeline:
 * ```
 *   DXF (mm, Y↑)  →  translate(panX, panY) + scale(zoom) + Y-flip  →  Screen (px, Y↓)
 * ```
 *
 * The Y-axis is inverted because DXF uses a standard Cartesian system
 * (positive Y points upward) while the HTML5 Canvas uses screen coordinates
 * (positive Y points downward).
 *
 * @module canvas/transform
 */

import type { Point, BoundingBox, GeometricMember } from "@/types/canvas";

/**
 * Convert a DXF world-space point to canvas screen-space coordinates.
 *
 * @param point        - Point in DXF coordinate space (mm).
 * @param zoom         - Current zoom level (DXF units per pixel).
 * @param pan          - Current pan offset in screen pixels.
 * @param canvasHeight - Height of the canvas element in pixels.
 * @returns The corresponding point in screen-space pixels.
 *
 * @example
 * ```ts
 * const screenPt = worldToScreen({ x: 5000, y: 3000 }, 0.1, { x: 50, y: 400 }, 800);
 * // screenPt.x = 5000 * 0.1 + 50 = 550
 * // screenPt.y = 800 - (3000 * 0.1 + 400) = 800 - 700 = 100
 * ```
 */
export function worldToScreen(
  point: Point,
  zoom: number,
  pan: Point,
  canvasHeight: number
): Point {
  return {
    x: point.x * zoom + pan.x,
    y: canvasHeight - (point.y * zoom + pan.y),
  };
}

/**
 * Convert a canvas screen-space point back to DXF world-space coordinates.
 *
 * This is the inverse of `worldToScreen` and is used for:
 * - Displaying live DXF coordinates in the coordinate readout
 * - Hit-testing mouse events against member geometry
 * - Zoom-toward-cursor calculations
 *
 * @param screenPt     - Point in screen-space pixels.
 * @param zoom         - Current zoom level.
 * @param pan          - Current pan offset in screen pixels.
 * @param canvasHeight - Height of the canvas element in pixels.
 * @returns The corresponding point in DXF world-space (mm).
 */
export function screenToWorld(
  screenPt: Point,
  zoom: number,
  pan: Point,
  canvasHeight: number
): Point {
  if (zoom === 0) return { x: 0, y: 0 };
  return {
    x: (screenPt.x - pan.x) / zoom,
    y: (canvasHeight - screenPt.y - pan.y) / zoom,
  };
}

/**
 * Compute the axis-aligned bounding box enclosing all structural members.
 *
 * Takes into account member start/end points, column section sizes,
 * and slab extent dimensions (Lx, Ly) to ensure the bounding box
 * fully contains all rendered geometry.
 *
 * @param members - Array of parsed structural members.
 * @returns Bounding box in DXF space, or null if no members exist.
 */
export function computeBounds(
  members: GeometricMember[]
): BoundingBox | null {
  if (members.length === 0) return null;

  let xMin = Infinity;
  let yMin = Infinity;
  let xMax = -Infinity;
  let yMax = -Infinity;

  const expand = (px: number, py: number) => {
    if (px < xMin) xMin = px;
    if (py < yMin) yMin = py;
    if (px > xMax) xMax = px;
    if (py > yMax) yMax = py;
  };

  for (const m of members) {
    expand(m.start.x, m.start.y);
    expand(m.end.x, m.end.y);

    // Columns: expand by their section dimensions
    if (m.member_type === "column" && m.meta.b_mm && m.meta.h_mm) {
      const halfB = m.meta.b_mm / 2;
      const halfH = m.meta.h_mm / 2;
      expand(m.start.x - halfB, m.start.y - halfH);
      expand(m.start.x + halfB, m.start.y + halfH);
    }

    // Slabs: expand by their full extent
    if (m.member_type === "slab" && m.meta.Lx && m.meta.Ly) {
      const cx = (m.start.x + m.end.x) / 2;
      const cy = (m.start.y + m.end.y) / 2;
      expand(cx - m.meta.Lx / 2, cy - m.meta.Ly / 2);
      expand(cx + m.meta.Lx / 2, cy + m.meta.Ly / 2);
    }

    // Beams: expand by their cross-section width perpendicular to span
    if (m.member_type === "beam" && m.meta.b_mm) {
      const halfB = m.meta.b_mm / 2;
      expand(m.start.x - halfB, m.start.y - halfB);
      expand(m.end.x + halfB, m.end.y + halfB);
    }
  }

  return { xMin, yMin, xMax, yMax };
}

/**
 * Compute the zoom level and pan offset that centers all members
 * within the canvas viewport with padding.
 *
 * @param bounds  - Bounding box of all members in DXF space.
 * @param canvasW - Canvas width in pixels.
 * @param canvasH - Canvas height in pixels.
 * @param padding - Fraction of viewport reserved as padding (default 0.1 = 10%).
 * @returns Object with computed zoom level and pan offset.
 *
 * @example
 * ```ts
 * const { zoom, pan } = computeFitTransform(bounds, 1200, 800);
 * canvasStore.setZoom(zoom);
 * canvasStore.setPan(pan);
 * ```
 */
export function computeFitTransform(
  bounds: BoundingBox,
  canvasW: number,
  canvasH: number,
  padding = 0.1
): { zoom: number; pan: Point } {
  const dxfW = bounds.xMax - bounds.xMin;
  const dxfH = bounds.yMax - bounds.yMin;

  // Prevent division by zero for degenerate bounding boxes
  if (dxfW <= 0 || dxfH <= 0) {
    return { zoom: 1, pan: { x: canvasW / 2, y: canvasH / 2 } };
  }

  const usableW = canvasW * (1 - 2 * padding);
  const usableH = canvasH * (1 - 2 * padding);

  const zoom = Math.min(usableW / dxfW, usableH / dxfH);

  // Center the geometry: compute pan so bounding-box center maps to canvas center
  const centerDxfX = bounds.xMin + dxfW / 2;
  const centerDxfY = bounds.yMin + dxfH / 2;

  const panX = canvasW / 2 - centerDxfX * zoom;
  const panY = canvasH / 2 - centerDxfY * zoom;

  return { zoom, pan: { x: panX, y: panY } };
}

/**
 * Compute new pan offset after a zoom change so the zoom is centered
 * on the mouse cursor position.
 *
 * This prevents the jarring visual effect of zooming toward the canvas
 * origin instead of the point the user is looking at.
 *
 * @param mouseScreen - Mouse position in screen pixels.
 * @param oldZoom     - Zoom level before the change.
 * @param newZoom     - Zoom level after the change.
 * @param oldPan      - Pan offset before the change.
 * @returns New pan offset that keeps the world point under the cursor fixed.
 */
export function zoomTowardPoint(
  mouseScreen: Point,
  oldZoom: number,
  newZoom: number,
  oldPan: Point
): Point {
  // The world point under the mouse must remain at the same screen position.
  // oldWorldX = (mouseScreen.x - oldPan.x) / oldZoom
  // newPan.x = mouseScreen.x - oldWorldX * newZoom
  return {
    x: mouseScreen.x - ((mouseScreen.x - oldPan.x) / oldZoom) * newZoom,
    y: mouseScreen.y - ((mouseScreen.y - oldPan.y) / oldZoom) * newZoom,
  };
}

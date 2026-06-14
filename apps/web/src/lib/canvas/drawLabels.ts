/**
 * @file drawLabels.ts
 * @description Renders member ID labels and dimension annotations on the canvas.
 *
 * Labels are positioned near the center of each member and include
 * the member ID (e.g. "B1") and key dimensions (e.g. "450×225").
 *
 * The label pill border is optionally tinted to reflect the member's analysis
 * result (green = pass, red = fail, dashed neutral = skipped/unknown).
 *
 * @module canvas/drawLabels
 */

import type { GeometricMember, MemberType, Point, AnalysisStatus } from "@/types/canvas";
import { worldToScreen } from "./transform";

/** Label font for member IDs. */
const LABEL_FONT_ID = "bold 11px 'JetBrains Mono', monospace";

/** Label font for dimension text. */
const LABEL_FONT_DIM = "9px 'JetBrains Mono', monospace";

/** Label text color. */
const LABEL_COLOR = "rgba(213, 219, 228, 0.85)";

/** Label background for readability. */
const LABEL_BG = "rgba(11, 15, 25, 0.75)";

/** Pill border colours driven by analysis status. */
const PILL_BORDER_PASS   = "rgba(34, 197, 94, 0.80)";
const PILL_BORDER_FAIL   = "rgba(239, 68, 68, 0.85)";
const PILL_BORDER_SKIP   = "rgba(148, 163, 184, 0.40)";
const PILL_BORDER_NONE   = "rgba(255, 255, 255, 0.08)";

function getMemberCenter(member: GeometricMember): Point {
  if (member.center_point) {
    return member.center_point;
  }
  if (member.boundary_polygon && member.boundary_polygon.length > 0) {
    const xs = member.boundary_polygon.map((p) => p.x);
    const ys = member.boundary_polygon.map((p) => p.y);
    return {
      x: (Math.min(...xs) + Math.max(...xs)) / 2,
      y: (Math.min(...ys) + Math.max(...ys)) / 2,
    };
  }
  const startPoint = member.start_point ?? { x: 0, y: 0 };
  const endPoint = member.end_point ?? startPoint;
  return {
    x: (startPoint.x + endPoint.x) / 2,
    y: (startPoint.y + endPoint.y) / 2,
  };
}

/**
 * Draw the ID label and dimension annotation for a member.
 *
 * @param ctx            - Canvas 2D rendering context.
 * @param member         - The structural member to label.
 * @param zoom           - Current zoom level.
 * @param pan            - Current pan offset.
 * @param canvasHeight   - Canvas height in pixels.
 * @param analysisStatus - Optional analysis result; when provided the pill border
 *                         is tinted green (pass), red (fail), or dashed gray (skipped).
 */
export function drawMemberLabel(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  analysisStatus?: AnalysisStatus
): void {
  // Skip labels at very low zoom levels where they'd be unreadable
  if (zoom < 0.02) return;

  // Compute screen-space center of the member
  const worldCenter = getMemberCenter(member);
  const screen = worldToScreen(worldCenter, zoom, pan, canvasHeight);

  // Build label text
  const idText = member.member_id;
  const b = member.meta.b_mm;
  const h = member.meta.h_mm;
  const dimText = b && h ? `${b}×${h}` : "";

  // Measure text for background pill
  ctx.font = LABEL_FONT_ID;
  const idWidth = ctx.measureText(idText).width;
  ctx.font = LABEL_FONT_DIM;
  const dimWidth = dimText ? ctx.measureText(dimText).width : 0;

  const totalWidth = Math.max(idWidth, dimWidth) + 10;
  const totalHeight = dimText ? 30 : 18;

  const bgX = screen.x - totalWidth / 2;
  const bgY = screen.y - totalHeight / 2;

  // Background pill
  ctx.fillStyle = LABEL_BG;
  ctx.beginPath();
  ctx.roundRect(bgX, bgY, totalWidth, totalHeight, 3);
  ctx.fill();

  // Pill border — tinted by analysis status when overlay is active
  ctx.save();
  const borderColor = analysisStatus
    ? analysisStatus === "pass"
      ? PILL_BORDER_PASS
      : analysisStatus === "fail"
        ? PILL_BORDER_FAIL
        : analysisStatus === "skipped"
          ? PILL_BORDER_SKIP
          : PILL_BORDER_NONE
    : PILL_BORDER_NONE;

  if (analysisStatus === "skipped") {
    ctx.setLineDash([3, 3]);
  }
  ctx.strokeStyle = borderColor;
  ctx.lineWidth = analysisStatus && analysisStatus !== "unknown" ? 1.5 : 0.5;
  ctx.beginPath();
  ctx.roundRect(bgX, bgY, totalWidth, totalHeight, 3);
  ctx.stroke();
  ctx.restore();

  // Member ID
  ctx.fillStyle = LABEL_COLOR;
  ctx.font = LABEL_FONT_ID;
  ctx.textAlign = "center";
  ctx.textBaseline = dimText ? "bottom" : "middle";
  ctx.fillText(idText, screen.x, dimText ? screen.y - 1 : screen.y);

  // Dimension text
  if (dimText) {
    ctx.font = LABEL_FONT_DIM;
    ctx.fillStyle = "rgba(213, 219, 228, 0.55)";
    ctx.textBaseline = "top";
    ctx.fillText(dimText, screen.x, screen.y + 2);
  }
}

/**
 * Draw labels for all members that are visible on screen, respecting
 * the label visibility filters and optionally tinting pill borders by
 * analysis result.
 *
 * @param ctx             - Canvas 2D rendering context.
 * @param members         - Array of structural members.
 * @param zoom            - Current zoom level.
 * @param pan             - Current pan offset.
 * @param canvasWidth     - Canvas width in pixels.
 * @param canvasHeight    - Canvas height in pixels.
 * @param analysisMap     - Optional map from member_id → AnalysisStatus.
 *                          When provided and non-empty, pill borders are tinted.
 * @param hiddenLabelTypes - Set of MemberType strings whose labels are suppressed.
 * @param hiddenLabelIds   - Set of individual member IDs whose labels are suppressed.
 */
export function drawAllLabels(
  ctx: CanvasRenderingContext2D,
  members: GeometricMember[],
  zoom: number,
  pan: Point,
  canvasWidth: number,
  canvasHeight: number,
  analysisMap?: Map<string, AnalysisStatus>,
  hiddenLabelTypes?: Set<MemberType>,
  hiddenLabelIds?: Set<string>
): void {
  for (const member of members) {
    // ── Visibility filters ─────────────────────────────────────────────────
    if (hiddenLabelTypes?.has(member.member_type)) continue;
    if (hiddenLabelIds?.has(member.member_id)) continue;

    const worldCenter = getMemberCenter(member);
    const screen = worldToScreen(worldCenter, zoom, pan, canvasHeight);

    // Skip labels outside the visible viewport (with buffer)
    if (
      screen.x < -50 ||
      screen.x > canvasWidth + 50 ||
      screen.y < -50 ||
      screen.y > canvasHeight + 50
    ) {
      continue;
    }

    const analysisStatus = analysisMap?.get(member.member_id);
    drawMemberLabel(ctx, member, zoom, pan, canvasHeight, analysisStatus);
  }
}

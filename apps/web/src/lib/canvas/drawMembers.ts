/**
 * @file drawMembers.ts
 * @description Renders structural members on the HTML5 Canvas.
 *
 * Each member type has a distinct visual treatment:
 * - **Beams**: Indigo filled rectangles between start/end points.
 * - **Columns**: Amber filled squares at their position.
 * - **Slabs**: Emerald semi-transparent zones with spanning direction arrows.
 * - **Voids**: Red diagonal X-crossing hatching.
 * - **Walls**: Thick slate-colored lines.
 * - **Footings**: Dashed amber rectangles below columns.
 *
 * Selected members get a glowing cyan animated border.
 * Hovered members get a brightness boost (+15% opacity).
 *
 * @module canvas/drawMembers
 */

import type { GeometricMember, Point, AnalysisStatus } from "@/types/canvas";
import { worldToScreen } from "./transform";


// ── Color Palette ───────────────────────────────────────────────────────────

const BEAM_FILL = "rgba(99, 102, 241, 0.25)";
const BEAM_FILL_HOVER = "rgba(99, 102, 241, 0.40)";
const BEAM_STROKE = "rgba(99, 102, 241, 0.85)";

const COLUMN_FILL = "rgba(245, 158, 11, 0.35)";
const COLUMN_FILL_HOVER = "rgba(245, 158, 11, 0.50)";
const COLUMN_STROKE = "rgba(245, 158, 11, 0.90)";

const SLAB_FILL = "rgba(16, 185, 129, 0.10)";
const SLAB_FILL_HOVER = "rgba(16, 185, 129, 0.20)";
const SLAB_STROKE = "rgba(16, 185, 129, 0.50)";

const VOID_FILL = "rgba(239, 68, 68, 0.08)";
const VOID_STROKE = "rgba(239, 68, 68, 0.40)";

const WALL_STROKE = "rgba(100, 116, 139, 0.75)";

const FOOTING_FILL = "rgba(217, 119, 6, 0.15)";
const FOOTING_STROKE = "rgba(217, 119, 6, 0.65)";

const SELECTION_GLOW = "rgba(6, 182, 212, 0.80)";
const SELECTION_GLOW_SHADOW = "rgba(6, 182, 212, 0.35)";

// ── Analysis overlay colours ─────────────────────────────────────────────────

/** Outer stroke for a member that passed all analysis checks. */
const ANALYSIS_PASS_STROKE = "rgba(34, 197, 94, 0.85)";
const ANALYSIS_PASS_SHADOW = "rgba(34, 197, 94, 0.30)";

/** Outer stroke for a member that failed one or more checks. */
const ANALYSIS_FAIL_STROKE = "rgba(239, 68, 68, 0.90)";
const ANALYSIS_FAIL_SHADOW = "rgba(239, 68, 68, 0.35)";

/** Dashed border for members skipped from analysis (e.g. voids). */
const ANALYSIS_SKIP_STROKE = "rgba(148, 163, 184, 0.50)";


// ── Helper: Screen-space rectangle for a beam ───────────────────────────────

function beamScreenRect(
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number
): { x: number; y: number; w: number; h: number } {
  const startPoint = member.start_point ?? { x: 0, y: 0 };
  const endPoint = member.end_point ?? startPoint;
  const s = worldToScreen(startPoint, zoom, pan, canvasHeight);
  const e = worldToScreen(endPoint, zoom, pan, canvasHeight);
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

// ── Draw Functions ──────────────────────────────────────────────────────────

export function drawBeam(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean,
  analysisStatus?: AnalysisStatus
): void {
  const rect = beamScreenRect(member, zoom, pan, canvasHeight);
  if (rect.w < 1 && rect.h < 1) return;

  ctx.fillStyle = isHovered ? BEAM_FILL_HOVER : BEAM_FILL;
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h);

  ctx.strokeStyle = BEAM_STROKE;
  ctx.lineWidth = isSelected ? 2.5 : 1.5;
  ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

  if (isSelected) {
    drawSelectionGlow(ctx, rect.x, rect.y, rect.w, rect.h);
  } else if (analysisStatus && analysisStatus !== "unknown") {
    drawAnalysisOverlay(ctx, rect.x, rect.y, rect.w, rect.h, analysisStatus);
  }
}


export function drawColumn(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean,
  analysisStatus?: AnalysisStatus
): void {
  const centerPoint = member.center_point ?? { x: 0, y: 0 };
  const center = worldToScreen(centerPoint, zoom, pan, canvasHeight);
  const w = member.meta.b_mm * zoom;
  const h = member.meta.h_mm * zoom;

  const drawW = Math.max(w, 4);
  const drawH = Math.max(h, 4);
  const x = center.x - drawW / 2;
  const y = center.y - drawH / 2;

  ctx.fillStyle = isHovered ? COLUMN_FILL_HOVER : COLUMN_FILL;
  ctx.fillRect(x, y, drawW, drawH);

  ctx.strokeStyle = COLUMN_STROKE;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + drawW, y + drawH);
  ctx.moveTo(x + drawW, y);
  ctx.lineTo(x, y + drawH);
  ctx.stroke();

  ctx.lineWidth = isSelected ? 2.5 : 1.5;
  ctx.strokeRect(x, y, drawW, drawH);

  if (isSelected) {
    drawSelectionGlow(ctx, x, y, drawW, drawH);
  } else if (analysisStatus && analysisStatus !== "unknown") {
    drawAnalysisOverlay(ctx, x, y, drawW, drawH, analysisStatus);
  }
}


function drawArrowHead(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  angle: number
): void {
  const size = 5;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-size * 1.5, -size);
  ctx.lineTo(-size * 1.5, size);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawSpanningArrows(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  member: GeometricMember
): void {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const arrowLen = Math.min(w, h) * 0.35;

  ctx.strokeStyle = SLAB_STROKE;
  ctx.fillStyle = SLAB_STROKE;
  ctx.lineWidth = 1.2;

  const isHorizontalShort = w <= h;

  if (isHorizontalShort) {
    const leftX = cx - arrowLen;
    const rightX = cx + arrowLen;
    ctx.beginPath();
    ctx.moveTo(leftX, cy);
    ctx.lineTo(rightX, cy);
    ctx.stroke();
    drawArrowHead(ctx, rightX, cy, 0);
    drawArrowHead(ctx, leftX, cy, Math.PI);
  } else {
    const topY = cy - arrowLen;
    const bottomY = cy + arrowLen;
    ctx.beginPath();
    ctx.moveTo(cx, topY);
    ctx.lineTo(cx, bottomY);
    ctx.stroke();
    drawArrowHead(ctx, cx, bottomY, Math.PI / 2);
    drawArrowHead(ctx, cx, topY, -Math.PI / 2);
  }

  const lx = member.meta.Lx;
  const ly = member.meta.Ly;
  if (lx || ly) {
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = "rgba(16, 185, 129, 0.70)";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const label = lx ? `Lx=${lx.toFixed(1)}m` : `Ly=${(ly ?? 0).toFixed(1)}m`;
    ctx.fillText(label, cx, cy + 8);
  }
}

export function drawSlab(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean,
  analysisStatus?: AnalysisStatus
): void {
  let cx: number, cy: number;
  let xMin: number, yMin: number, w: number, h: number;

  // Use true boundary polygon coordinates if available
  if (member.boundary_polygon && member.boundary_polygon.length >= 3) {
    const pts = member.boundary_polygon.map((p) => worldToScreen(p, zoom, pan, canvasHeight));
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();

    ctx.fillStyle = isHovered ? SLAB_FILL_HOVER : SLAB_FILL;
    ctx.fill();
    ctx.strokeStyle = SLAB_STROKE;
    ctx.lineWidth = isSelected ? 2 : 1;
    ctx.setLineDash([6, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    xMin = Math.min(...xs); yMin = Math.min(...ys);
    w = Math.max(...xs) - xMin; h = Math.max(...ys) - yMin;

    // FIX: Anchor arrows exactly to the backend calculated center mass
    const rawCenter = member.center_point ?? {
      x: (Math.min(...member.boundary_polygon.map(p => p.x)) + Math.max(...member.boundary_polygon.map(p => p.x))) / 2,
      y: (Math.min(...member.boundary_polygon.map(p => p.y)) + Math.max(...member.boundary_polygon.map(p => p.y))) / 2,
    };
    const screenCenter = worldToScreen(rawCenter, zoom, pan, canvasHeight);
    cx = screenCenter.x;
    cy = screenCenter.y;
  } else {
    // Fallback block configuration
    const startPoint = member.start_point ?? { x: 0, y: 0 };
    const endPoint = member.end_point ?? startPoint;
    const s = worldToScreen(startPoint, zoom, pan, canvasHeight);
    const e = worldToScreen(endPoint, zoom, pan, canvasHeight);
    xMin = Math.min(s.x, e.x); yMin = Math.min(s.y, e.y);
    w = Math.abs(e.x - s.x); h = Math.abs(e.y - s.y);
    if (w < 2 && h < 2) return;

    ctx.fillStyle = isHovered ? SLAB_FILL_HOVER : SLAB_FILL;
    ctx.fillRect(xMin, yMin, w, h);
    ctx.strokeStyle = SLAB_STROKE;
    ctx.lineWidth = isSelected ? 2 : 1;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(xMin, yMin, w, h);
    ctx.setLineDash([]);

    cx = xMin + w / 2;
    cy = yMin + h / 2;
  }

  // Draw spans using true context layout coordinates
  if (w > 30 && h > 30) {
    drawSpanningArrows(ctx, cx, cy, w, h, member); // <-- Modify drawSpanningArrows to accept cx, cy directly
  }

  if (isSelected) {
    drawSelectionGlow(ctx, xMin, yMin, w, h);
  } else if (analysisStatus && analysisStatus !== "unknown") {
    drawAnalysisOverlay(ctx, xMin, yMin, w, h, analysisStatus);
  }
}

export function drawVoid(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
): void {
  let xMin: number, yMin: number, w: number, h: number;
  let path: Path2D | null = null;

  if (member.boundary_polygon && member.boundary_polygon.length >= 3) {
    const pts = member.boundary_polygon.map((p) => worldToScreen(p, zoom, pan, canvasHeight));
    path = new Path2D();
    path.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) path.lineTo(pts[i].x, pts[i].y);
    path.closePath();

    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    xMin = Math.min(...xs); yMin = Math.min(...ys);
    w = Math.max(...xs) - xMin; h = Math.max(...ys) - yMin;
  } else {
    const startPoint = member.start_point ?? { x: 0, y: 0 };
    const endPoint = member.end_point ?? startPoint;
    const s = worldToScreen(startPoint, zoom, pan, canvasHeight);
    const e = worldToScreen(endPoint, zoom, pan, canvasHeight);
    xMin = Math.min(s.x, e.x); yMin = Math.min(s.y, e.y);
    w = Math.abs(e.x - s.x); h = Math.abs(e.y - s.y);
    if (w < 2 && h < 2) return;
  }

  ctx.fillStyle = isHovered ? "rgba(239, 68, 68, 0.12)" : VOID_FILL;
  if (path) ctx.fill(path); else ctx.fillRect(xMin, yMin, w, h);

  ctx.save();
  if (path) ctx.clip(path); else { ctx.beginPath(); ctx.rect(xMin, yMin, w, h); ctx.clip(); }
  ctx.strokeStyle = VOID_STROKE;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(xMin, yMin); ctx.lineTo(xMin + w, yMin + h);
  ctx.moveTo(xMin + w, yMin); ctx.lineTo(xMin, yMin + h);
  ctx.stroke();
  ctx.restore();

  ctx.strokeStyle = VOID_STROKE;
  ctx.lineWidth = isSelected ? 2 : 1;
  if (path) ctx.stroke(path); else ctx.strokeRect(xMin, yMin, w, h);

  if (isSelected) {
    drawSelectionGlow(ctx, xMin, yMin, w, h);
  }
}

export function drawWall(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
): void {
  const startPoint = member.start_point ?? { x: 0, y: 0 };
  const endPoint = member.end_point ?? startPoint;
  const s = worldToScreen(startPoint, zoom, pan, canvasHeight);
  const e = worldToScreen(endPoint, zoom, pan, canvasHeight);
  const thickness = Math.max(member.meta.b_mm * zoom, 3);

  ctx.strokeStyle = isHovered ? "rgba(100, 116, 139, 0.90)" : WALL_STROKE;
  ctx.lineWidth = isSelected ? thickness + 2 : thickness;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(s.x, s.y);
  ctx.lineTo(e.x, e.y);
  ctx.stroke();

  if (isSelected) {
    ctx.strokeStyle = SELECTION_GLOW;
    ctx.lineWidth = thickness + 4;
    ctx.globalAlpha = 0.3;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(e.x, e.y);
    ctx.stroke();
    ctx.globalAlpha = 1.0;
  }
}

export function drawFooting(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
): void {
  const centerPoint = member.center_point ?? { x: 0, y: 0 };
  const center = worldToScreen(centerPoint, zoom, pan, canvasHeight);
  const w = Math.max(member.meta.b_mm * zoom, 6);
  const h = Math.max(member.meta.h_mm * zoom, 6);

  const x = center.x - w / 2;
  const y = center.y - h / 2;

  ctx.fillStyle = isHovered ? "rgba(217, 119, 6, 0.22)" : FOOTING_FILL;
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = FOOTING_STROKE;
  ctx.lineWidth = isSelected ? 2 : 1.5;
  ctx.setLineDash([4, 3]);
  ctx.strokeRect(x, y, w, h);
  ctx.setLineDash([]);

  if (isSelected) {
    drawSelectionGlow(ctx, x, y, w, h);
  }
}

// ── Analysis overlay helper ──────────────────────────────────────────────────

/**
 * Draw a coloured glow border indicating analysis pass/fail/skipped status.
 *
 * Must be called *after* the member's own geometry is drawn so the glow
 * renders on top without being clipped by fill areas.
 *
 * @param ctx    - Canvas 2D rendering context.
 * @param x      - Left edge of the member bounding rect (screen pixels).
 * @param y      - Top edge of the member bounding rect (screen pixels).
 * @param w      - Width of the member bounding rect (screen pixels).
 * @param h      - Height of the member bounding rect (screen pixels).
 * @param status - Analysis result status driving the colour choice.
 */
function drawAnalysisOverlay(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  status: AnalysisStatus
): void {
  if (status === "unknown") return;

  ctx.save();

  if (status === "skipped") {
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = ANALYSIS_SKIP_STROKE;
    ctx.lineWidth = 1.5;
    ctx.shadowColor = "transparent";
    ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
  } else {
    const strokeColor =
      status === "pass" ? ANALYSIS_PASS_STROKE : ANALYSIS_FAIL_STROKE;
    const shadowColor =
      status === "pass" ? ANALYSIS_PASS_SHADOW : ANALYSIS_FAIL_SHADOW;
    ctx.shadowColor = shadowColor;
    ctx.shadowBlur = 10;
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
  }

  ctx.restore();
}

function drawSelectionGlow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number
): void {
  ctx.save();
  ctx.shadowColor = SELECTION_GLOW_SHADOW;
  ctx.shadowBlur = 12;
  ctx.strokeStyle = SELECTION_GLOW;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.lineDashOffset = -(performance.now() / 40) % 20;
  ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
  ctx.setLineDash([]);
  ctx.restore();
}


export function drawMember(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean,
  /** Optional analysis result status — drives pass/fail colour-coding overlay. */
  analysisStatus?: AnalysisStatus
): void {
  switch (member.member_type) {
    case "beam":
      drawBeam(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered, analysisStatus);
      break;
    case "column":
      drawColumn(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered, analysisStatus);
      break;
    case "slab":
      drawSlab(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered, analysisStatus);
      break;
    case "void":
    case "staircase":
      drawVoid(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
      break;
    case "wall":
      drawWall(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
      break;
    case "footing":
      drawFooting(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
      break;
  }
}


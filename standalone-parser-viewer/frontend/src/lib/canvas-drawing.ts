/**
 * @file canvas-drawing.ts
 * @description Standard types, coordinate transforms, and drawing functions for the standalone viewer.
 */

// ── Types ───────────────────────────────────────────────────────────────────

export interface Point {
  x: number;
  y: number;
}

export interface BoundingBox {
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
}

export type MemberType =
  | "beam"
  | "column"
  | "slab"
  | "wall"
  | "footing"
  | "staircase"
  | "void";

export interface MemberMeta {
  b_mm: number;
  h_mm: number;
  L_clear?: number;
  Lx?: number;
  Ly?: number;
  [key: string]: unknown;
}

export interface GeometricMember {
  member_id: string;
  member_type: MemberType;
  start: Point;
  end: Point;
  boundary_polygon?: Point[];
  meta: MemberMeta;
}

export interface ScaleInfo {
  factor: number;
  unit: string;
  detected: boolean;
  confirmed: boolean;
}

export interface ParsedGeometry {
  members: GeometricMember[];
  scale: ScaleInfo;
  raw_entity_count?: number;
  parse_warnings?: string[];
  filenames?: {
    dxf: string;
    pdf: string | null;
  };
}

// ── Normalization ──────────────────────────────────────────────────────────

/**
 * Normalizes backend parsed member structures into standard GeometricMember structures.
 */
export function normalizeBackendMember(raw: any): GeometricMember {
  const m = raw as Record<string, any>;
  const polygon = Array.isArray(m.boundary_polygon)
    ? (m.boundary_polygon as Point[])
    : undefined;

  let startRaw: Point;
  let endRaw: Point;

  if (polygon && polygon.length >= 2) {
    const xs = polygon.map((p) => p.x);
    const ys = polygon.map((p) => p.y);
    startRaw = { x: Math.min(...xs), y: Math.min(...ys) };
    endRaw = { x: Math.max(...xs), y: Math.max(...ys) };
  } else {
    startRaw = (m.start ?? m.start_point ?? m.center_point ?? { x: 0, y: 0 }) as Point;
    endRaw = (m.end ?? m.end_point ?? m.center_point ?? startRaw) as Point;
  }

  const rawMeta = (m.meta ?? {}) as Record<string, any>;
  const meta = {
    ...rawMeta,
    b_mm: Number(rawMeta.b_mm ?? rawMeta.b ?? 300),
    h_mm: Number(rawMeta.h_mm ?? rawMeta.h ?? 500),
  } as MemberMeta;

  return {
    member_id: (m.member_id ?? m.id ?? "Unknown") as string,
    member_type: (m.member_type ?? m.type ?? "beam") as MemberType,
    start: startRaw,
    end: endRaw,
    boundary_polygon: polygon,
    meta,
  };
}

// ── Transforms ─────────────────────────────────────────────────────────────

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

export function computeBounds(members: GeometricMember[]): BoundingBox | null {
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

    if (m.member_type === "column" && m.meta.b_mm && m.meta.h_mm) {
      const halfB = m.meta.b_mm / 2;
      const halfH = m.meta.h_mm / 2;
      expand(m.start.x - halfB, m.start.y - halfH);
      expand(m.start.x + halfB, m.start.y + halfH);
    }

    if (m.member_type === "slab" && m.meta.Lx && m.meta.Ly) {
      const cx = (m.start.x + m.end.x) / 2;
      const cy = (m.start.y + m.end.y) / 2;
      expand(cx - m.meta.Lx / 2, cy - m.meta.Ly / 2);
      expand(cx + m.meta.Lx / 2, cy + m.meta.Ly / 2);
    }

    if (m.member_type === "beam" && m.meta.b_mm) {
      const halfB = m.meta.b_mm / 2;
      expand(m.start.x - halfB, m.start.y - halfB);
      expand(m.end.x + halfB, m.end.y + halfB);
    }
  }

  return { xMin, yMin, xMax, yMax };
}

export function computeFitTransform(
  bounds: BoundingBox,
  canvasW: number,
  canvasH: number,
  padding = 0.1
): { zoom: number; pan: Point } {
  const dxfW = bounds.xMax - bounds.xMin;
  const dxfH = bounds.yMax - bounds.yMin;

  if (dxfW <= 0 || dxfH <= 0) {
    return { zoom: 1, pan: { x: canvasW / 2, y: canvasH / 2 } };
  }

  const usableW = canvasW * (1 - 2 * padding);
  const usableH = canvasH * (1 - 2 * padding);
  const zoom = Math.min(usableW / dxfW, usableH / dxfH);

  const centerDxfX = bounds.xMin + dxfW / 2;
  const centerDxfY = bounds.yMin + dxfH / 2;

  const panX = canvasW / 2 - centerDxfX * zoom;
  const panY = canvasH / 2 - centerDxfY * zoom;

  return { zoom, pan: { x: panX, y: panY } };
}

export function zoomTowardPoint(
  mouseScreen: Point,
  oldZoom: number,
  newZoom: number,
  oldPan: Point
): Point {
  return {
    x: mouseScreen.x - ((mouseScreen.x - oldPan.x) / oldZoom) * newZoom,
    y: mouseScreen.y - ((mouseScreen.y - oldPan.y) / oldZoom) * newZoom,
  };
}

// ── Grid Background ────────────────────────────────────────────────────────

const BASE_GRID_SPACING = 1000;
const MIN_PIXEL_SPACING = 15;
const MAX_PIXEL_SPACING = 80;
const DOT_RADIUS = 0.8;
const DOT_COLOR_PRIMARY = "rgba(100, 116, 139, 0.25)";
const DOT_COLOR_SECONDARY = "rgba(100, 116, 139, 0.15)";

export function drawDotGrid(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  zoom: number,
  pan: Point
): void {
  let spacing = BASE_GRID_SPACING;
  let screenSpacing = spacing * zoom;

  while (screenSpacing > MAX_PIXEL_SPACING && spacing > 10) {
    spacing /= 2;
    screenSpacing = spacing * zoom;
  }
  while (screenSpacing < MIN_PIXEL_SPACING) {
    spacing *= 2;
    screenSpacing = spacing * zoom;
  }

  const worldXMin = -pan.x / zoom;
  const worldXMax = (width - pan.x) / zoom;
  const worldYMin = -pan.y / zoom;
  const worldYMax = (height - pan.y) / zoom;

  const startX = Math.floor(worldXMin / spacing) * spacing;
  const endX = Math.ceil(worldXMax / spacing) * spacing;
  const startY = Math.floor(worldYMin / spacing) * spacing;
  const endY = Math.ceil(worldYMax / spacing) * spacing;

  ctx.beginPath();
  for (let wx = startX; wx <= endX; wx += spacing) {
    for (let wy = startY; wy <= endY; wy += spacing) {
      const sx = wx * zoom + pan.x;
      const sy = height - (wy * zoom + pan.y);
      if (sx < -2 || sx > width + 2 || sy < -2 || sy > height + 2) continue;
      ctx.moveTo(sx + DOT_RADIUS, sy);
      ctx.arc(sx, sy, DOT_RADIUS, 0, Math.PI * 2);
    }
  }
  ctx.fillStyle = DOT_COLOR_PRIMARY;
  ctx.fill();

  const subSpacing = spacing / 2;
  const subScreenSpacing = subSpacing * zoom;
  if (subScreenSpacing >= MIN_PIXEL_SPACING && zoom > 0.05) {
    const subStartX = Math.floor(worldXMin / subSpacing) * subSpacing;
    const subEndX = Math.ceil(worldXMax / subSpacing) * subSpacing;
    const subStartY = Math.floor(worldYMin / subSpacing) * subSpacing;
    const subEndY = Math.ceil(worldYMax / subSpacing) * subSpacing;

    ctx.beginPath();
    for (let wx = subStartX; wx <= subEndX; wx += subSpacing) {
      for (let wy = subStartY; wy <= subEndY; wy += subSpacing) {
        const onPrimaryX = Math.abs(wx % spacing) < 0.01;
        const onPrimaryY = Math.abs(wy % spacing) < 0.01;
        if (onPrimaryX && onPrimaryY) continue;

        const sx = wx * zoom + pan.x;
        const sy = height - (wy * zoom + pan.y);
        if (sx < -2 || sx > width + 2 || sy < -2 || sy > height + 2) continue;

        ctx.moveTo(sx + DOT_RADIUS * 0.6, sy);
        ctx.arc(sx, sy, DOT_RADIUS * 0.6, 0, Math.PI * 2);
      }
    }
    ctx.fillStyle = DOT_COLOR_SECONDARY;
    ctx.fill();
  }
}

// ── Colors ──────────────────────────────────────────────────────────────────

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

// ── Draw Members ────────────────────────────────────────────────────────────

function beamScreenRect(
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number
): { x: number; y: number; w: number; h: number } {
  const s = worldToScreen(member.start, zoom, pan, canvasHeight);
  const e = worldToScreen(member.end, zoom, pan, canvasHeight);
  const halfWidth = ((member.meta.b_mm ?? 300) * zoom) / 2;

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

export function drawBeam(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
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
  }
}

export function drawColumn(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
): void {
  const center = worldToScreen(member.start, zoom, pan, canvasHeight);
  const w = (member.meta.b_mm ?? 300) * zoom;
  const h = (member.meta.h_mm ?? 300) * zoom;

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
    ctx.font = "10px monospace";
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
  isHovered: boolean
): void {
  let x: number, y: number, w: number, h: number;

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
    x = Math.min(...xs); y = Math.min(...ys);
    w = Math.max(...xs) - x; h = Math.max(...ys) - y;
  } else {
    const s = worldToScreen(member.start, zoom, pan, canvasHeight);
    const e = worldToScreen(member.end, zoom, pan, canvasHeight);
    x = Math.min(s.x, e.x); y = Math.min(s.y, e.y);
    w = Math.abs(e.x - s.x); h = Math.abs(e.y - s.y);
    if (w < 2 && h < 2) return;

    ctx.fillStyle = isHovered ? SLAB_FILL_HOVER : SLAB_FILL;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = SLAB_STROKE;
    ctx.lineWidth = isSelected ? 2 : 1;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
  }

  if (w > 30 && h > 30) {
    drawSpanningArrows(ctx, x, y, w, h, member);
  }
  if (isSelected) {
    drawSelectionGlow(ctx, x, y, w, h);
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
  let x: number, y: number, w: number, h: number;
  let path: Path2D | null = null;

  if (member.boundary_polygon && member.boundary_polygon.length >= 3) {
    const pts = member.boundary_polygon.map((p) => worldToScreen(p, zoom, pan, canvasHeight));
    path = new Path2D();
    path.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) path.lineTo(pts[i].x, pts[i].y);
    path.closePath();

    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    x = Math.min(...xs); y = Math.min(...ys);
    w = Math.max(...xs) - x; h = Math.max(...ys) - y;
  } else {
    const s = worldToScreen(member.start, zoom, pan, canvasHeight);
    const e = worldToScreen(member.end, zoom, pan, canvasHeight);
    x = Math.min(s.x, e.x); y = Math.min(s.y, e.y);
    w = Math.abs(e.x - s.x); h = Math.abs(e.y - s.y);
    if (w < 2 && h < 2) return;
  }

  ctx.fillStyle = isHovered ? "rgba(239, 68, 68, 0.12)" : VOID_FILL;
  if (path) ctx.fill(path); else ctx.fillRect(x, y, w, h);

  ctx.save();
  if (path) ctx.clip(path); else { ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); }
  ctx.strokeStyle = VOID_STROKE;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x, y); ctx.lineTo(x + w, y + h);
  ctx.moveTo(x + w, y); ctx.lineTo(x, y + h);
  ctx.stroke();
  ctx.restore();

  ctx.strokeStyle = VOID_STROKE;
  ctx.lineWidth = isSelected ? 2 : 1;
  if (path) ctx.stroke(path); else ctx.strokeRect(x, y, w, h);

  if (isSelected) {
    drawSelectionGlow(ctx, x, y, w, h);
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
  const s = worldToScreen(member.start, zoom, pan, canvasHeight);
  const e = worldToScreen(member.end, zoom, pan, canvasHeight);
  const thickness = Math.max((member.meta.b_mm ?? 225) * zoom, 3);

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
  const center = worldToScreen(member.start, zoom, pan, canvasHeight);
  const w = Math.max((member.meta.b_mm ?? 1000) * zoom, 6);
  const h = Math.max((member.meta.h_mm ?? 1000) * zoom, 6);

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
  ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
  ctx.restore();
}

export function drawMember(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number,
  isSelected: boolean,
  isHovered: boolean
): void {
  switch (member.member_type) {
    case "beam":
      drawBeam(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
      break;
    case "column":
      drawColumn(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
      break;
    case "slab":
      drawSlab(ctx, member, zoom, pan, canvasHeight, isSelected, isHovered);
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

// ── Labels ──────────────────────────────────────────────────────────────────

const LABEL_FONT_ID = "bold 11px monospace";
const LABEL_FONT_DIM = "9px monospace";
const LABEL_COLOR = "rgba(213, 219, 228, 0.85)";
const LABEL_BG = "rgba(11, 15, 25, 0.75)";

export function drawMemberLabel(
  ctx: CanvasRenderingContext2D,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number
): void {
  if (zoom < 0.02) return;

  const worldCenter: Point = {
    x: (member.start.x + member.end.x) / 2,
    y: (member.start.y + member.end.y) / 2,
  };
  const screen = worldToScreen(worldCenter, zoom, pan, canvasHeight);

  const idText = member.member_id;
  const b = member.meta.b_mm;
  const h = member.meta.h_mm;
  const dimText = b && h ? `${b}×${h}` : "";

  ctx.font = LABEL_FONT_ID;
  const idWidth = ctx.measureText(idText).width;
  ctx.font = LABEL_FONT_DIM;
  const dimWidth = dimText ? ctx.measureText(dimText).width : 0;

  const totalWidth = Math.max(idWidth, dimWidth) + 10;
  const totalHeight = dimText ? 30 : 18;

  const bgX = screen.x - totalWidth / 2;
  const bgY = screen.y - totalHeight / 2;

  ctx.fillStyle = LABEL_BG;
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(bgX, bgY, totalWidth, totalHeight, 3);
  } else {
    ctx.rect(bgX, bgY, totalWidth, totalHeight);
  }
  ctx.fill();

  ctx.fillStyle = LABEL_COLOR;
  ctx.font = LABEL_FONT_ID;
  ctx.textAlign = "center";
  ctx.textBaseline = dimText ? "bottom" : "middle";
  ctx.fillText(idText, screen.x, dimText ? screen.y - 1 : screen.y);

  if (dimText) {
    ctx.font = LABEL_FONT_DIM;
    ctx.fillStyle = "rgba(213, 219, 228, 0.55)";
    ctx.textBaseline = "top";
    ctx.fillText(dimText, screen.x, screen.y + 2);
  }
}

export function drawAllLabels(
  ctx: CanvasRenderingContext2D,
  members: GeometricMember[],
  zoom: number,
  pan: Point,
  canvasWidth: number,
  canvasHeight: number
): void {
  for (const member of members) {
    const worldCenter: Point = {
      x: (member.start.x + member.end.x) / 2,
      y: (member.start.y + member.end.y) / 2,
    };
    const screen = worldToScreen(worldCenter, zoom, pan, canvasHeight);

    if (
      screen.x < -50 ||
      screen.x > canvasWidth + 50 ||
      screen.y < -50 ||
      screen.y > canvasHeight + 50
    ) {
      continue;
    }

    drawMemberLabel(ctx, member, zoom, pan, canvasHeight);
  }
}

// ── Hit Testing ─────────────────────────────────────────────────────────────

const HIT_TOLERANCE_PX = 5;

function pointInRect(
  px: number,
  py: number,
  rx: number,
  ry: number,
  rw: number,
  rh: number,
  tolerance: number
): boolean {
  return (
    px >= rx - tolerance &&
    px <= rx + rw + tolerance &&
    py >= ry - tolerance &&
    py <= ry + rh + tolerance
  );
}

function pointToLineDistance(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;

  if (lenSq === 0) {
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
}

function hitTestMember(
  mouseScreen: Point,
  member: GeometricMember,
  zoom: number,
  pan: Point,
  canvasHeight: number
): boolean {
  const { x: mx, y: my } = mouseScreen;

  switch (member.member_type) {
    case "beam": {
      const rect = beamScreenRect(member, zoom, pan, canvasHeight);
      return pointInRect(mx, my, rect.x, rect.y, rect.w, rect.h, HIT_TOLERANCE_PX);
    }

    case "column":
    case "footing": {
      const center = worldToScreen(member.start, zoom, pan, canvasHeight);
      const w = Math.max((member.meta.b_mm ?? 300) * zoom, 4);
      const h = Math.max((member.meta.h_mm ?? 300) * zoom, 4);
      return pointInRect(mx, my, center.x - w / 2, center.y - h / 2, w, h, HIT_TOLERANCE_PX);
    }

    case "slab":
    case "void":
    case "staircase": {
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
      const thickness = Math.max((member.meta.b_mm ?? 225) * zoom, 3);
      const dist = pointToLineDistance(mx, my, s.x, s.y, e.x, e.y);
      return dist <= thickness / 2 + HIT_TOLERANCE_PX;
    }

    default:
      return false;
  }
}

export function hitTestMembers(
  mouseScreen: Point,
  members: GeometricMember[],
  zoom: number,
  pan: Point,
  canvasHeight: number
): string | null {
  const priorityOrder: Record<string, number> = {
    column: 0,
    beam: 1,
    wall: 2,
    footing: 3,
    slab: 4,
    void: 5,
    staircase: 5,
  };

  const sorted = [...members].sort(
    (a, b) =>
      (priorityOrder[a.member_type] ?? 9) - (priorityOrder[b.member_type] ?? 9)
  );

  for (const member of sorted) {
    if (hitTestMember(mouseScreen, member, zoom, pan, canvasHeight)) {
      return member.member_id;
    }
  }

  return null;
}

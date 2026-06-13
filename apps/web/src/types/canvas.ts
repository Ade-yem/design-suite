/**
 * @file canvas.ts
 * @description Core type definitions for the interactive structural canvas.
 *
 * These types mirror the backend parser's output schema (`GeometricMember`)
 * and define the data contract between the Python Vision Agent and the
 * HTML5 Canvas rendering engine.
 *
 * All coordinate values are in DXF space (millimetres) unless explicitly
 * noted as screen-space pixels.
 */

// ── Geometric Primitives ────────────────────────────────────────────────────

/**
 * A 2D point in either DXF world space (mm) or screen space (px).
 *
 * @property x - Horizontal coordinate.
 * @property y - Vertical coordinate (DXF: up-positive; Screen: down-positive).
 */
export interface Point {
  x: number;
  y: number;
}

/**
 * Axis-aligned bounding box of all parsed members.
 * Used for fit-to-view calculations and viewport clipping.
 *
 * @property xMin - Minimum X coordinate in DXF space.
 * @property yMin - Minimum Y coordinate in DXF space.
 * @property xMax - Maximum X coordinate in DXF space.
 * @property yMax - Maximum Y coordinate in DXF space.
 */
export interface BoundingBox {
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
}

// ── Structural Member Schema ────────────────────────────────────────────────

/**
 * Supported structural member classifications.
 *
 * These directly map to the `member_type` field returned by the
 * Vision Agent's LLM classification step (`agents/parser.py`).
 */
export type MemberType =
  | "beam"
  | "column"
  | "slab"
  | "wall"
  | "footing"
  | "staircase"
  | "void";

/**
 * Cross-section and dimensional metadata for a structural member.
 *
 * The parser populates these fields from DXF geometry analysis
 * and LLM classification. All dimensions are in millimetres
 * unless suffixed with `_m`.
 *
 * @property b_mm    - Cross-section width in mm (e.g. beam web width).
 * @property h_mm    - Cross-section depth/height in mm.
 * @property L_clear - Clear span in metres (beams, slabs).
 * @property Lx      - Slab short span in mm.
 * @property Ly      - Slab long span in mm.
 */
export interface MemberMeta {
  b_mm: number;
  h_mm: number;
  L_clear?: number;
  Lx?: number;
  Ly?: number;
  [key: string]: unknown;
}

/**
 * A single parsed structural member as produced by the Vision Agent.
 *
 * This is the primary data unit consumed by the canvas renderer.
 * Each member has a unique ID, a type classification, DXF-space
 * coordinates, and dimensional metadata.
 *
 * @property member_id   - Unique label (e.g. "B1", "C3", "S-A1").
 * @property member_type - Structural classification.
 * @property start            - Start point in DXF coordinate space (mm). For slabs/voids
 *                              this is the AABB min corner derived from boundary_polygon.
 * @property end              - End point in DXF coordinate space (mm). For slabs/voids
 *                              this is the AABB max corner derived from boundary_polygon.
 * @property boundary_polygon - Optional explicit polygon vertices (slabs, voids). When
 *                              present the renderer draws the true shape rather than a
 *                              bounding rectangle.
 * @property meta             - Cross-section and dimensional metadata.
 */
export interface GeometricMember {
  member_id: string;
  member_type: MemberType;
  start_point?: Point | null;
  end_point?: Point | null;
  center_point?: Point | null;
  boundary_polygon?: Point[] | null;
  meta: MemberMeta;
  spans_m?: number[];
}

// ── Scale & Parsing Metadata ────────────────────────────────────────────────

/**
 * Scale and unit information detected during DXF parsing.
 *
 * @property factor    - Numeric multiplier (e.g. 0.001 for mm→m).
 * @property unit      - Human-readable unit label ("mm" | "m").
 * @property detected  - True if the parser auto-detected the scale.
 * @property confirmed - True if the engineer has confirmed the scale.
 */
export interface ScaleInfo {
  factor: number;
  unit: string;
  detected: boolean;
  confirmed: boolean;
}

/**
 * Full parsed geometry payload returned by `GET /api/v1/files/{id}/parsed`.
 *
 * This is the top-level response the frontend fetches after a successful
 * DXF/PDF parse, and the data source for the canvas rendering engine.
 *
 * @property members          - Array of parsed structural members.
 * @property scale            - Scale and unit metadata.
 * @property raw_entity_count - Number of raw DXF entities processed.
 * @property parse_warnings   - Non-fatal warnings generated during parse.
 */
export interface ParsedGeometry {
  members: GeometricMember[];
  scale: ScaleInfo;
  raw_entity_count?: number;
  parse_warnings?: string[];
}

// ── Canvas Interaction State ────────────────────────────────────────────────

/**
 * Active tool mode for the canvas viewport.
 *
 * - `"select"` — Click to select/hover members, show property inspector.
 * - `"pan"`    — Click and drag to pan the viewport.
 */
export type CanvasTool = "select" | "pan";

/**
 * Verification status of the parsed geometry.
 *
 * - `"pending"`    — Geometry parsed but not yet reviewed.
 * - `"submitting"` — Verification request in flight.
 * - `"verified"`   — Engineer confirmed; pipeline can proceed.
 * - `"error"`      — Verification request failed.
 */
export type VerificationStatus = "pending" | "submitting" | "verified" | "error";

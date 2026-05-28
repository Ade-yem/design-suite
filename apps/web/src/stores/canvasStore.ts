/**
 * @file canvasStore.ts
 * @description Zustand state store for the interactive structural canvas.
 *
 * Manages all transient canvas state: parsed geometry, viewport transform
 * (zoom/pan), selection, hover, tool mode, and verification status.
 *
 * This store is NOT persisted — canvas state is reconstructed from the
 * backend on each project load. Persisting zoom/pan across sessions would
 * be misleading if the parser output has changed.
 *
 * Usage
 * -----
 * ```ts
 * const members = useCanvasStore(s => s.members);
 * const { loadGeometry, selectMember } = useCanvasStore();
 * ```
 *
 * Scale at Scale
 * --------------
 * At large member counts (200+), the draw loop should read state via
 * `useCanvasStore.getState()` inside `requestAnimationFrame` rather than
 * subscribing to every state change. The store's `selectMember` and
 * `hoverMember` actions are designed to be called at mouse-event frequency
 * (~60 Hz) without causing unnecessary re-renders.
 */

import { create } from "zustand";
import type {
  GeometricMember,
  MemberType,
  ScaleInfo,
  BoundingBox,
  Point,
  CanvasTool,
  VerificationStatus,
  ParsedGeometry,
} from "@/types/canvas";

/**
 * Normalize a raw backend member to the frontend GeometricMember shape.
 *
 * The Vision Agent returns `start_point`/`end_point`/`center_point` while the
 * canvas renderer expects `start`/`end`.  Columns use `center_point` for both.
 */
function normalizeBackendMember(raw: unknown): GeometricMember {
  const m = raw as Record<string, unknown>;
  const startRaw = (m.start ?? m.start_point ?? m.center_point ?? { x: 0, y: 0 }) as Point;
  const endRaw = (m.end ?? m.end_point ?? m.center_point ?? startRaw) as Point;
  return {
    member_id: m.member_id as string,
    member_type: m.member_type as MemberType,
    start: startRaw,
    end: endRaw,
    meta: (m.meta ?? { b_mm: 300, h_mm: 500 }) as GeometricMember["meta"],
  };
}

// ── Bounding Box Computation ────────────────────────────────────────────────

/**
 * Compute the axis-aligned bounding box of all parsed members.
 *
 * Iterates over every member's start and end coordinates plus any
 * slab dimensions (Lx, Ly) to ensure the bounding box fully
 * contains all rendered geometry.
 *
 * @param members - Array of parsed structural members.
 * @returns The computed bounding box, or null if no members exist.
 */
function computeBounds(members: GeometricMember[]): BoundingBox | null {
  if (members.length === 0) return null;

  let xMin = Infinity;
  let yMin = Infinity;
  let xMax = -Infinity;
  let yMax = -Infinity;

  for (const m of members) {
    // Core start/end points
    const points: Point[] = [m.start, m.end];

    // For slabs, consider the full rectangular extent
    if (m.member_type === "slab" && m.meta.Lx && m.meta.Ly) {
      const cx = (m.start.x + m.end.x) / 2;
      const cy = (m.start.y + m.end.y) / 2;
      const halfLx = m.meta.Lx / 2;
      const halfLy = m.meta.Ly / 2;
      points.push(
        { x: cx - halfLx, y: cy - halfLy },
        { x: cx + halfLx, y: cy + halfLy }
      );
    }

    // For columns, consider the section size
    if (m.member_type === "column" && m.meta.b_mm && m.meta.h_mm) {
      const halfB = m.meta.b_mm / 2;
      const halfH = m.meta.h_mm / 2;
      points.push(
        { x: m.start.x - halfB, y: m.start.y - halfH },
        { x: m.start.x + halfB, y: m.start.y + halfH }
      );
    }

    for (const p of points) {
      if (p.x < xMin) xMin = p.x;
      if (p.y < yMin) yMin = p.y;
      if (p.x > xMax) xMax = p.x;
      if (p.y > yMax) yMax = p.y;
    }
  }

  return { xMin, yMin, xMax, yMax };
}

/**
 * Compute the zoom level and pan offset that centers all members
 * within the canvas viewport with padding.
 *
 * @param bounds   - Bounding box of all members in DXF space.
 * @param canvasW  - Canvas width in pixels.
 * @param canvasH  - Canvas height in pixels.
 * @param padding  - Fraction of viewport to use as padding (default 0.1 = 10%).
 * @returns Object with computed zoom and pan values.
 */
function computeFitTransform(
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

  // Center the geometry: pan so the bounding-box center maps to canvas center
  const panX = canvasW / 2 - (bounds.xMin + dxfW / 2) * zoom;
  const panY = canvasH / 2 + (bounds.yMin + dxfH / 2) * zoom;

  return { zoom, pan: { x: panX, y: panY } };
}

// ── Store Interface ─────────────────────────────────────────────────────────

/**
 * Canvas store state — the data layer of the rendering engine.
 */
interface CanvasState {
  /** Parsed structural members currently displayed on the canvas. */
  members: GeometricMember[];

  /** Scale and unit metadata from the parser. */
  scale: ScaleInfo | null;

  /** Bounding box of all members (DXF space), computed on load. */
  bounds: BoundingBox | null;

  /** Current zoom level (1.0 = 1 DXF unit : 1 screen pixel). */
  zoom: number;

  /** Current pan offset in screen pixels. */
  pan: Point;

  /** ID of the currently selected member, or null. */
  selectedMemberId: string | null;

  /** ID of the member currently under the cursor, or null. */
  hoveredMemberId: string | null;

  /** Active interaction tool mode. */
  activeTool: CanvasTool;

  /** Whether parsed geometry has been loaded into the store. */
  isGeometryLoaded: boolean;

  /** Current verification gate status. */
  verificationStatus: VerificationStatus;

  /** Error message from the last failed verification attempt. */
  verifyError: string | null;

  /** Live DXF world coordinates under the mouse cursor. */
  mouseWorldPos: Point;
}

/**
 * Canvas store actions — mutators for the rendering engine state.
 */
interface CanvasActions {
  /**
   * Load parsed geometry from the backend into the store.
   * Computes bounding box and resets interaction state.
   *
   * @param data - Full parsed geometry payload from the API.
   */
  loadGeometry: (data: ParsedGeometry) => void;

  /**
   * Set the zoom level.
   * Clamped between 0.01 (extreme zoom-out) and 100 (extreme zoom-in).
   *
   * @param z - New zoom level.
   */
  setZoom: (z: number) => void;

  /**
   * Set the pan offset in screen pixels.
   *
   * @param p - New pan position.
   */
  setPan: (p: Point) => void;

  /**
   * Compute and apply zoom/pan to fit all members within the viewport.
   *
   * @param canvasW - Canvas element width in pixels.
   * @param canvasH - Canvas element height in pixels.
   */
  fitToView: (canvasW: number, canvasH: number) => void;

  /**
   * Set the currently selected member.
   *
   * @param id - Member ID to select, or null to deselect.
   */
  selectMember: (id: string | null) => void;

  /**
   * Set the currently hovered member.
   *
   * @param id - Member ID under the cursor, or null.
   */
  hoverMember: (id: string | null) => void;

  /**
   * Switch the active canvas interaction tool.
   *
   * @param tool - The tool mode to activate.
   */
  setTool: (tool: CanvasTool) => void;

  /**
   * Update the live mouse position in DXF world coordinates.
   *
   * @param p - Current cursor position in DXF space.
   */
  setMouseWorldPos: (p: Point) => void;

  /**
   * Update properties of a specific member.
   * Only modifies local state — changes are not sent to the backend
   * until the engineer confirms via the verification gate.
   *
   * @param id    - Member ID to update.
   * @param patch - Partial member data to merge.
   */
  updateMember: (
    id: string,
    patch: Partial<Pick<GeometricMember, "meta">>
  ) => void;

  /**
   * Delete a member from the local canvas state.
   * The deletion is applied to the backend only when the engineer
   * confirms geometry via the verification gate.
   *
   * @param id - Member ID to remove.
   */
  deleteMember: (id: string) => void;

  /**
   * Set the verification gate status.
   *
   * @param status - New verification status.
   * @param error  - Error message if status is "error".
   */
  setVerificationStatus: (
    status: VerificationStatus,
    error?: string | null
  ) => void;

  /**
   * Discard all local edits and reload geometry from the backend.
   * Resets verification status to "pending".
   */
  resetGeometry: () => void;

  /**
   * Clear all canvas state. Called when switching projects or signing out.
   */
  clearCanvas: () => void;
}

export type CanvasStore = CanvasState & CanvasActions;

// ── Initial State ───────────────────────────────────────────────────────────

const INITIAL_STATE: CanvasState = {
  members: [],
  scale: null,
  bounds: null,
  zoom: 1,
  pan: { x: 0, y: 0 },
  selectedMemberId: null,
  hoveredMemberId: null,
  activeTool: "select",
  isGeometryLoaded: false,
  verificationStatus: "pending",
  verifyError: null,
  mouseWorldPos: { x: 0, y: 0 },
};

// ── Store ───────────────────────────────────────────────────────────────────

export const useCanvasStore = create<CanvasStore>()((set, get) => ({
  ...INITIAL_STATE,

  loadGeometry: (data) => {
    const members = (data.members ?? []).map(normalizeBackendMember);
    const bounds = computeBounds(members);
    set({
      members,
      scale: data.scale ?? null,
      bounds,
      isGeometryLoaded: members.length > 0,
      verificationStatus: "pending",
      verifyError: null,
      selectedMemberId: null,
      hoveredMemberId: null,
    });
  },

  setZoom: (z) => {
    const clamped = Math.max(0.01, Math.min(100, z));
    set({ zoom: clamped });
  },

  setPan: (p) => set({ pan: p }),

  fitToView: (canvasW, canvasH) => {
    const { bounds } = get();
    if (!bounds) return;
    const { zoom, pan } = computeFitTransform(bounds, canvasW, canvasH);
    set({ zoom, pan });
  },

  selectMember: (id) => set({ selectedMemberId: id }),

  hoverMember: (id) => {
    // Avoid unnecessary state updates when the hovered member hasn't changed
    if (get().hoveredMemberId === id) return;
    set({ hoveredMemberId: id });
  },

  setTool: (tool) => set({ activeTool: tool }),

  setMouseWorldPos: (p) => {
    // Write directly without triggering re-renders for non-subscribed consumers.
    // Components that need live coordinates should read from getState().
    set({ mouseWorldPos: p });
  },

  updateMember: (id, patch) => {
    set((state) => ({
      members: state.members.map((m) =>
        m.member_id === id ? { ...m, meta: { ...m.meta, ...patch.meta } } : m
      ),
      bounds: computeBounds(
        state.members.map((m) =>
          m.member_id === id ? { ...m, meta: { ...m.meta, ...patch.meta } } : m
        )
      ),
    }));
  },

  deleteMember: (id) => {
    set((state) => {
      const next = state.members.filter((m) => m.member_id !== id);
      return {
        members: next,
        bounds: computeBounds(next),
        selectedMemberId:
          state.selectedMemberId === id ? null : state.selectedMemberId,
        hoveredMemberId:
          state.hoveredMemberId === id ? null : state.hoveredMemberId,
      };
    });
  },

  setVerificationStatus: (status, error = null) =>
    set({ verificationStatus: status, verifyError: error }),

  resetGeometry: () => {
    set({
      verificationStatus: "pending",
      verifyError: null,
      selectedMemberId: null,
      hoveredMemberId: null,
    });
  },

  clearCanvas: () => set(INITIAL_STATE),
}));

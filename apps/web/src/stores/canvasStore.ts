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
import { computeBounds, computeFitTransform } from "@/lib/canvas/transform";

/**
 * Normalize a raw backend member to the frontend GeometricMember shape.
 *
 * The Vision Agent returns `start_point`/`end_point`/`center_point` while the
 * canvas renderer expects `start`/`end`.  Slabs and voids arrive with a
 * `boundary_polygon` array; their `start`/`end` are derived as AABB corners so
 * that bounding-box logic (fit-to-view, hit test fallback) still works.
 */
function normalizeBackendMember(raw: unknown): GeometricMember {
  const m = raw as Record<string, unknown>;
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

  // Columns arrive with section dims under `b`/`h`; beams/walls use `b_mm`/`h_mm`.
  // Normalise to `b_mm`/`h_mm` so the renderer, bounds, and hit-test stay uniform.
  const rawMeta = (m.meta ?? {}) as Record<string, unknown>;
  const meta = {
    ...rawMeta,
    b_mm: (rawMeta.b_mm ?? rawMeta.b ?? 300) as number,
    h_mm: (rawMeta.h_mm ?? rawMeta.h ?? 500) as number,
  } as GeometricMember["meta"];

  return {
    member_id: m.member_id as string,
    member_type: m.member_type as MemberType,
    start: startRaw,
    end: endRaw,
    boundary_polygon: polygon,
    meta,
  };
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

  /** The most recently deleted member, retained so the delete can be undone. */
  lastDeleted: GeometricMember | null;
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
   * Re-insert the most recently deleted member, undoing the last delete.
   * No-op if nothing has been deleted since the last load.
   */
  restoreLastDeleted: () => void;

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
  lastDeleted: null,
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
      const removed = state.members.find((m) => m.member_id === id) ?? null;
      const next = state.members.filter((m) => m.member_id !== id);
      return {
        members: next,
        bounds: computeBounds(next),
        lastDeleted: removed,
        selectedMemberId:
          state.selectedMemberId === id ? null : state.selectedMemberId,
        hoveredMemberId:
          state.hoveredMemberId === id ? null : state.hoveredMemberId,
      };
    });
  },

  restoreLastDeleted: () => {
    set((state) => {
      if (!state.lastDeleted) return {};
      const next = [...state.members, state.lastDeleted];
      return {
        members: next,
        bounds: computeBounds(next),
        lastDeleted: null,
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

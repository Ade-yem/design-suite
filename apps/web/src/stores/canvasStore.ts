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
  MemberMeta,
  AnalysisStatus,
  MemberAnalysisResult,
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
export function normalizeBackendMember(raw: unknown): GeometricMember {
  const m = raw as Record<string, unknown>;
  const polygon = Array.isArray(m.boundary_polygon)
    ? (m.boundary_polygon as Point[])
    : undefined;

  const rawMeta = (m.meta ?? {}) as Record<string, unknown>;
  const meta = {
    ...rawMeta,
    b_mm: Number(rawMeta.b_mm ?? rawMeta.b ?? 300),
    h_mm: Number(rawMeta.h_mm ?? rawMeta.h ?? 500),
  } as MemberMeta;

  return {
    member_id: String(m.member_id ?? m.id ?? "Unknown"),
    member_type: (m.member_type ?? m.type ?? "beam") as MemberType,
    start_point: (m.start_point ?? null) as Point | null,
    end_point: (m.end_point ?? null) as Point | null,
    center_point: (m.center_point ?? null) as Point | null,
    boundary_polygon: polygon,
    meta,
    spans_m: Array.isArray(m.spans_m) ? (m.spans_m as number[]) : undefined,
    storey: (m.storey ?? null) as string | null,
    elevation_m:
      m.elevation_m === undefined || m.elevation_m === null
        ? null
        : Number(m.elevation_m),
  };
}

/**
 * Sorted list of distinct storey codes present in a member set (e.g.
 * `["L01", "L02"]`). Empty when the geometry has not been extrapolated into
 * storeys yet (single typical floor).
 */
export function deriveStoreys(members: GeometricMember[]): string[] {
  const set = new Set<string>();
  for (const m of members) {
    if (m.storey) set.add(m.storey);
  }
  return Array.from(set).sort();
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

  // ── Analysis overlay state ────────────────────────────────────────────────

  /**
   * When true, members on the canvas are colour-coded by their analysis
   * result (green = pass, red = fail, dashed neutral = skipped).
   * Toggled by the BarChart2 icon in the toolbar.
   */
  analysisOverlay: boolean;

  /**
   * Lookup map from member_id → AnalysisStatus, populated once per
   * session from `GET /api/v1/analysis/{project_id}/results`.
   * The draw loop reads this map to colour-code each member in O(1).
   */
  memberAnalysisMap: Map<string, AnalysisStatus>;

  /**
   * Set of MemberType strings whose ID labels are currently hidden.
   * When a type is in this set, `drawAllLabels` skips every member of
   * that type, regardless of individual overrides.
   */
  hiddenLabelTypes: Set<MemberType>;

  /**
   * Set of individual member IDs whose ID labels are hidden.
   * Takes effect even when the member's type is not in `hiddenLabelTypes`.
   */
  hiddenLabelIds: Set<string>;

  /**
   * Currently active storey filter (e.g. "L01"), or null to show all storeys.
   * Only meaningful once geometry has been extrapolated into multiple storeys.
   */
  activeStorey: string | null;
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
   * Set the active storey filter, or null to show every storey.
   *
   * @param storey - Storey code (e.g. "L01") or null.
   */
  setActiveStorey: (storey: string | null) => void;

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
    patch: {
      meta?: Partial<MemberMeta>;
      member_type?: MemberType;
      spans_m?: number[];
    }
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

  /**
   * Compute zoom/pan to focus on a single member, then apply it.
   * Zooms and centers the canvas on the specified member.
   *
   * @param memberId - The member ID to focus on.
   */
  focusMember: (memberId: string, canvasW: number, canvasH: number) => void;

  // ── Analysis overlay actions ──────────────────────────────────────────────

  /**
   * Load analysis results from the backend into the store.
   * Builds the `memberAnalysisMap` lookup and keeps `analysisOverlay` at
   * whatever the engineer last set.
   *
   * @param results - Array of `MemberAnalysisResult` from the API.
   */
  setAnalysisResults: (results: MemberAnalysisResult[]) => void;

  /**
   * Toggle the analysis colour-coding overlay on/off.
   * No-op if no analysis results have been loaded.
   */
  toggleAnalysisOverlay: () => void;

  /**
   * Toggle label visibility for an entire member type.
   * If the type is currently hidden, it becomes visible; vice-versa.
   *
   * @param type - The `MemberType` to toggle.
   */
  toggleLabelType: (type: MemberType) => void;

  /**
   * Toggle label visibility for a single member by ID.
   *
   * @param id - The member ID whose label to toggle.
   */
  toggleLabelMember: (id: string) => void;

  /**
   * Reset all label visibility overrides so every member label is visible.
   */
  resetLabelVisibility: () => void;
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
  // Analysis overlay
  analysisOverlay: false,
  memberAnalysisMap: new Map(),
  hiddenLabelTypes: new Set(),
  hiddenLabelIds: new Set(),
  activeStorey: null,
};

// ── Store ───────────────────────────────────────────────────────────────────

export const useCanvasStore = create<CanvasStore>()((set, get) => ({
  ...INITIAL_STATE,

  loadGeometry: (data) => {
    const members = (data.members ?? []).map(normalizeBackendMember);
    const bounds = computeBounds(members);
    const storeys = deriveStoreys(members);
    set({
      members,
      scale: data.scale ?? null,
      bounds,
      isGeometryLoaded: members.length > 0,
      verificationStatus: "pending",
      verifyError: null,
      selectedMemberId: null,
      hoveredMemberId: null,
      // Multi-storey plans overlap in plan view, so default to the lowest
      // storey; single-floor geometry shows everything (null filter).
      activeStorey: storeys.length > 1 ? storeys[0] : null,
    });
  },

  setActiveStorey: (storey) => set({ activeStorey: storey }),

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
    // Merge meta shallowly, but also allow top-level fields (member_type
    // reclassification, spans_m) to be patched so corrections persist through
    // the verification gate.
    const applyPatch = (m: GeometricMember): GeometricMember => {
      if (m.member_id !== id) return m;
      const next: GeometricMember = { ...m };
      if (patch.member_type !== undefined) next.member_type = patch.member_type;
      if (patch.spans_m !== undefined) next.spans_m = patch.spans_m;
      if (patch.meta !== undefined) next.meta = { ...m.meta, ...patch.meta };
      return next;
    };
    set((state) => ({
      members: state.members.map(applyPatch),
      bounds: computeBounds(state.members.map(applyPatch)),
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

  focusMember: (memberId, canvasW, canvasH) => {
    const { members } = get();
    const member = members.find((m) => m.member_id === memberId);
    if (!member) return;

    // Compute bounds for this single member
    const bounds = computeBounds([member]);
    if (!bounds) return;

    // Reuse the fitTransform helper to get zoom/pan for this bounds
    // Use 5% padding for a balanced zoom
    const transform = computeFitTransform(bounds, canvasW, canvasH, 0.05);

    set({
      pan: transform.pan,
      zoom: transform.zoom,
    });
  },

  // ── Analysis overlay action implementations ───────────────────────────────

  setAnalysisResults: (results) => {
    const map = new Map<string, AnalysisStatus>();
    for (const r of results) {
      map.set(r.member_id, r.status);
    }
    set({
      memberAnalysisMap: map,
      // Auto-enable overlay when results are first loaded
      analysisOverlay: map.size > 0,
    });
  },

  toggleAnalysisOverlay: () => {
    set((state) => {
      // Only toggle if we actually have results to show
      if (state.memberAnalysisMap.size === 0) return {};
      return { analysisOverlay: !state.analysisOverlay };
    });
  },

  toggleLabelType: (type) => {
    set((state) => {
      const next = new Set(state.hiddenLabelTypes);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return { hiddenLabelTypes: next };
    });
  },

  toggleLabelMember: (id) => {
    set((state) => {
      const next = new Set(state.hiddenLabelIds);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return { hiddenLabelIds: next };
    });
  },

  resetLabelVisibility: () =>
    set({ hiddenLabelTypes: new Set(), hiddenLabelIds: new Set() }),
}));

"use client";

/**
 * @file CanvasViewport.tsx
 * @description Premium, high-fidelity interactive structural CAD viewport.
 *
 * Implements Phase 1, 2, and 3 of the structural canvas engine:
 * 1. Infinite pan and zoom (scroll-to-zoom centered on cursor).
 * 2. High-performance rendering of beams, columns, slabs, and openings.
 * 3. Tactile manipulation: click to select, hover tooltips, and properties editing/deletion.
 * 4. Safety Gate 1: Human-in-the-loop geometry verification bar.
 *
 * This file has been refactored and modularized into subcomponents to maintain the highest
 * architectural code quality and support double-file (DXF + PDF) staging areas concurrently.
 *
 * @module components/CanvasViewport
 */

import * as React from "react";
import {
  useState,
  useCallback,
  useMemo,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useCanvasStore } from "@/stores/canvasStore";
import { useAnalysisStore } from "@/stores/analysisStore";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { screenToWorld, zoomTowardPoint } from "@/lib/canvas/transform";
import { drawDotGrid } from "@/lib/canvas/drawGrid";
import { drawMember } from "@/lib/canvas/drawMembers";
import { drawAllLabels } from "@/lib/canvas/drawLabels";
import { hitTestMembers } from "@/lib/canvas/hitTest";
import type { Point, ParsedGeometry } from "@/types/canvas";

import { CanvasToolbar } from "./CanvasToolbar";
import { FloorSwitcher } from "./FloorSwitcher";
import { CoordinateReadout } from "./CoordinateReadout";
import { MemberTooltip } from "./MemberTooltip";
import { PropertyInspector, type MemberPropertyPatch } from "./PropertyInspector";
import { CanvasUploader, type CanvasUploaderHandle } from "./CanvasUploader";
import { MembersPanel } from "./MembersPanel";
import { GeometryGate } from "./GeometryGate";
import { LabelVisibilityModal } from "./LabelVisibilityModal";
import { useProjectSocket } from "@/hooks/useProjectSocket";
import { Loader2 } from "lucide-react";
import { useProjectStore } from "@/stores/projectStore";
import { CanvasLoading } from "./CanvasLoading";


export interface CanvasViewportHandle {
  /** Public API: lets parent elements trigger DXF file browsing */
  triggerFilePicker: () => void;
}

interface ParsedGeometrySummary {
  memberCount: number;
  scale: { factor: number; unit: string };
}

interface CanvasViewportProps {
  projectId: string;
  onParsed?: (summary: ParsedGeometrySummary) => void;
  onUploadStart?: () => void;
}

type UploadState = "not ready" | "idle" | "done" | "parsing";

export const CanvasViewport = forwardRef<
  CanvasViewportHandle,
  CanvasViewportProps
>(function CanvasViewport(
  { projectId, onParsed, onUploadStart },
  ref,
): React.ReactElement {
  // ── Store state & actions ────────────────────────────────────────────────
  const {
    members,
    scale,
    zoom,
    pan,
    selectedMemberId,
    hoveredMemberId,
    activeTool,
    verificationStatus,
    mouseWorldPos,
    loadGeometry,
    setZoom,
    setPan,
    fitToView,
    selectMember,
    hoverMember,
    setTool,
    setMouseWorldPos,
    updateMember,
    deleteMember,
    restoreLastDeleted,
    setVerificationStatus,
    resetGeometry,
    focusMember,
    // Analysis overlay
    analysisOverlay,
    memberAnalysisMap,
    hiddenLabelTypes,
    hiddenLabelIds,
    setAnalysisResults,
    toggleAnalysisOverlay,
    toggleLabelType,
    toggleLabelMember,
    resetLabelVisibility,
    activeStorey,
    setActiveStorey,
  } = useCanvasStore();

  // Members visible on the canvas — filtered to the active storey when the
  // geometry has been extrapolated into multiple floors. Members without a
  // storey (single typical floor) are always shown.
  const visibleMembers = useMemo(
    () =>
      activeStorey
        ? members.filter((m) => !m.storey || m.storey === activeStorey)
        : members,
    [members, activeStorey]
  );

  // Distinct storey codes available for the floor switcher.
  const storeys = useMemo(() => {
    const set = new Set<string>();
    for (const m of members) if (m.storey) set.add(m.storey);
    return Array.from(set).sort();
  }, [members]);


  // ── Component State ──────────────────────────────────────────────────────
  const [uploadState, setUploadState] = useState<UploadState>("not ready");
  const [tooltipPos, setTooltipPos] = useState<Point | null>(null);
  const [scaleUnit, setScaleUnit] = useState<string>("mm");
  const [scaleFactor, setScaleFactor] = useState<number>(1);
  const [isConfirmingScale, setIsConfirmingScale] = useState(false);
  const [isLabelModalOpen, setIsLabelModalOpen] = useState(false);


  // Regeneration state
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateProgress, setRegenerateProgress] = useState<number>(0);
  const [regenerateStep, setRegenerateStep] = useState<string>("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Establish dynamic WebSocket connection for live regeneration progress updates
  useProjectSocket(projectId, {
    onJobUpdate: (msg) => {
      if (activeJobId && msg.job_id === activeJobId) {
        if (msg.status === "complete") {
          fetchExistingGeometry().then(() => {
            setIsRegenerating(false);
            setActiveJobId(null);
            setRegenerateProgress(0);
            setRegenerateStep("");
            toast.success("Geometry layout regenerated successfully.");
          });
        } else if (msg.status === "failed") {
          setIsRegenerating(false);
          setActiveJobId(null);
          setRegenerateProgress(0);
          setRegenerateStep("");
          toast.error(msg.errors?.[0] ?? "Geometry regeneration failed.");
        } else {
          setRegenerateProgress(msg.progress_pct);
          setRegenerateStep(msg.current_step);
        }
      }
    },
  });

  // Refs
  const uploaderRef = useRef<CanvasUploaderHandle>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isPanningRef = useRef(false);
  const startPanRef = useRef<Point>({ x: 0, y: 0 });

  // Keep a mutable ref of the callback to prevent recreation of fetchExistingGeometry
  const onParsedRef = useRef(onParsed);
  useEffect(() => {
    onParsedRef.current = onParsed;
  }, [onParsed]);

  // Expose DXF browse trigger to parent component hooks
  useImperativeHandle(ref, () => ({
    triggerFilePicker: () => {
      uploaderRef.current?.triggerDxfPicker();
    },
  }));

  // ── Fetch existing parsed geometry on mount or project switch ──────────
  const fetchExistingGeometry = useCallback(async () => {
    try {
      if (!projectId) {
        setUploadState("idle");
        return;
      }
      setUploadState((prev) => (prev === "done" ? "done" : "not ready"));
      const { data } = await apiClient.get<ParsedGeometry>(
        `/api/v1/files/${projectId}/parsed`,
      );
      loadGeometry(data);
      setUploadState("done");
      if (onParsedRef.current) {
        onParsedRef.current({
          memberCount: data.members?.length ?? 0,
          scale: data.scale ?? { factor: 1, unit: "mm" },
        });
      }
    } catch {
      // No parsed geometry exists yet (404) — show idle upload screen
      setUploadState("idle");
    }
  }, [projectId, loadGeometry]);

  const activeProject = useProjectStore((s) => s.activeProject);
  useEffect(() => {
    if (activeProject && activeProject.project_id === projectId) {
      const isVerified = activeProject.pipeline_status_ordinal >= 2; // geometry_verified = 2
      if (isVerified) {
        setVerificationStatus("verified");
      }
    }
  }, [activeProject, projectId, setVerificationStatus]);

  // ── Fetch analysis results for colour-coding overlay ────────────────────
  useEffect(() => {
    if (
      !activeProject ||
      activeProject.project_id !== projectId ||
      activeProject.pipeline_status_ordinal < 4  // ANALYSIS_COMPLETE = 4
    ) {
      return;
    }
    apiClient
      .get<{ members: Array<{ member_id: string; status: string; reason?: string }> }>(
        `/api/v1/analysis/${projectId}/results`
      )
      .then(({ data }) => {
        if (Array.isArray(data?.members)) {
          setAnalysisResults(
            data.members.map((m) => ({
              member_id: m.member_id,
              status: (m.status as "pass" | "fail" | "skipped") ?? "unknown",
              reason: m.reason,
            }))
          );
        }
      })
      .catch(() => {
        // Non-fatal: overlay just won't be displayed
      });
  }, [activeProject, projectId, setAnalysisResults]);

  // ── Fetch full analysis + design results for the member detail drawer ─────
  const fetchAnalysisDetail = useAnalysisStore((s) => s.fetchResults);
  const fetchDesignDetail = useAnalysisStore((s) => s.fetchDesign);
  useEffect(() => {
    if (
      !activeProject ||
      activeProject.project_id !== projectId ||
      activeProject.pipeline_status_ordinal < 4 // ANALYSIS_COMPLETE = 4
    ) {
      return;
    }
    fetchAnalysisDetail(projectId);
    fetchDesignDetail(projectId);
  }, [activeProject, projectId, fetchAnalysisDetail, fetchDesignDetail]);

  // Whether the analysis drawer experience is unlocked for this project.
  const analysisReady =
    !!activeProject &&
    activeProject.project_id === projectId &&
    activeProject.pipeline_status_ordinal >= 4;
  const openMemberDrawer = useAnalysisStore((s) => s.openForMember);


  useEffect(() => {
    fetchExistingGeometry();
  }, [projectId, fetchExistingGeometry]);

  // Sync local scale form state when scale is loaded from backend
  useEffect(() => {
    if (scale) {
      setScaleUnit(scale.unit ?? "mm");
      setScaleFactor(scale.factor ?? 1);
    }
  }, [scale]);

  const handleConfirmScale = useCallback(async () => {
    setIsConfirmingScale(true);
    try {
      await apiClient.put(`/api/v1/files/${projectId}/scale`, {
        scale_factor: scaleFactor,
        unit_label: scaleUnit,
        confirmed: true,
      });
      // Reload geometry so scale.confirmed flips to true in the store
      await fetchExistingGeometry();
    } catch {
      // Non-fatal — engineer can retry; geometry is still displayed
    } finally {
      setIsConfirmingScale(false);
    }
  }, [projectId, scaleFactor, scaleUnit, fetchExistingGeometry]);

  // ── Drawing loop using requestAnimationFrame ─────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear the canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Draw dot grid background
    drawDotGrid(ctx, canvas.width, canvas.height, zoom, pan);

    // 2. Draw structural members with optional analysis overlay
    for (const member of visibleMembers) {
      const isSelected = member.member_id === selectedMemberId;
      const isHovered = member.member_id === hoveredMemberId;
      const analysisStatus =
        analysisOverlay ? memberAnalysisMap.get(member.member_id) : undefined;
      drawMember(ctx, member, zoom, pan, canvas.height, isSelected, isHovered, analysisStatus);
    }

    // 3. Draw labels and dimension pills on top, with visibility filters
    drawAllLabels(
      ctx,
      visibleMembers,
      zoom,
      pan,
      canvas.width,
      canvas.height,
      analysisOverlay ? memberAnalysisMap : undefined,
      hiddenLabelTypes,
      hiddenLabelIds
    );
  }, [visibleMembers, zoom, pan, selectedMemberId, hoveredMemberId, analysisOverlay, memberAnalysisMap, hiddenLabelTypes, hiddenLabelIds]);


  // Setup rendering trigger
  useEffect(() => {
    let animFrameId: number;
    const render = () => {
      draw();
      animFrameId = requestAnimationFrame(render);
    };
    if (uploadState === "done" && canvasRef.current) {
      animFrameId = requestAnimationFrame(render);
    }
    return () => {
      cancelAnimationFrame(animFrameId);
    };
  }, [uploadState, draw]);

  // Resize canvas handler — intentionally stable (empty deps). The rAF loop
  // redraws every frame, so this only needs to update the backing-store size.
  // It must NOT depend on `draw` (which changes on every zoom/pan), or the
  // fit-to-view effect below would re-run on every zoom and snap the view back.
  const handleResize = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
  }, []);

  // Size the canvas and fit geometry to the viewport ONCE per geometry load.
  // Depends only on `uploadState` (handleResize/fitToView are stable), so
  // user zoom/pan is preserved instead of being reset on every interaction.
  useEffect(() => {
    if (uploadState !== "done" || !containerRef.current) return;

    handleResize();

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    resizeObserver.observe(containerRef.current);

    // Delay fit to view slightly to allow container sizing to settle
    const fitTimer = setTimeout(() => {
      fitToView(
        canvasRef.current?.width ?? 800,
        canvasRef.current?.height ?? 600,
      );
    }, 100);

    return () => {
      resizeObserver.disconnect();
      clearTimeout(fitTimer);
    };
  }, [uploadState, handleResize, fitToView]);

  // ── Mouse & Wheel Interaction Handlers ────────────────────────────────────

  const handleMouseDown = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Handle pan mode (Spacebar or Middle Click or Pan Tool active)
    if (activeTool === "pan" || e.button === 1 || e.shiftKey) {
      isPanningRef.current = true;
      startPanRef.current = { x: e.clientX - pan.x, y: e.clientY + pan.y };
      e.preventDefault();
      return;
    }

    // Handle Select Mode clicking (passing screen-space mouse position)
    const rect = canvas.getBoundingClientRect();
    const clickScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };

    const hitId = hitTestMembers(
      clickScreen,
      visibleMembers,
      zoom,
      pan,
      canvas.height,
    );
    selectMember(hitId);

    // Once analysis is complete, clicking a member opens the analysis &
    // calculation verification drawer for it.
    if (hitId && analysisReady) {
      openMemberDrawer(hitId);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const mouseWorld = screenToWorld(mouseScreen, zoom, pan, canvas.height);

    setMouseWorldPos(mouseWorld);

    if (isPanningRef.current) {
      const nextPan = {
        x: e.clientX - startPanRef.current.x,
        y: startPanRef.current.y - e.clientY,
      };
      setPan(nextPan);
    } else if (activeTool === "select") {
      const hoveredId = hitTestMembers(
        mouseScreen,
        visibleMembers,
        zoom,
        pan,
        canvas.height,
      );
      hoverMember(hoveredId);

      // Position tooltip slightly above the cursor
      if (hoveredId) {
        setTooltipPos({ x: mouseScreen.x, y: mouseScreen.y - 12 });
      } else {
        setTooltipPos(null);
      }
    }
  };

  const handleMouseUp = () => {
    isPanningRef.current = false;
  };

  // ── Passive Event Listeners for Zoom ────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || uploadState !== "done") return;

    /**
     * Natively handles scroll-to-zoom centered around the mouse cursor position.
     * Prevents default browser scroll behaviors (e.g. page zooming or viewport panning).
     *
     * @param {WheelEvent} e - Native browser WheelEvent.
     */
    const handleNativeWheel = (e: WheelEvent) => {
      e.preventDefault(); // Allowed because passive is false

      const rect = canvas.getBoundingClientRect();
      const mouseScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };

      const zoomFactor = 1.1;
      const nextZoom = e.deltaY < 0 ? zoom * zoomFactor : zoom / zoomFactor;
      const nextPan = zoomTowardPoint(mouseScreen, zoom, nextZoom, pan);

      setZoom(nextZoom);
      setPan(nextPan);
    };

    canvas.addEventListener("wheel", handleNativeWheel, { passive: false });
    return () => {
      canvas.removeEventListener("wheel", handleNativeWheel);
    };
  }, [uploadState, zoom, pan, setZoom, setPan]);

  // ── Property update actions ───────────────────────────────────────────────

  const handleSaveProperties = (patch: MemberPropertyPatch) => {
    if (!selectedMemberId) return;
    updateMember(selectedMemberId, patch);
    selectMember(null);
  };

  const handleDeleteMember = () => {
    if (selectedMemberId) {
      deleteMember(selectedMemberId);
      toast("Member deleted", {
        description:
          "Removed from the staged layout. Not saved until you confirm geometry.",
        action: {
          label: "Undo",
          onClick: () => restoreLastDeleted(),
        },
      });
    }
  };

  // ── Geometry Verification API handlers ───────────────────────────────────

  const handleConfirmGeometry = async (notes?: string) => {
    setVerificationStatus("submitting");
    try {
      const corrections = members.map((m) => ({
        member_id: m.member_id,
        member_type: m.member_type,
        start_point: m.start_point,
        end_point: m.end_point,
        center_point: m.center_point,
        boundary_polygon: m.boundary_polygon,
        meta: m.meta,
        spans_m: m.spans_m,
      }));

      await apiClient.put(`/api/v1/files/${projectId}/verify`, {
        confirmed: true,
        corrections,
        notes,
      });

      // Geometry is its own safety gate (Gate 1). Confirming it advances the
      // pipeline automatically — no hand-off to the chat — so the engineer's
      // single confirm action both locks the layout and unblocks load analysis.
      await apiClient.post(`/api/v1/pipeline/${projectId}/resume`);

      setVerificationStatus("verified");
      if (onParsedRef.current) {
        onParsedRef.current({
          memberCount: members.length,
          scale: scale ?? { factor: 1, unit: "mm" },
        });
      }
    } catch (err: unknown) {
      const msg =
        (err as { detail?: string }).detail ??
        "Failed to save verification gate.";
      setVerificationStatus("error", msg);
    }
  };

  const handleResetGeometry = async () => {
    resetGeometry();
    await fetchExistingGeometry();
  };

  const handleRegenerateLayout = async () => {
    setIsRegenerating(true);
    setRegenerateProgress(0);
    setRegenerateStep("Initiating layout regeneration...");
    setVerificationStatus("pending");
    resetGeometry();

    try {
      const { data } = await apiClient.post<{ job_id: string }>(
        `/api/v1/files/${projectId}/reparse`,
      );
      setActiveJobId(data.job_id);
    } catch (err: unknown) {
      const msg =
        (err as { detail?: string }).detail ??
        "Failed to trigger geometry regeneration.";
      toast.error(msg);
      setIsRegenerating(false);
      setRegenerateProgress(0);
      setRegenerateStep("");
    }
  };

  const handleZoomToMember = (memberId: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    focusMember(memberId, canvas.width, canvas.height);
  };

  const selectedMember = members.find((m) => m.member_id === selectedMemberId);
  const hoveredMember = members.find((m) => m.member_id === hoveredMemberId);

  return (
    <div className="h-full flex flex-row relative" ref={containerRef}>
      {/* Members panel: left dock (collapsible) */}
      {uploadState === "done" && (
        <MembersPanel
          members={members}
          selectedMemberId={selectedMemberId}
          onSelectMember={selectMember}
          onZoomToMember={handleZoomToMember}
        />
      )}

      {/* Canvas area: flex-1 container with floating layers */}
      <div className="flex-1 flex flex-col relative overflow-hidden bg-[#0b0f19] transition-colors select-none">
        {/* Absolute floating UI elements (positioned into this container, not the outer) */}
        {uploadState === "done" && (
          <>
            {/* Unified stepped Safety Gate 1 — replaces scale banner + geometry bar */}
            <GeometryGate
              scale={scale}
              scaleFactor={scaleFactor}
              scaleUnit={scaleUnit as "mm" | "m" | "cm"}
              onScaleUnitChange={setScaleUnit}
              onConfirmScale={handleConfirmScale}
              isConfirmingScale={isConfirmingScale}
              verificationStatus={verificationStatus}
              memberCount={members.length}
              onConfirmGeometry={handleConfirmGeometry}
              onResetGeometry={handleResetGeometry}
              onRegenerateLayout={handleRegenerateLayout}
              isRegenerating={isRegenerating}
            />

            {storeys.length > 1 && (
              <FloorSwitcher
                storeys={storeys}
                activeStorey={activeStorey}
                onChange={setActiveStorey}
              />
            )}

            <CanvasToolbar
              activeTool={activeTool}
              setTool={setTool}
              onZoomIn={() => setZoom(zoom * 1.2)}
              onZoomOut={() => setZoom(zoom / 1.2)}
              onFitToView={() =>
                fitToView(
                  canvasRef.current?.width ?? 800,
                  canvasRef.current?.height ?? 600,
                )
              }
              analysisOverlay={analysisOverlay}
              hasAnalysisResults={memberAnalysisMap.size > 0}
              onToggleAnalysisOverlay={toggleAnalysisOverlay}
              onOpenLabelModal={() => setIsLabelModalOpen((v) => !v)}
              isLabelModalOpen={isLabelModalOpen}
            />

            {isLabelModalOpen && (
              <LabelVisibilityModal
                members={members}
                hiddenLabelTypes={hiddenLabelTypes}
                hiddenLabelIds={hiddenLabelIds}
                onToggleType={toggleLabelType}
                onToggleMember={toggleLabelMember}
                onReset={resetLabelVisibility}
                onClose={() => setIsLabelModalOpen(false)}
              />
            )}


            <CoordinateReadout mouseWorldPos={mouseWorldPos} scale={scale} />

            {hoveredMember && tooltipPos && (
              <MemberTooltip
                hoveredMember={hoveredMember}
                tooltipPos={tooltipPos}
              />
            )}

            {/* Geometry editor is only for the pre-analysis phase; once
                analysis is complete the member analysis drawer takes over. */}
            {selectedMember && !analysisReady && (
              <PropertyInspector
                selectedMember={selectedMember}
                onDeselect={() => selectMember(null)}
                onDelete={handleDeleteMember}
                onSave={handleSaveProperties}
              />
            )}

            {analysisReady && (
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 px-3 py-1.5 rounded-full bg-card/90 backdrop-blur-sm border border-border/50 shadow-sm text-[11px] text-muted-foreground pointer-events-none">
                Analysis complete — click a member to inspect its calculations
              </div>
            )}
          </>
        )}

        {/* Viewport content area */}
        <div className="flex-1 relative overflow-hidden">
          {uploadState === "done" ? (
            <>
              <canvas
                ref={canvasRef}
                className="absolute inset-0 block cursor-crosshair"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
              />
              {isRegenerating && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-card/75 backdrop-blur-xs z-30">
                  <div className="flex flex-col items-center gap-4 bg-[#0b0f19]/80 px-8 py-6 rounded-xl border border-border/40 shadow-2xl">
                    <Loader2 className="h-10 w-10 text-primary animate-spin" />
                    <p className="text-sm font-semibold tracking-wide uppercase font-mono text-primary">
                      Regenerating Layout ({regenerateProgress.toFixed(0)}%)
                    </p>
                    <p className="text-xs text-muted-foreground font-mono text-center max-w-sm">
                      {regenerateStep}
                    </p>
                  </div>
                </div>
              )}
            </>
          ) : uploadState === "not ready" ? (
            <CanvasLoading />
          ) : (
            <CanvasUploader
              ref={uploaderRef}
              projectId={projectId}
              onUploadStart={onUploadStart}
              onParsed={fetchExistingGeometry}
            />
          )}
        </div>
      </div>
    </div>
  );
});

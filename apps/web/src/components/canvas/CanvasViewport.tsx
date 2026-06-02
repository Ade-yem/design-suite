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
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { useCanvasStore } from "@/stores/canvasStore";
import { apiClient } from "@/lib/api";
import { screenToWorld, zoomTowardPoint } from "@/lib/canvas/transform";
import { drawDotGrid } from "@/lib/canvas/drawGrid";
import { drawMember } from "@/lib/canvas/drawMembers";
import { drawAllLabels } from "@/lib/canvas/drawLabels";
import { hitTestMembers } from "@/lib/canvas/hitTest";
import type { Point, ParsedGeometry } from "@/types/canvas";

// Imported split-out subcomponents
import { CanvasToolbar } from "./CanvasToolbar";
import { CoordinateReadout } from "./CoordinateReadout";
import { MemberTooltip } from "./MemberTooltip";
import { PropertyInspector } from "./PropertyInspector";
import { GeometryVerificationBar } from "./GeometryVerificationBar";
import { CanvasUploader, type CanvasUploaderHandle } from "./CanvasUploader";

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

type UploadState = "idle" | "done" | "parsing";

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
    setVerificationStatus,
    resetGeometry,
  } = useCanvasStore();

  // ── Component State ──────────────────────────────────────────────────────
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [tooltipPos, setTooltipPos] = useState<Point | null>(null);
  const [scaleUnit, setScaleUnit] = useState<string>("mm");
  const [scaleFactor, setScaleFactor] = useState<number>(1);
  const [isConfirmingScale, setIsConfirmingScale] = useState(false);

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
      setUploadState("parsing");
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

    // 2. Draw structural members
    for (const member of members) {
      const isSelected = member.member_id === selectedMemberId;
      const isHovered = member.member_id === hoveredMemberId;
      drawMember(ctx, member, zoom, pan, canvas.height, isSelected, isHovered);
    }

    // 3. Draw labels and dimension pills on top
    drawAllLabels(ctx, members, zoom, pan, canvas.width, canvas.height);
  }, [members, zoom, pan, selectedMemberId, hoveredMemberId]);

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
    if (uploadState !== "done") return;
    handleResize();
    window.addEventListener("resize", handleResize);
    // Delay fit to view slightly to allow container sizing to settle
    const fitTimer = setTimeout(() => {
      fitToView(
        canvasRef.current?.width ?? 800,
        canvasRef.current?.height ?? 600,
      );
    }, 100);
    return () => {
      window.removeEventListener("resize", handleResize);
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
      startPanRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
      e.preventDefault();
      return;
    }

    // Handle Select Mode clicking (passing screen-space mouse position)
    const rect = canvas.getBoundingClientRect();
    const clickScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };

    const hitId = hitTestMembers(
      clickScreen,
      members,
      zoom,
      pan,
      canvas.height,
    );
    selectMember(hitId);
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
        y: e.clientY - startPanRef.current.y,
      };
      setPan(nextPan);
    } else if (activeTool === "select") {
      const hoveredId = hitTestMembers(
        mouseScreen,
        members,
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

  const handleSaveProperties = (
    width: number,
    depth: number,
    span: number | undefined,
  ) => {
    if (!selectedMemberId) return;

    updateMember(selectedMemberId, {
      meta: {
        b_mm: width,
        h_mm: depth,
        L_clear: span,
      },
    });
    selectMember(null);
  };

  const handleDeleteMember = () => {
    if (selectedMemberId) {
      deleteMember(selectedMemberId);
    }
  };

  // ── Geometry Verification API handlers ───────────────────────────────────

  const handleConfirmGeometry = async (notes: string) => {
    setVerificationStatus("submitting");
    try {
      const corrections = members.map((m) => ({
        member_id: m.member_id,
        member_type: m.member_type,
        start: m.start,
        end: m.end,
        meta: m.meta,
      }));

      await apiClient.put(`/api/v1/files/${projectId}/verify`, {
        confirmed: true,
        corrections,
        notes,
      });

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

  const selectedMember = members.find((m) => m.member_id === selectedMemberId);
  const hoveredMember = members.find((m) => m.member_id === hoveredMemberId);

  return (
    <div className="h-full flex flex-col relative" ref={containerRef}>
      {/* Absolute floating UI elements */}
      {uploadState === "done" && (
        <>
          {/* Scale confirmation banner — shown when scale was auto-detected but not yet confirmed */}
          {scale?.detected && !scale?.confirmed && (
            <div className="absolute top-0 inset-x-0 z-20 flex items-center gap-3 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 backdrop-blur-md">
              <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
              <span className="text-xs text-amber-200 font-medium flex-1">
                Scale auto-detected — please confirm before proceeding.
              </span>
              <span className="text-xs text-amber-300/70 font-mono">
                factor: {scaleFactor}
              </span>
              <select
                value={scaleUnit}
                onChange={(e) => setScaleUnit(e.target.value)}
                className="bg-muted/60 border border-border text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-amber-400 text-foreground"
              >
                <option value="mm">mm</option>
                <option value="m">m</option>
                <option value="cm">cm</option>
              </select>
              <button
                onClick={handleConfirmScale}
                disabled={isConfirmingScale}
                className="flex items-center gap-1.5 px-3 py-1 bg-amber-500 text-amber-950 text-xs font-semibold rounded hover:bg-amber-400 transition-all disabled:opacity-50 shrink-0"
              >
                {isConfirmingScale ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                Confirm Scale
              </button>
            </div>
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
          />

          <CoordinateReadout mouseWorldPos={mouseWorldPos} scale={scale} />

          {hoveredMember && tooltipPos && (
            <MemberTooltip
              hoveredMember={hoveredMember}
              tooltipPos={tooltipPos}
            />
          )}

          {selectedMember && (
            <PropertyInspector
              selectedMember={selectedMember}
              onDeselect={() => selectMember(null)}
              onDelete={handleDeleteMember}
              onSave={handleSaveProperties}
            />
          )}

          <GeometryVerificationBar
            verificationStatus={verificationStatus}
            memberCount={members.length}
            onConfirm={handleConfirmGeometry}
            onReset={handleResetGeometry}
          />
        </>
      )}

      {/* Viewport content area */}
      <div className="flex-1 bg-[#0b0f19] relative overflow-hidden transition-colors select-none">
        {uploadState === "done" ? (
          <canvas
            ref={canvasRef}
            className="absolute inset-0 block cursor-crosshair"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          />
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
  );
});

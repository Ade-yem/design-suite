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
 * @module components/CanvasViewport
 */

import {
  useState,
  useCallback,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import {
  Upload,
  FileUp,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Move,
  MousePointer,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Save,
  RotateCcw,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";
import { useCanvasStore } from "@/stores/canvasStore";
import {
  worldToScreen,
  screenToWorld,
  zoomTowardPoint,
} from "@/lib/canvas/transform";
import { drawDotGrid } from "@/lib/canvas/drawGrid";
import { drawMember } from "@/lib/canvas/drawMembers";
import { drawAllLabels } from "@/lib/canvas/drawLabels";
import { hitTestMembers } from "@/lib/canvas/hitTest";
import type { JobStatus } from "@/types/project";
import type { GeometricMember, Point, ParsedGeometry } from "@/types/canvas";

export interface CanvasViewportHandle {
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

type UploadState = "idle" | "uploading" | "parsing" | "done" | "error";

const POLL_INTERVAL_MS = 2000;
const ACCEPTED_EXTS = [".dxf", ".pdf"];

export const CanvasViewport = forwardRef<CanvasViewportHandle, CanvasViewportProps>(
  function CanvasViewport({ projectId, onParsed, onUploadStart }, ref) {
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
      verifyError,
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
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const [notes, setNotes] = useState("");
    const [tooltipPos, setTooltipPos] = useState<Point | null>(null);

    // Property Inspector Form state
    const [editWidth, setEditWidth] = useState("");
    const [editDepth, setEditDepth] = useState("");
    const [editSpan, setEditSpan] = useState("");

    // Refs
    const fileInputRef = useRef<HTMLInputElement>(null);
    const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const isPanningRef = useRef(false);
    const startPanRef = useRef<Point>({ x: 0, y: 0 });

    useImperativeHandle(ref, () => ({
      triggerFilePicker: () => fileInputRef.current?.click(),
    }));

    // ── Fetch existing parsed geometry on mount or project switch ──────────
    const fetchExistingGeometry = useCallback(async () => {
      try {
        setUploadState("parsing");
        const { data } = await apiClient.get<ParsedGeometry>(
          `/api/v1/files/${projectId}/parsed`
        );
        loadGeometry(data);
        setUploadState("done");
        if (onParsed) {
          onParsed({
            memberCount: data.members?.length ?? 0,
            scale: data.scale ?? { factor: 1, unit: "mm" },
          });
        }
      } catch {
        // No parsed geometry exists yet (404) — show idle upload screen
        setUploadState("idle");
      }
    }, [projectId, loadGeometry, onParsed]);

    useEffect(() => {
      fetchExistingGeometry();
      return () => {
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
      };
    }, [projectId, fetchExistingGeometry]);

    // ── Property inspector form updates on selection ─────────────────────────
    const selectedMember = members.find((m) => m.member_id === selectedMemberId);

    useEffect(() => {
      if (selectedMember) {
        setEditWidth(String(selectedMember.meta.b_mm ?? ""));
        setEditDepth(String(selectedMember.meta.h_mm ?? ""));
        setEditSpan(String(selectedMember.meta.L_clear ?? ""));
      } else {
        setEditWidth("");
        setEditDepth("");
        setEditSpan("");
      }
    }, [selectedMemberId, selectedMember]);

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

    // Resize canvas handler
    const handleResize = useCallback(() => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
      draw();
    }, [draw]);

    useEffect(() => {
      if (uploadState === "done") {
        handleResize();
        window.addEventListener("resize", handleResize);
        // Delay fit to view slightly to allow container sizing to settle
        setTimeout(() => {
          fitToView(canvasRef.current?.width ?? 800, canvasRef.current?.height ?? 600);
        }, 100);
      }
      return () => {
        window.removeEventListener("resize", handleResize);
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

      // Select mode hit testing
      if (activeTool === "select" && e.button === 0) {
        const rect = canvas.getBoundingClientRect();
        const mouseScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        const clickedId = hitTestMembers(
          mouseScreen,
          members,
          zoom,
          pan,
          canvas.height
        );
        selectMember(clickedId);
      }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const mouseScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };

      // Update coordinate readout and live world position
      const worldPos = screenToWorld(mouseScreen, zoom, pan, canvas.height);
      setMouseWorldPos({
        x: Number(worldPos.x.toFixed(3)),
        y: Number(worldPos.y.toFixed(3)),
      });

      if (isPanningRef.current) {
        setPan({
          x: e.clientX - startPanRef.current.x,
          y: e.clientY - startPanRef.current.y,
        });
        return;
      }

      // Proximity hover checking in select tool
      if (activeTool === "select") {
        const hoveredId = hitTestMembers(
          mouseScreen,
          members,
          zoom,
          pan,
          canvas.height
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

    const handleWheel = (e: React.WheelEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      e.preventDefault();

      const rect = canvas.getBoundingClientRect();
      const mouseScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };

      const zoomFactor = 1.1;
      const nextZoom = e.deltaY < 0 ? zoom * zoomFactor : zoom / zoomFactor;

      // Adjust pan coordinates so zoom is centered on the cursor
      const nextPan = zoomTowardPoint(mouseScreen, zoom, nextZoom, pan);

      setZoom(nextZoom);
      setPan(nextPan);
    };

    // ── Property update actions ───────────────────────────────────────────────

    const handleSaveProperties = () => {
      if (!selectedMemberId) return;
      const b = editWidth ? parseFloat(editWidth) : 0;
      const h = editDepth ? parseFloat(editDepth) : 0;
      const l = editSpan ? parseFloat(editSpan) : undefined;

      updateMember(selectedMemberId, {
        meta: {
          b_mm: b,
          h_mm: h,
          L_clear: l,
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

    const handleConfirmGeometry = async () => {
      setVerificationStatus("submitting");
      try {
        // Preparecorrections to pass downstream
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
        // Trigger page refresh to advance project stage
        if (onParsed) {
          onParsed({
            memberCount: members.length,
            scale: scale ?? { factor: 1, unit: "mm" },
          });
        }
      } catch (err: unknown) {
        const msg = (err as { detail?: string }).detail ?? "Failed to save verification gate.";
        setVerificationStatus("error", msg);
      }
    };

    const handleResetGeometry = async () => {
      resetGeometry();
      await fetchExistingGeometry();
    };

    // ── Upload & Parsing Flow ────────────────────────────────────────────────

    const uploadAndParse = useCallback(
      async (file: File) => {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        if (!ACCEPTED_EXTS.includes(`.${ext}`)) {
          setUploadError("Unsupported file type. Please upload a .dxf or .pdf file.");
          setUploadState("error");
          return;
        }

        onUploadStart?.();
        setUploadState("uploading");
        setUploadError(null);

        try {
          const form = new FormData();
          form.append("file", file);

          const { data: job } = await apiClient.post<{ job_id: string }>(
            `/api/v1/files/upload/${projectId}`,
            form,
            { headers: { "Content-Type": "multipart/form-data" } }
          );

          setUploadState("parsing");

          const poll = async () => {
            try {
              const { data: status } = await apiClient.get<JobStatus>(
                `/api/v1/jobs/${job.job_id}`
              );

              if (status.status === "complete") {
                await fetchExistingGeometry();
              } else if (status.status === "failed") {
                setUploadError((status.errors ?? [])[0] ?? "Parsing failed.");
                setUploadState("error");
              } else {
                pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
              }
            } catch {
              setUploadError("Lost connection while checking parse status. Please retry.");
              setUploadState("error");
            }
          };

          await poll();
        } catch (err: unknown) {
          setUploadError((err as { detail?: string }).detail ?? "Upload failed.");
          setUploadState("error");
        }
      },
      [projectId, onUploadStart, fetchExistingGeometry]
    );

    const handleDragOver = useCallback((e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback(() => setIsDragOver(false), []);

    const handleDrop = useCallback(
      (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) uploadAndParse(file);
      },
      [uploadAndParse]
    );

    const handleFileInput = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) uploadAndParse(file);
      },
      [uploadAndParse]
    );

    const handleRetry = () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
      setUploadState("idle");
      setUploadError(null);
    };

    const hoveredMember = members.find((m) => m.member_id === hoveredMemberId);

    return (
      <div className="h-full flex flex-col relative" ref={containerRef}>
        {/* Toolbar (Only shown when drawing layout is loaded) */}
        {uploadState === "done" && (
          <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-1">
            <button
              onClick={() => setTool("select")}
              title="Select Tool"
              className={cn(
                "p-2 rounded-md transition-colors",
                activeTool === "select"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
            >
              <MousePointer className="h-4 w-4" />
            </button>
            <button
              onClick={() => setTool("pan")}
              title="Pan Tool"
              className={cn(
                "p-2 rounded-md transition-colors",
                activeTool === "pan"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
            >
              <Move className="h-4 w-4" />
            </button>
            <div className="h-px bg-border my-0.5" />
            <button
              onClick={() => setZoom(zoom * 1.2)}
              title="Zoom In"
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <ZoomIn className="h-4 w-4" />
            </button>
            <button
              onClick={() => setZoom(zoom / 1.2)}
              title="Zoom Out"
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <ZoomOut className="h-4 w-4" />
            </button>
            <button
              onClick={() =>
                fitToView(canvasRef.current?.width ?? 800, canvasRef.current?.height ?? 600)
              }
              title="Fit to View"
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Coordinate Readout */}
        {uploadState === "done" && (
          <div className="absolute bottom-3 left-3 z-10 flex items-center gap-3 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-1.5 shadow-sm">
            <span className="text-xs font-mono text-muted-foreground">
              X: <span className="text-foreground">{mouseWorldPos.x.toFixed(1)}</span>
            </span>
            <span className="text-xs font-mono text-muted-foreground">
              Y: <span className="text-foreground">{mouseWorldPos.y.toFixed(1)}</span>
            </span>
            <div className="w-px h-3 bg-border" />
            <span className="text-xs font-mono text-muted-foreground">
              Scale:{" "}
              <span className="text-foreground">
                {scale ? `1:${(1 / scale.factor).toFixed(0)} (${scale.unit})` : "—"}
              </span>
            </span>
          </div>
        )}

        {/* Hover Tooltip Overlay (Tactile feedback) */}
        {uploadState === "done" && hoveredMember && tooltipPos && (
          <div
            className="absolute z-30 pointer-events-none px-2.5 py-1.5 bg-card/95 border border-border text-foreground rounded shadow-lg text-xs font-mono flex flex-col gap-0.5 backdrop-blur-md"
            style={{ left: tooltipPos.x + 12, top: tooltipPos.y - 32 }}
          >
            <span className="font-semibold text-primary">{hoveredMember.member_id} ({hoveredMember.member_type})</span>
            {hoveredMember.meta.b_mm && hoveredMember.meta.h_mm && (
              <span className="text-muted-foreground">Section: {hoveredMember.meta.b_mm} × {hoveredMember.meta.h_mm} mm</span>
            )}
            {hoveredMember.meta.L_clear !== undefined && (
              <span className="text-muted-foreground">Span: {hoveredMember.meta.L_clear} m</span>
            )}
          </div>
        )}

        {/* Main Canvas Container */}
        <div
          className={cn(
            "flex-1 bg-[#0b0f19] relative overflow-hidden transition-colors select-none",
            isDragOver && "bg-primary/5"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".dxf,.pdf"
            className="hidden"
            onChange={handleFileInput}
          />

          {/* Idle upload zone */}
          {uploadState === "idle" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className={cn(
                  "flex flex-col items-center gap-4 p-10 rounded-xl border-2 border-dashed transition-all bg-card/40 backdrop-blur-sm shadow-md",
                  isDragOver
                    ? "border-primary bg-primary/5 scale-105"
                    : "border-border hover:border-muted-foreground"
                )}
              >
                <div
                  className={cn(
                    "h-16 w-16 rounded-xl flex items-center justify-center transition-colors",
                    isDragOver ? "bg-primary/15" : "bg-muted"
                  )}
                >
                  {isDragOver ? (
                    <FileUp className="h-8 w-8 text-primary animate-pulse" />
                  ) : (
                    <Upload className="h-8 w-8 text-muted-foreground" />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">
                    {isDragOver ? "Drop DXF or PDF here" : "Upload Architectural Design"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Supports geometry extraction + multimodal reference PDFs
                  </p>
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-all shadow-sm"
                >
                  Browse Files
                </button>
                <p className="text-xs text-muted-foreground font-mono">.dxf, .pdf supported</p>
              </div>
            </div>
          )}

          {/* Parse/Upload Spinner */}
          {(uploadState === "uploading" || uploadState === "parsing") && (
            <div className="absolute inset-0 flex items-center justify-center bg-card/25 backdrop-blur-xs">
              <div className="flex flex-col items-center gap-4">
                <Loader2 className="h-10 w-10 text-primary animate-spin" />
                <p className="text-sm font-medium">
                  {uploadState === "uploading" ? "Uploading file to pipeline…" : "Multimodal Vision Agent parsing drawing…"}
                </p>
                <p className="text-xs text-muted-foreground font-mono">
                  {uploadState === "parsing"
                    ? "Extracting geometric locations, beams, slabs & cross-sections"
                    : "Initializing drawing buffer"}
                </p>
              </div>
            </div>
          )}

          {/* Error Alert Display */}
          {uploadState === "error" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-4 max-w-sm text-center bg-card/60 p-6 rounded-xl border border-border backdrop-blur-sm">
                <AlertCircle className="h-10 w-10 text-destructive" />
                <p className="text-sm font-medium text-destructive">{uploadError}</p>
                <button
                  onClick={handleRetry}
                  className="px-4 py-2 bg-muted text-foreground text-sm rounded-lg hover:bg-muted/80 transition-colors"
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          {/* High Fidelity HTML5 Canvas Element */}
          {uploadState === "done" && (
            <canvas
              ref={canvasRef}
              className="absolute inset-0 block cursor-crosshair"
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onWheel={handleWheel}
            />
          )}

          {/* Property Inspector bottom panel overlay */}
          {uploadState === "done" && selectedMember && (
            <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[90%] max-w-2xl bg-card/95 border border-border shadow-xl rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md animate-fade-in-up">
              <div className="flex items-center justify-between border-b border-border pb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-primary">{selectedMember.member_id}</span>
                  <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground uppercase font-mono">
                    {selectedMember.member_type}
                  </span>
                </div>
                <button
                  onClick={() => selectMember(null)}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  Deselect
                </button>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-muted-foreground font-mono">Width b (mm)</label>
                  <input
                    type="number"
                    value={editWidth}
                    onChange={(e) => setEditWidth(e.target.value)}
                    className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-muted-foreground font-mono">Depth/Thickness h (mm)</label>
                  <input
                    type="number"
                    value={editDepth}
                    onChange={(e) => setEditDepth(e.target.value)}
                    className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-muted-foreground font-mono">Clear Span L (m)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editSpan}
                    onChange={(e) => setEditSpan(e.target.value)}
                    disabled={selectedMember.member_type === "column" || selectedMember.member_type === "footing"}
                    className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 disabled:opacity-50 focus:outline-hidden focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border mt-1">
                <button
                  onClick={handleDeleteMember}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-destructive border border-destructive/20 rounded hover:bg-destructive/10 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete Member
                </button>
                <button
                  onClick={handleSaveProperties}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/95 transition-colors font-medium shadow-xs"
                >
                  <Save className="h-3.5 w-3.5" />
                  Apply & Save Property
                </button>
              </div>
            </div>
          )}

          {/* Sticky HITL Geometry Verification Bar (Safety Gate 1) */}
          {uploadState === "done" && (
            <div
              className={cn(
                "absolute bottom-0 inset-x-0 z-10 border-t flex flex-col md:flex-row items-stretch md:items-center justify-between p-3.5 gap-3 backdrop-blur-md transition-all shadow-lg",
                verificationStatus === "verified"
                  ? "bg-green-500/10 border-green-500/20"
                  : "bg-amber-500/10 border-amber-500/20"
              )}
            >
              <div className="flex items-start gap-3">
                {verificationStatus === "verified" ? (
                  <CheckCircle2 className="h-5 w-5 text-green-400 mt-0.5 shrink-0" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
                )}
                <div className="flex flex-col">
                  <p className="text-xs font-semibold">
                    {verificationStatus === "verified"
                      ? "Geometry Verified & Safety Gate Approved"
                      : "Geometry Verification Required (Safety Gate 1)"}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {verificationStatus === "verified"
                      ? "Design parameters locked in. Let the Assistant engineer know in the conversation sidebar to analyze."
                      : `Verify detected ${members.length} member locations. Select any beam/column to customize cross-sections.`}
                  </p>
                </div>
              </div>

              {verificationStatus !== "verified" && (
                <div className="flex items-center gap-2 max-w-md w-full md:w-auto">
                  <input
                    type="text"
                    placeholder="Enter review notes (optional)..."
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="flex-1 bg-muted/60 text-xs rounded border border-border px-2.5 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary w-48 font-mono"
                  />
                  <button
                    onClick={handleResetGeometry}
                    title="Reset geometry to original AI parsed state"
                    className="p-1.5 text-muted-foreground hover:text-foreground border border-border rounded hover:bg-muted transition-all"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </button>
                  <button
                    onClick={handleConfirmGeometry}
                    disabled={verificationStatus === "submitting"}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded hover:bg-primary/95 transition-all shadow-xs disabled:opacity-50 shrink-0"
                  >
                    {verificationStatus === "submitting" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5" />
                    )}
                    Confirm Layout
                  </button>
                </div>
              )}

              {verificationStatus === "verified" && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-green-400 font-medium">Ready for Downstream Analysis</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
);

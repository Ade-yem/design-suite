import * as React from "react";
import { useState, useEffect, useRef, useCallback } from "react";
import type { Point, GeometricMember } from "../lib/canvas-drawing";
import {
  computeBounds,
  computeFitTransform,
  screenToWorld,
  zoomTowardPoint,
  drawDotGrid,
  drawMember,
  drawAllLabels,
  hitTestMembers,
} from "../lib/canvas-drawing";
import { Maximize2, Move, MousePointerClick, SlidersHorizontal, Layers } from "lucide-react";

interface CanvasViewportProps {
  members: GeometricMember[];
  selectedMemberId: string | null;
  onSelectMember: (id: string | null) => void;
}

/**
 * Configuration schema for the visibility states of different structural member labels.
 */
export interface LabelVisibilityConfig {
  /** Whether column labels are currently visible */
  columns: boolean;
  /** Whether beam labels are currently visible */
  beams: boolean;
  /** Whether slab and void labels are currently visible */
  slabs: boolean;
  /** Whether labels for other components (e.g. walls, staircases) are visible */
  others: boolean;
}

export function CanvasViewport({
  members,
  selectedMemberId,
  onSelectMember,
}: CanvasViewportProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Viewport transforms
  const [zoom, setZoom] = useState<number>(0.05);
  const [pan, setPan] = useState<Point>({ x: 100, y: 300 });

  // Interaction modes
  const [activeTool, setActiveTool] = useState<"select" | "pan">("select");
  const [hoveredMemberId, setHoveredMemberId] = useState<string | null>(null);
  const [cursorCoords, setCursorCoords] = useState<Point>({ x: 0, y: 0 });

  // Dragging states
  const isPanningRef = useRef<boolean>(false);
  const startPanRef = useRef<Point>({ x: 0, y: 0 });
  const startMouseRef = useRef<Point>({ x: 0, y: 0 });

  // Label visibility menu states
  const [isLabelMenuOpen, setIsLabelMenuOpen] = useState<boolean>(false);
  const [labelVisibility, setLabelVisibility] = useState<LabelVisibilityConfig>({
    columns: true,
    beams: true,
    slabs: true,
    others: true,
  });

  /**
   * Toggles the visibility of a specific category of labels.
   * @param category The label category key to toggle (columns, beams, slabs, or others).
   */
  const handleToggleLabel = useCallback((category: keyof LabelVisibilityConfig): void => {
    setLabelVisibility((prev) => {
      const nextVal = !prev[category];
      console.log(`[CanvasViewport] Toggled label visibility for ${category}: ${nextVal}`);
      return {
        ...prev,
        [category]: nextVal,
      };
    });
  }, []);

  /**
   * Helper variable indicating if all label types are currently visible.
   */
  const allLabelsVisible =
    labelVisibility.columns &&
    labelVisibility.beams &&
    labelVisibility.slabs &&
    labelVisibility.others;

  /**
   * Toggles visibility for all label categories simultaneously.
   */
  const toggleAllLabels = useCallback((): void => {
    setLabelVisibility((prev) => {
      const nextState = !allLabelsVisible;
      console.log(`[CanvasViewport] Setting all label visibilities to: ${nextState}`);
      return {
        columns: nextState,
        beams: nextState,
        slabs: nextState,
        others: nextState,
      };
    });
  }, [allLabelsVisible]);

  // ── Transform Fit View ───────────────────────────────────────────────────

  const fitToView = useCallback(
    (w: number, h: number) => {
      const bounds = computeBounds(members);
      if (!bounds) return;

      const { zoom: newZoom, pan: newPan } = computeFitTransform(bounds, w, h, 0.15);
      setZoom(newZoom);
      setPan(newPan);
    },
    [members]
  );

  const handleFitView = () => {
    const canvas = canvasRef.current;
    if (canvas) {
      fitToView(canvas.width, canvas.height);
    }
  };

  // ── Render loop ──────────────────────────────────────────────────────────

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Grid
    drawDotGrid(ctx, canvas.width, canvas.height, zoom, pan);

    // 2. Members
    for (const member of members) {
      const isSelected = member.member_id === selectedMemberId;
      const isHovered = member.member_id === hoveredMemberId;
      drawMember(ctx, member, zoom, pan, canvas.height, isSelected, isHovered);
    }

    // Filter members to only include those whose labels are set to visible
    const membersWithVisibleLabels = members.filter((member) => {
      const type = member.member_type;
      if (type === "column") {
        return labelVisibility.columns;
      }
      if (type === "beam") {
        return labelVisibility.beams;
      }
      if (type === "slab" || type === "void") {
        return labelVisibility.slabs;
      }
      return labelVisibility.others;
    });

    // 3. Labels
    drawAllLabels(ctx, membersWithVisibleLabels, zoom, pan, canvas.width, canvas.height);
  }, [members, zoom, pan, selectedMemberId, hoveredMemberId, labelVisibility]);

  useEffect(() => {
    let animFrameId: number;
    const render = () => {
      draw();
      animFrameId = requestAnimationFrame(render);
    };
    animFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animFrameId);
  }, [draw]);

  // ── Resize handler ───────────────────────────────────────────────────────

  const handleResize = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
  }, []);

  useEffect(() => {
    handleResize();
    const resizeObserver = new ResizeObserver(() => handleResize());
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }
    return () => resizeObserver.disconnect();
  }, [handleResize]);

  // Run fit-to-view when members load — delay slightly so the canvas has been
  // sized by the ResizeObserver before we compute zoom/pan.
  useEffect(() => {
    if (members.length === 0) return;
    const timer = setTimeout(() => {
      const canvas = canvasRef.current;
      if (canvas) fitToView(canvas.width, canvas.height);
    }, 100);
    return () => clearTimeout(timer);
  }, [members, fitToView]);

  // ── Mouse Event Handlers ─────────────────────────────────────────────────

  const handleMouseDown = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (activeTool === "pan" || e.button === 1 || e.shiftKey) {
      isPanningRef.current = true;
      startPanRef.current = { ...pan };
      startMouseRef.current = { x: sx, y: sy };
      canvas.style.cursor = "grabbing";
    } else {
      // Selection click
      const mouseScreen = { x: sx, y: sy };
      const hitId = hitTestMembers(mouseScreen, members, zoom, pan, canvas.height);
      onSelectMember(hitId);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    // Track cursor coordinates in DXF world-space
    const worldCoords = screenToWorld({ x: sx, y: sy }, zoom, pan, canvas.height);
    setCursorCoords(worldCoords);

    if (isPanningRef.current) {
      const dx = sx - startMouseRef.current.x;
      const dy = sy - startMouseRef.current.y;
      setPan({
        x: startPanRef.current.x + dx,
        y: startPanRef.current.y - dy, // inversion adjust
      });
    } else {
      // Hover hit testing
      const mouseScreen = { x: sx, y: sy };
      const hitId = hitTestMembers(mouseScreen, members, zoom, pan, canvas.height);
      setHoveredMemberId(hitId);
    }
  };

  const handleMouseUp = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    isPanningRef.current = false;
    canvas.style.cursor = activeTool === "pan" ? "move" : "default";
  };

  const handleWheel = (e: React.WheelEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const zoomIntensity = 0.12;
    const wheelDelta = -e.deltaY;
    const zoomFactor = wheelDelta > 0 ? 1 + zoomIntensity : 1 - zoomIntensity;

    const newZoom = Math.min(Math.max(zoom * zoomFactor, 0.001), 2.0);

    const mouseScreen = { x: sx, y: sy };
    const newPan = zoomTowardPoint(mouseScreen, zoom, newZoom, pan);

    setZoom(newZoom);
    setPan(newPan);
  };

  return (
    <div ref={containerRef} className="relative w-full h-full bg-[#0b0f19] select-none border border-slate-800 rounded-lg overflow-hidden">
      {/* Floating Control: Label Visibility Menu */}
      <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2">
        <div className="relative">
          <button
            onClick={() => setIsLabelMenuOpen((prev) => !prev)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border transition-all duration-200 shadow-lg cursor-pointer ${
              isLabelMenuOpen
                ? "bg-[#6366f1] border-[#6366f1] text-white"
                : "bg-[#141b2b]/95 border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 backdrop-blur"
            }`}
            title="Toggle Label Visibility Menu"
          >
            <SlidersHorizontal size={14} />
            <span>Label Visibility</span>
          </button>

          {isLabelMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 bg-[#141b2b]/98 backdrop-blur-md border border-slate-800/90 p-3.5 rounded-lg shadow-2xl flex flex-col gap-3 transition-all duration-200 animate-in fade-in slide-in-from-top-1">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 select-none">
                  <Layers size={11} className="text-[#6366f1]" />
                  Active Labels
                </span>
                <button
                  onClick={toggleAllLabels}
                  className="text-[10px] text-[#818cf8] hover:text-[#a5b4fc] transition-colors font-medium cursor-pointer"
                >
                  {allLabelsVisible ? "Hide All" : "Show All"}
                </button>
              </div>

              <div className="flex flex-col gap-2.5">
                {/* Columns Toggle */}
                <label className="flex items-center justify-between group cursor-pointer">
                  <div className="flex items-center gap-2 select-none">
                    <div className="w-2 h-2 rounded-full bg-[#3b82f6]" />
                    <span className="text-xs text-slate-300 group-hover:text-white transition-colors">Columns</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={labelVisibility.columns}
                    onChange={() => handleToggleLabel("columns")}
                    className="sr-only peer"
                  />
                  <div className="relative w-7 h-4 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-[#6366f1] peer-checked:after:bg-white peer-checked:after:border-transparent" />
                </label>

                {/* Beams Toggle */}
                <label className="flex items-center justify-between group cursor-pointer">
                  <div className="flex items-center gap-2 select-none">
                    <div className="w-2 h-2 rounded-full bg-[#10b981]" />
                    <span className="text-xs text-slate-300 group-hover:text-white transition-colors">Beams</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={labelVisibility.beams}
                    onChange={() => handleToggleLabel("beams")}
                    className="sr-only peer"
                  />
                  <div className="relative w-7 h-4 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-[#6366f1] peer-checked:after:bg-white peer-checked:after:border-transparent" />
                </label>

                {/* Slabs Toggle */}
                <label className="flex items-center justify-between group cursor-pointer">
                  <div className="flex items-center gap-2 select-none">
                    <div className="w-2 h-2 rounded-full bg-[#f59e0b]" />
                    <span className="text-xs text-slate-300 group-hover:text-white transition-colors">Slabs & Voids</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={labelVisibility.slabs}
                    onChange={() => handleToggleLabel("slabs")}
                    className="sr-only peer"
                  />
                  <div className="relative w-7 h-4 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-[#6366f1] peer-checked:after:bg-white peer-checked:after:border-transparent" />
                </label>

                {/* Others Toggle */}
                <label className="flex items-center justify-between group cursor-pointer">
                  <div className="flex items-center gap-2 select-none">
                    <div className="w-2 h-2 rounded-full bg-[#ec4899]" />
                    <span className="text-xs text-slate-300 group-hover:text-white transition-colors">Others</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={labelVisibility.others}
                    onChange={() => handleToggleLabel("others")}
                    className="sr-only peer"
                  />
                  <div className="relative w-7 h-4 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-[#6366f1] peer-checked:after:bg-white peer-checked:after:border-transparent" />
                </label>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Canvas Viewport */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className="w-full h-full block"
        style={{ cursor: activeTool === "pan" ? "move" : "default" }}
      />

      {/* Toolbar */}
      <div className="absolute bottom-4 left-4 flex items-center gap-2 bg-[#141b2b]/95 backdrop-blur border border-slate-800 p-1.5 rounded-lg shadow-lg">
        <button
          onClick={() => setActiveTool("select")}
          className={`p-2 rounded transition-colors ${
            activeTool === "select"
              ? "bg-[#6366f1] text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-800"
          }`}
          title="Select Member"
        >
          <MousePointerClick size={16} />
        </button>
        <button
          onClick={() => setActiveTool("pan")}
          className={`p-2 rounded transition-colors ${
            activeTool === "pan"
              ? "bg-[#6366f1] text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-800"
          }`}
          title="Pan Tool"
        >
          <Move size={16} />
        </button>
        <div className="w-px h-6 bg-slate-800" />
        <button
          onClick={handleFitView}
          className="p-2 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          title="Fit to Viewport"
        >
          <Maximize2 size={16} />
        </button>
      </div>

      {/* Coordinate Display */}
      <div className="absolute bottom-4 right-4 bg-[#141b2b]/95 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-slate-400 shadow-lg flex items-center gap-4">
        <div>
          X: <span className="text-white">{(cursorCoords.x / 1000).toFixed(3)}m</span>
        </div>
        <div>
          Y: <span className="text-white">{(cursorCoords.y / 1000).toFixed(3)}m</span>
        </div>
        <div>
          Zoom: <span className="text-white">{(zoom * 100).toFixed(1)}%</span>
        </div>
      </div>
    </div>
  );
}

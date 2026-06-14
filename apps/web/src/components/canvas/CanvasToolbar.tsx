"use client";

import * as React from "react";
import { MousePointer, Move, ZoomIn, ZoomOut, Maximize2, Tag, BarChart2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Props for the CanvasToolbar component.
 */
interface CanvasToolbarProps {
  /** The current active tool mode: 'select' | 'pan' */
  activeTool: "select" | "pan";
  /** Callback to change the active tool mode */
  setTool: (tool: "select" | "pan") => void;
  /** Callback to zoom in (increases zoom factor) */
  onZoomIn: () => void;
  /** Callback to zoom out (decreases zoom factor) */
  onZoomOut: () => void;
  /** Callback to center and scale drawing coordinates to fit container bounds */
  onFitToView: () => void;
  /** Whether the analysis colour-coding overlay is currently active */
  analysisOverlay: boolean;
  /** True when analysis results are available to display (enables toggle) */
  hasAnalysisResults: boolean;
  /** Callback to toggle analysis pass/fail colour-coding on/off */
  onToggleAnalysisOverlay: () => void;
  /** Callback to open/close the label visibility modal */
  onOpenLabelModal: () => void;
  /** Whether the label visibility modal is currently open */
  isLabelModalOpen: boolean;
}

/**
 * CanvasToolbar component.
 * Renders absolute floating tool actions over the structural canvas workspace.
 *
 * Tools:
 * - Select / Pan / Zoom In / Zoom Out / Fit to View (always visible when geometry is loaded)
 * - Tag: Opens the member label visibility modal (always visible when geometry is loaded)
 * - BarChart2: Toggles the analysis pass/fail colour-coding overlay (visible only when
 *              analysis results are available)
 *
 * @param {CanvasToolbarProps} props - Component properties.
 * @returns {React.ReactElement} The rendered absolute coordinate toolbar.
 */
export function CanvasToolbar({
  activeTool,
  setTool,
  onZoomIn,
  onZoomOut,
  onFitToView,
  analysisOverlay,
  hasAnalysisResults,
  onToggleAnalysisOverlay,
  onOpenLabelModal,
  isLabelModalOpen,
}: CanvasToolbarProps): React.ReactElement {
  return (
    <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-1">
      {/* Interaction tools */}
      <button
        id="canvas-tool-select"
        onClick={() => setTool("select")}
        title="Select Tool"
        className={cn(
          "p-2 rounded-md transition-colors",
          activeTool === "select"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
      >
        <MousePointer className="h-4 w-4" />
      </button>
      <button
        id="canvas-tool-pan"
        onClick={() => setTool("pan")}
        title="Pan Tool"
        className={cn(
          "p-2 rounded-md transition-colors",
          activeTool === "pan"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
      >
        <Move className="h-4 w-4" />
      </button>

      <div className="h-px bg-border my-0.5" />

      {/* Zoom tools */}
      <button
        id="canvas-tool-zoom-in"
        onClick={onZoomIn}
        title="Zoom In"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        id="canvas-tool-zoom-out"
        onClick={onZoomOut}
        title="Zoom Out"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        id="canvas-tool-fit-view"
        onClick={onFitToView}
        title="Fit to View"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <Maximize2 className="h-4 w-4" />
      </button>

      <div className="h-px bg-border my-0.5" />

      {/* Label visibility toggle */}
      <button
        id="canvas-tool-labels"
        onClick={onOpenLabelModal}
        title="Member Labels"
        className={cn(
          "p-2 rounded-md transition-colors",
          isLabelModalOpen
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
      >
        <Tag className="h-4 w-4" />
      </button>

      {/* Analysis colour-coding toggle — only shown when results exist */}
      {hasAnalysisResults && (
        <button
          id="canvas-tool-analysis-overlay"
          onClick={onToggleAnalysisOverlay}
          title={analysisOverlay ? "Hide Analysis Colours" : "Show Analysis Colours"}
          className={cn(
            "p-2 rounded-md transition-colors",
            analysisOverlay
              ? "bg-emerald-600/80 text-white"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          <BarChart2 className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

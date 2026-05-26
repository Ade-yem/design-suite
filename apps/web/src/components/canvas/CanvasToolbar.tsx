"use client";

import * as React from "react";
import { MousePointer, Move, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
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
}

/**
 * CanvasToolbar component.
 * Renders absolute floating tool actions (Select, Pan, Zoom, and Fit to View)
 * over the high-fidelity structural canvas workspace.
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
}: CanvasToolbarProps): React.ReactElement {
  return (
    <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-1">
      <button
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
      <button
        onClick={onZoomIn}
        title="Zoom In"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        onClick={onZoomOut}
        title="Zoom Out"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        onClick={onFitToView}
        title="Fit to View"
        className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  );
}

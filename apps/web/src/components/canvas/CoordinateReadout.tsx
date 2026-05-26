"use client";

import * as React from "react";
import type { Point } from "@/types/canvas";

/**
 * Props for the CoordinateReadout component.
 */
interface CoordinateReadoutProps {
  /** The current calculated vector coordinates of the mouse cursor */
  mouseWorldPos: Point;
  /** Scale and units information detected for the drawing */
  scale: { factor: number; unit: string } | null;
}

/**
 * CoordinateReadout component.
 * Displays real-time cursor tracking coordinate readouts (X, Y) and
 * structural blueprint grid scaling factor at the bottom-left corner of the viewport.
 *
 * @param {CoordinateReadoutProps} props - Component properties.
 * @returns {React.ReactElement} The rendered CoordinateReadout element.
 */
export function CoordinateReadout({
  mouseWorldPos,
  scale,
}: CoordinateReadoutProps): React.ReactElement {
  return (
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
  );
}

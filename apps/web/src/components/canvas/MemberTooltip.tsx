"use client";

import * as React from "react";
import type { GeometricMember, Point } from "@/types/canvas";

/**
 * Props for the MemberTooltip component.
 */
interface MemberTooltipProps {
  /** The structural member currently being hovered */
  hoveredMember: GeometricMember;
  /** The current absolute screen position where the tooltip should render */
  tooltipPos: Point;
}

/**
 * MemberTooltip component.
 * Renders a lightweight, high-performance floating tooltip overlay immediately
 * adjacent to the active hovered structural drawing member (e.g. beam dimensions, span, ID).
 *
 * @param {MemberTooltipProps} props - Component properties.
 * @returns {React.ReactElement} The rendered MemberTooltip element.
 */
export function MemberTooltip({
  hoveredMember,
  tooltipPos,
}: MemberTooltipProps): React.ReactElement {
  return (
    <div
      className="absolute z-30 pointer-events-none px-2.5 py-1.5 bg-card/95 border border-border text-foreground rounded shadow-lg text-xs font-mono flex flex-col gap-0.5 backdrop-blur-md"
      style={{ left: tooltipPos.x + 12, top: tooltipPos.y - 32 }}
    >
      <span className="font-semibold text-primary">
        {hoveredMember.member_id} ({hoveredMember.member_type})
      </span>
      {hoveredMember.meta.b_mm && hoveredMember.meta.h_mm && (
        <span className="text-muted-foreground">
          Section: {hoveredMember.meta.b_mm} × {hoveredMember.meta.h_mm} mm
        </span>
      )}
      {hoveredMember.meta.L_clear !== undefined && (
        <span className="text-muted-foreground">
          Span: {hoveredMember.meta.L_clear} m
        </span>
      )}
    </div>
  );
}

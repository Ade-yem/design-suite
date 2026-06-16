"use client";

import * as React from "react";

/**
 * A single primitive emitted by the backend drawing generators
 * (`core/drawing/*`). Geometry is in millimetres, y grows downward — the same
 * convention SVG uses, so commands map directly into a `viewBox`.
 */
export type DrawCommand =
  | { type: "rect"; x: number; y: number; width: number; height: number; style?: string; label?: string | null; mark?: string | null }
  | { type: "circle"; cx: number; cy: number; r: number; style?: string; label?: string | null; mark?: string | null }
  | { type: "line"; x1: number; y1: number; x2: number; y2: number; style?: string; diameter?: number | null; label?: string | null; mark?: string | null }
  | { type: "dimension"; axis: "horizontal" | "vertical"; value: number; label: string; x?: number; y?: number }
  | { type: "text"; text: string; x: number; y: number; style?: string };

/** A full member drawing as returned by GET /api/v1/drawings/{id}/member/{id}. */
export interface MemberDrawing {
  section?: DrawCommand[];
  elevation?: DrawCommand[];
  dimensions?: DrawCommand[];
  bar_marks?: DrawCommand[];
  annotations?: DrawCommand[];
  canvas_bounds?: { width: number; height: number };
  scale?: number;
}

interface DrawingCanvasProps {
  drawing: MemberDrawing;
  /** Which primary view to render. Dimensions + bar marks + annotations overlay it. */
  view?: "section" | "elevation";
  className?: string;
}

// Style → stroke/fill mapping for the renderer.
const STROKE: Record<string, string> = {
  structural_outline: "var(--color-foreground, #e5e7eb)",
  cover_line: "#9ca3af",
  rebar: "#ef4444",
  link: "#f59e0b",
  dimension_line: "#60a5fa",
};
const TEXT_FILL: Record<string, string> = {
  title: "var(--color-foreground, #e5e7eb)",
  subtitle: "#9ca3af",
  annotation: "#9ca3af",
  bar_mark: "#ef4444",
};

function strokeFor(style?: string): string {
  return (style && STROKE[style]) || "var(--color-foreground, #e5e7eb)";
}

/**
 * Renders backend draw-commands as an SVG. No drawing-specific logic lives here —
 * it is a thin, reusable consumer of the `{type: rect|circle|line|text|dimension}`
 * primitives, used by the staircase panel and any future member drawing view.
 */
export function DrawingCanvas({
  drawing,
  view = "elevation",
  className,
}: DrawingCanvasProps): React.ReactElement {
  const bounds = drawing.canvas_bounds ?? { width: 500, height: 500 };
  const primary = (view === "section" ? drawing.section : drawing.elevation) ?? [];
  const commands: DrawCommand[] = [
    ...primary,
    ...(drawing.dimensions ?? []),
    ...(drawing.bar_marks ?? []),
    ...(drawing.annotations ?? []),
  ];

  return (
    <svg
      className={className}
      viewBox={`0 0 ${bounds.width} ${bounds.height}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`${view} drawing`}
    >
      {commands.map((c, i) => {
        switch (c.type) {
          case "rect":
            return (
              <rect
                key={i}
                x={c.x}
                y={c.y}
                width={c.width}
                height={c.height}
                fill="none"
                stroke={strokeFor(c.style)}
                strokeWidth={c.style === "cover_line" ? 1 : 2}
              />
            );
          case "circle":
            return (
              <circle
                key={i}
                cx={c.cx}
                cy={c.cy}
                r={Math.max(c.r, 4)}
                fill={c.style === "rebar" ? "#ef4444" : "none"}
                stroke={strokeFor(c.style)}
                strokeWidth={1}
              />
            );
          case "line":
            return (
              <line
                key={i}
                x1={c.x1}
                y1={c.y1}
                x2={c.x2}
                y2={c.y2}
                stroke={strokeFor(c.style)}
                strokeWidth={c.style === "rebar" ? Math.max(c.diameter ?? 3, 3) : 2}
              />
            );
          case "dimension": {
            const x = c.x ?? 0;
            const y = c.y ?? 0;
            return (
              <text key={i} x={x} y={y} fontSize={26} fill={STROKE.dimension_line}>
                {c.label}
              </text>
            );
          }
          case "text":
            return (
              <text
                key={i}
                x={c.x}
                y={c.y}
                fontSize={c.style === "title" ? 30 : 24}
                fontWeight={c.style === "title" ? 700 : 400}
                fill={(c.style && TEXT_FILL[c.style]) || "#9ca3af"}
              >
                {c.text}
              </text>
            );
          default:
            return null;
        }
      })}
    </svg>
  );
}

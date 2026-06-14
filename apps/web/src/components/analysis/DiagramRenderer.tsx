"use client";

/**
 * @file DiagramRenderer.tsx
 * @description SVG-based structural diagram renderer.
 *
 * Renders engineering-quality Bending Moment Diagrams (BMD), Shear Force
 * Diagrams (SFD), and Deflection curves from analysis result data.
 *
 * All curves are generated analytically from peak values + standard beam
 * theory shapes (UDL assumption for continuous beams, point load for columns).
 */

import React, { useRef, useCallback } from "react";
import { Download } from "lucide-react";
import type { StressResultants, SLSChecks } from "@/types/analysis";

// ── Helpers ──────────────────────────────────────────────────────────────────

const W = 600;
const H = 200;
const MARGIN = { top: 24, right: 24, bottom: 40, left: 60 };
const PLOT_W = W - MARGIN.left - MARGIN.right;
const PLOT_H = H - MARGIN.top - MARGIN.bottom;
const N_PTS = 80;

function linspace(a: number, b: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => a + (i / (n - 1)) * (b - a));
}

function mapX(t: number): number {
  return MARGIN.left + t * PLOT_W;
}

function mapY(v: number, vMin: number, vMax: number): number {
  const range = vMax - vMin || 1;
  return MARGIN.top + PLOT_H - ((v - vMin) / range) * PLOT_H;
}

function polyline(xs: number[], ys: number[], vMin: number, vMax: number): string {
  return xs
    .map((x, i) => `${mapX(x).toFixed(1)},${mapY(ys[i], vMin, vMax).toFixed(1)}`)
    .join(" ");
}

/** Build SVG fill-path: line + close to the zero axis. */
function buildFillPath(
  xs: number[],
  ys: number[],
  vMin: number,
  vMax: number,
  zeroY: number
): string {
  if (xs.length === 0) return "";
  const pts = xs.map(
    (x, i) => `${mapX(x).toFixed(1)},${mapY(ys[i], vMin, vMax).toFixed(1)}`
  );
  const lastX = mapX(xs[xs.length - 1]).toFixed(1);
  const firstX = mapX(xs[0]).toFixed(1);
  return `M${pts.join("L")}L${lastX},${zeroY.toFixed(1)}L${firstX},${zeroY.toFixed(1)}Z`;
}

function downloadSvg(svgEl: SVGSVGElement | null, filename: string) {
  if (!svgEl) return;
  const xml = new XMLSerializer().serializeToString(svgEl);
  const blob = new Blob([xml], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Axis & grid helpers ───────────────────────────────────────────────────────

function AxisLabels({
  vMin,
  vMax,
  unit,
}: {
  vMin: number;
  vMax: number;
  unit: string;
}) {
  const ticks = [vMin, 0, vMax].filter(
    (v, i, arr) => Math.abs(v) > 0.01 || i === 1
  );
  return (
    <>
      {ticks.map((v, i) => (
        <text
          key={i}
          x={MARGIN.left - 6}
          y={mapY(v, vMin, vMax) + 4}
          textAnchor="end"
          fontSize="9"
          fill="#94a3b8"
          fontFamily="JetBrains Mono, monospace"
        >
          {Math.abs(v) < 0.5 ? "0" : v.toFixed(1)}
        </text>
      ))}
      <text
        x={8}
        y={MARGIN.top + PLOT_H / 2}
        fontSize="9"
        fill="#64748b"
        fontFamily="JetBrains Mono, monospace"
        transform={`rotate(-90, 8, ${MARGIN.top + PLOT_H / 2})`}
        textAnchor="middle"
      >
        {unit}
      </text>
    </>
  );
}

function SpanAxis({ spanM }: { spanM: number }) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <>
      {ticks.map((t) => (
        <text
          key={t}
          x={mapX(t)}
          y={H - 6}
          textAnchor="middle"
          fontSize="9"
          fill="#94a3b8"
          fontFamily="JetBrains Mono, monospace"
        >
          {(t * spanM).toFixed(1)}m
        </text>
      ))}
    </>
  );
}

// ── BMD ──────────────────────────────────────────────────────────────────────

export function BMDRenderer({
  resultants,
  spanM = 6,
  memberId,
}: {
  resultants: StressResultants;
  spanM?: number;
  memberId: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  const xs = linspace(0, 1, N_PTS);
  const mSag = resultants.M_max_sagging_kNm;
  const mHog = -Math.abs(resultants.M_max_hogging_kNm);

  // Approximate: parabolic sagging + hogging at supports
  const ys = xs.map((t) => {
    const sagging = mSag * 4 * t * (1 - t);
    const hogging = mHog * (1 - Math.pow(2 * t - 1, 2)); // hogging peak at supports
    return sagging + hogging;
  });

  const vMax = Math.max(...ys, 0.1);
  const vMin = Math.min(...ys, -0.1);
  const zeroY = mapY(0, vMin, vMax);

  const handleDownload = useCallback(
    () => downloadSvg(svgRef.current, `${memberId}_BMD.svg`),
    [memberId]
  );

  return (
    <div className="relative">
      <button
        onClick={handleDownload}
        className="absolute top-0 right-0 p-1.5 text-muted-foreground hover:text-foreground transition-colors"
        title="Download BMD"
      >
        <Download className="w-3.5 h-3.5" />
      </button>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: 200 }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Background */}
        <rect width={W} height={H} fill="#0f172a" />

        {/* Grid */}
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={mapX(t)}
            y1={MARGIN.top}
            x2={mapX(t)}
            y2={MARGIN.top + PLOT_H}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}
        <line
          x1={MARGIN.left}
          y1={zeroY}
          x2={MARGIN.left + PLOT_W}
          y2={zeroY}
          stroke="#334155"
          strokeWidth="1"
          strokeDasharray="4,3"
        />

        {/* Fill: positive (sagging) */}
        <path
          d={buildFillPath(xs, ys, vMin, vMax, zeroY)}
          fill="rgba(99,102,241,0.15)"
        />

        {/* Curve */}
        <polyline
          points={polyline(xs, ys, vMin, vMax)}
          fill="none"
          stroke="#818cf8"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Max sagging marker */}
        {mSag > 0 && (
          <>
            <circle cx={mapX(0.5)} cy={mapY(mSag * 0.98, vMin, vMax)} r="3" fill="#818cf8" />
            <text
              x={mapX(0.5) + 6}
              y={mapY(mSag * 0.98, vMin, vMax) + 4}
              fontSize="9"
              fill="#818cf8"
              fontFamily="JetBrains Mono, monospace"
            >
              {mSag.toFixed(1)} kNm
            </text>
          </>
        )}

        {/* Axes */}
        <line
          x1={MARGIN.left}
          y1={MARGIN.top}
          x2={MARGIN.left}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />
        <line
          x1={MARGIN.left}
          y1={MARGIN.top + PLOT_H}
          x2={MARGIN.left + PLOT_W}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />

        <AxisLabels vMin={vMin} vMax={vMax} unit="kNm" />
        <SpanAxis spanM={spanM} />

        {/* Label */}
        <text
          x={MARGIN.left + 4}
          y={MARGIN.top + 12}
          fontSize="9"
          fill="#64748b"
          fontFamily="JetBrains Mono, monospace"
        >
          BENDING MOMENT DIAGRAM
        </text>
      </svg>
    </div>
  );
}

// ── SFD ──────────────────────────────────────────────────────────────────────

export function SFDRenderer({
  resultants,
  reactions,
  spanM = 6,
  memberId,
}: {
  resultants: StressResultants;
  reactions: number[];
  spanM?: number;
  memberId: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  const xs = linspace(0, 1, N_PTS);
  const vMax = resultants.V_max_kN;
  const RA = reactions[0] ?? vMax;
  const RB = reactions[1] ?? -vMax;

  // Linear variation for UDL: V(x) = RA - (RA - RB) * x
  const ys = xs.map((t) => RA - (RA - RB) * t);

  const yMax = Math.max(...ys, 0.1);
  const yMin = Math.min(...ys, -0.1);
  const zeroY = mapY(0, yMin, yMax);

  const handleDownload = useCallback(
    () => downloadSvg(svgRef.current, `${memberId}_SFD.svg`),
    [memberId]
  );

  return (
    <div className="relative">
      <button
        onClick={handleDownload}
        className="absolute top-0 right-0 p-1.5 text-muted-foreground hover:text-foreground transition-colors"
        title="Download SFD"
      >
        <Download className="w-3.5 h-3.5" />
      </button>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: 200 }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect width={W} height={H} fill="#0f172a" />

        {/* Grid */}
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={mapX(t)}
            y1={MARGIN.top}
            x2={mapX(t)}
            y2={MARGIN.top + PLOT_H}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}
        <line
          x1={MARGIN.left}
          y1={zeroY}
          x2={MARGIN.left + PLOT_W}
          y2={zeroY}
          stroke="#334155"
          strokeWidth="1"
          strokeDasharray="4,3"
        />

        {/* Positive fill */}
        <path
          d={buildFillPath(
            xs.filter((_, i) => ys[i] >= 0),
            ys.filter((v) => v >= 0),
            yMin,
            yMax,
            zeroY
          )}
          fill="rgba(34,197,94,0.12)"
        />

        {/* Negative fill */}
        <path
          d={buildFillPath(
            xs.filter((_, i) => ys[i] <= 0),
            ys.filter((v) => v <= 0),
            yMin,
            yMax,
            zeroY
          )}
          fill="rgba(239,68,68,0.12)"
        />

        {/* Curve */}
        <polyline
          points={polyline(xs, ys, yMin, yMax)}
          fill="none"
          stroke="#22c55e"
          strokeWidth="2"
        />

        {/* Peak markers */}
        <circle cx={mapX(0.01)} cy={mapY(RA, yMin, yMax)} r="3" fill="#22c55e" />
        <text
          x={mapX(0.03)}
          y={mapY(RA, yMin, yMax) - 5}
          fontSize="9"
          fill="#22c55e"
          fontFamily="JetBrains Mono, monospace"
        >
          {RA.toFixed(1)} kN
        </text>

        <circle cx={mapX(0.99)} cy={mapY(RB, yMin, yMax)} r="3" fill="#f87171" />
        <text
          x={mapX(0.97) - 50}
          y={mapY(RB, yMin, yMax) + 12}
          fontSize="9"
          fill="#f87171"
          fontFamily="JetBrains Mono, monospace"
        >
          {RB.toFixed(1)} kN
        </text>

        <line
          x1={MARGIN.left}
          y1={MARGIN.top}
          x2={MARGIN.left}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />
        <line
          x1={MARGIN.left}
          y1={MARGIN.top + PLOT_H}
          x2={MARGIN.left + PLOT_W}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />

        <AxisLabels vMin={yMin} vMax={yMax} unit="kN" />
        <SpanAxis spanM={spanM} />

        <text
          x={MARGIN.left + 4}
          y={MARGIN.top + 12}
          fontSize="9"
          fill="#64748b"
          fontFamily="JetBrains Mono, monospace"
        >
          SHEAR FORCE DIAGRAM
        </text>
      </svg>
    </div>
  );
}

// ── Deflection ───────────────────────────────────────────────────────────────

export function DeflectionRenderer({
  resultants,
  slsChecks,
  spanM = 6,
  memberId,
}: {
  resultants: StressResultants;
  slsChecks?: SLSChecks;
  spanM?: number;
  memberId: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  const xs = linspace(0, 1, N_PTS);
  const dMax = resultants.deflection_max_mm;

  // Approximate cubic for simply-supported beam under UDL
  const ys = xs.map((t) => dMax * Math.sin(Math.PI * t));

  const limit = slsChecks?.deflection_limit_mm ?? spanM * 1000 / 250;
  const actual = slsChecks?.deflection_actual_mm ?? dMax;
  const fail = actual > limit;

  const yMin = 0;
  const yMax = Math.max(ys.reduce((a, b) => Math.max(a, b), 0) * 1.2, limit * 1.2, 1);

  const handleDownload = useCallback(
    () => downloadSvg(svgRef.current, `${memberId}_Deflection.svg`),
    [memberId]
  );

  return (
    <div className="relative">
      <button
        onClick={handleDownload}
        className="absolute top-0 right-0 p-1.5 text-muted-foreground hover:text-foreground transition-colors"
        title="Download Deflection"
      >
        <Download className="w-3.5 h-3.5" />
      </button>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: 200 }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect width={W} height={H} fill="#0f172a" />

        {/* Grid */}
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={mapX(t)}
            y1={MARGIN.top}
            x2={mapX(t)}
            y2={MARGIN.top + PLOT_H}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}

        {/* Limit line */}
        <line
          x1={MARGIN.left}
          y1={mapY(limit, yMin, yMax)}
          x2={MARGIN.left + PLOT_W}
          y2={mapY(limit, yMin, yMax)}
          stroke="#f59e0b"
          strokeWidth="1"
          strokeDasharray="6,3"
        />
        <text
          x={MARGIN.left + PLOT_W - 4}
          y={mapY(limit, yMin, yMax) - 4}
          textAnchor="end"
          fontSize="9"
          fill="#f59e0b"
          fontFamily="JetBrains Mono, monospace"
        >
          LIMIT {limit.toFixed(1)}mm
        </text>

        {/* Fill */}
        <path
          d={`M${mapX(0)},${mapY(0, yMin, yMax)}${xs.map((x, i) => `L${mapX(x).toFixed(1)},${mapY(ys[i], yMin, yMax).toFixed(1)}`).join("")}L${mapX(1)},${mapY(0, yMin, yMax)}Z`}
          fill={fail ? "rgba(239,68,68,0.12)" : "rgba(99,102,241,0.12)"}
        />

        {/* Curve */}
        <polyline
          points={polyline(xs, ys, yMin, yMax)}
          fill="none"
          stroke={fail ? "#f87171" : "#818cf8"}
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Peak marker */}
        <circle
          cx={mapX(0.5)}
          cy={mapY(dMax, yMin, yMax)}
          r="3"
          fill={fail ? "#f87171" : "#818cf8"}
        />
        <text
          x={mapX(0.5) + 6}
          y={mapY(dMax, yMin, yMax) + 4}
          fontSize="9"
          fill={fail ? "#f87171" : "#818cf8"}
          fontFamily="JetBrains Mono, monospace"
        >
          δ={dMax.toFixed(1)}mm {fail ? "⚠ EXCEED" : "✓"}
        </text>

        <line
          x1={MARGIN.left}
          y1={MARGIN.top}
          x2={MARGIN.left}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />
        <line
          x1={MARGIN.left}
          y1={MARGIN.top + PLOT_H}
          x2={MARGIN.left + PLOT_W}
          y2={MARGIN.top + PLOT_H}
          stroke="#475569"
          strokeWidth="1"
        />

        <AxisLabels vMin={yMin} vMax={yMax} unit="mm" />
        <SpanAxis spanM={spanM} />

        <text
          x={MARGIN.left + 4}
          y={MARGIN.top + 12}
          fontSize="9"
          fill="#64748b"
          fontFamily="JetBrains Mono, monospace"
        >
          DEFLECTION DIAGRAM
        </text>
      </svg>
    </div>
  );
}

// ── MiniSparkline — used in MemberCard list ──────────────────────────────────

export function MiniSparkline({
  values,
  color = "#818cf8",
  height = 40,
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  if (!values.length) return null;
  const w = 100;
  const h = height;
  const min = Math.min(...values);
  const max = Math.max(...values, min + 1);
  const mx = (i: number) => (i / (values.length - 1)) * w;
  const my = (v: number) => h - 2 - ((v - min) / (max - min)) * (h - 4);
  const pts = values.map((v, i) => `${mx(i).toFixed(1)},${my(v).toFixed(1)}`).join(" ");
  const fill = `M${mx(0)},${h}${values.map((v, i) => `L${mx(i).toFixed(1)},${my(v).toFixed(1)}`).join("")}L${w},${h}Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }}>
      <path d={fill} fill={color} opacity={0.15} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

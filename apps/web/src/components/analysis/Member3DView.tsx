"use client";

/**
 * @file Member3DView.tsx
 * @description SVG-based pseudo-3D rendering of a structural member.
 *
 * The backend supplies only plan-space geometry (no Z/elevation), so a true
 * 3D scene would be mostly synthetic. Instead we draw an honest isometric
 * extrusion of the member's section (b × h) along its span, with applied-load
 * arrows (UDL), support symbols, and a span dimension line. This gives the
 * engineer an immediate read of proportions and loading without a 3D engine.
 *
 * Beams/walls render as extruded prisms; columns render as a vertical prism;
 * slabs render as a thin extruded plate.
 */

import React, { useRef, useCallback } from "react";
import { Download, Box } from "lucide-react";
import type { GeometricMember } from "@/types/canvas";
import type { AnalysisMemberType, MemberCheckStatus } from "@/types/analysis";

const W = 520;
const H = 240;

// Isometric projection unit vectors (screen px per world unit).
const ISO_X = { x: 0.92, y: 0.38 };
const ISO_Y = { x: -0.92, y: 0.38 };
const ISO_Z = { x: 0, y: -1 };

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

function project(p: Vec3, ox: number, oy: number, s: number) {
  return {
    x: ox + (p.x * ISO_X.x + p.y * ISO_Y.x + p.z * ISO_Z.x) * s,
    y: oy + (p.x * ISO_X.y + p.y * ISO_Y.y + p.z * ISO_Z.y) * s,
  };
}

/** Render an axis-aligned box (L along x, B along y, Hh along z) as 3 faces. */
function boxFaces(
  L: number,
  B: number,
  Hh: number,
  ox: number,
  oy: number,
  s: number
) {
  const v = (x: number, y: number, z: number) =>
    project({ x, y, z }, ox, oy, s);

  // 8 corners
  const p000 = v(0, 0, 0);
  const p100 = v(L, 0, 0);
  const p110 = v(L, B, 0);
  const p010 = v(0, B, 0);
  const p001 = v(0, 0, Hh);
  const p101 = v(L, 0, Hh);
  const p111 = v(L, B, Hh);
  const p011 = v(0, B, Hh);

  const poly = (pts: { x: number; y: number }[]) =>
    pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return {
    top: poly([p001, p101, p111, p011]),
    front: poly([p000, p100, p101, p001]),
    side: poly([p100, p110, p111, p101]),
    // section face (the b×h end, shown to the viewer at the near corner)
    section: poly([p000, p010, p011, p001]),
  };
}

/**
 * Build a stepped flight as a list of projected tread/riser quads, climbing in
 * +x (going) and +z (riser). Conveys an honest staircase shape in the same
 * isometric projection used for the other members.
 */
function stairFaces(steps: number, ox: number, oy: number, s: number) {
  const run = 3.0; // total horizontal model length
  const B = 1.0; // flight width
  const going = run / steps;
  const riser = going * 0.82; // pleasant slope
  const v = (x: number, y: number, z: number) => project({ x, y, z }, ox, oy, s);
  const poly = (pts: { x: number; y: number }[]) =>
    pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  const out: { kind: "tread" | "riser"; points: string }[] = [];
  for (let i = 0; i < steps; i++) {
    const x0 = i * going;
    const z0 = i * riser;
    const x1 = x0 + going;
    const z1 = z0 + riser;
    out.push({ kind: "tread", points: poly([v(x0, 0, z0), v(x1, 0, z0), v(x1, B, z0), v(x0, B, z0)]) });
    out.push({ kind: "riser", points: poly([v(x1, 0, z0), v(x1, B, z0), v(x1, B, z1), v(x1, 0, z1)]) });
  }
  return out;
}

function downloadSvg(svg: SVGSVGElement | null, filename: string) {
  if (!svg) return;
  const xml = new XMLSerializer().serializeToString(svg);
  const blob = new Blob([xml], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const STATUS_STROKE: Record<MemberCheckStatus, string> = {
  pass: "#22c55e",
  fail: "#f87171",
  critical: "#ef4444",
  skipped: "#94a3b8",
};

export function Member3DView({
  member,
  status,
  spanM,
}: {
  member: GeometricMember;
  status: MemberCheckStatus;
  spanM: number;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const type = member.member_type as AnalysisMemberType;

  const b = member.meta.b_mm ?? 300;
  const h = member.meta.h_mm ?? 500;

  // Choose extrusion dimensions per member type (in a normalized model space).
  // We scale so the member roughly fills the viewport regardless of real size.
  const isColumn = type === "column" || type === "footing";
  const isPlate = type === "slab";
  const isStair = type === "staircase";
  const numSteps = Math.max(3, Math.min(18, Math.round(Number(member.meta.num_steps) || 12)));

  // Normalize: longest dimension → ~3.2 model units.
  const lengthModel = 3.4;
  const bModel = Math.max(0.4, Math.min(1.4, (b / Math.max(b, h)) * 1.2));
  const hModel = Math.max(0.4, Math.min(1.6, (h / Math.max(b, h)) * 1.4));

  let L: number, B: number, Hh: number;
  if (isColumn) {
    // Vertical prism: extrude section upward.
    L = bModel;
    B = bModel;
    Hh = lengthModel;
  } else if (isPlate) {
    // Thin plate.
    L = lengthModel;
    B = lengthModel * 0.7;
    Hh = 0.25;
  } else {
    // Beam/wall: extrude section along span.
    L = lengthModel;
    B = bModel;
    Hh = hModel;
  }

  const scale = isStair ? 36 : 42;
  const ox = W / 2 + (isStair ? -70 : 30);
  const oy = H / 2 + (isColumn ? 50 : isStair ? 60 : 20);
  const faces = boxFaces(L, B, Hh, ox, oy, scale);
  const steps = isStair ? stairFaces(numSteps, ox, oy, scale) : [];

  const stroke = STATUS_STROKE[status];

  const handleDownload = useCallback(
    () => downloadSvg(svgRef.current, `${member.member_id}_3d.svg`),
    [member.member_id]
  );

  // UDL arrows along the top of a beam.
  const loadArrows: React.ReactNode[] = [];
  if (!isColumn && !isStair) {
    const n = 6;
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const top = project({ x: t * L, y: B / 2, z: Hh }, ox, oy, scale);
      const above = project({ x: t * L, y: B / 2, z: Hh + 0.6 }, ox, oy, scale);
      loadArrows.push(
        <g key={i}>
          <line
            x1={above.x}
            y1={above.y}
            x2={top.x}
            y2={top.y}
            stroke="#f59e0b"
            strokeWidth="1.3"
          />
          <path
            d={`M${top.x},${top.y} l-3,-5 l6,0 z`}
            fill="#f59e0b"
          />
        </g>
      );
    }
  }

  return (
    <div className="relative bg-slate-900 rounded-md overflow-hidden border border-border/40">
      <div className="absolute top-2 left-3 z-10 flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400">
        <Box className="w-3 h-3" />
        Member View
      </div>
      <button
        onClick={handleDownload}
        className="absolute top-2 right-2 z-10 p-1.5 text-slate-400 hover:text-white transition-colors"
        title="Download view"
      >
        <Download className="w-3.5 h-3.5" />
      </button>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: H }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id="m3d-grid"
            width="20"
            height="20"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 20 0 L 0 0 0 20"
              fill="none"
              stroke="rgba(148,163,184,0.08)"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="#0f172a" />
        <rect width={W} height={H} fill="url(#m3d-grid)" />

        {isStair ? (
          /* Stepped flight — tread + riser quads climbing in isometric space */
          steps.map((q, i) => (
            <polygon
              key={i}
              points={q.points}
              fill={q.kind === "tread" ? "rgba(129,140,248,0.40)" : "rgba(99,102,241,0.20)"}
              stroke={stroke}
              strokeWidth="1.1"
            />
          ))
        ) : (
          /* Box faces — shaded for depth */
          <>
            <polygon points={faces.front} fill="rgba(99,102,241,0.28)" stroke={stroke} strokeWidth="1.2" />
            <polygon points={faces.side} fill="rgba(99,102,241,0.16)" stroke={stroke} strokeWidth="1.2" />
            <polygon points={faces.top} fill="rgba(129,140,248,0.40)" stroke={stroke} strokeWidth="1.2" />
            <polygon points={faces.section} fill="rgba(165,180,252,0.5)" stroke={stroke} strokeWidth="1.4" />
          </>
        )}

        {/* Load arrows */}
        {loadArrows}

        {/* Section dimension callout (b × h) */}
        <text
          x={16}
          y={H - 16}
          fontSize="10"
          fill="#cbd5e1"
          fontFamily="JetBrains Mono, monospace"
        >
          {`${type.toUpperCase()}  ${Math.round(b)} × ${Math.round(h)} mm`}
        </text>
        {!isColumn && (
          <text
            x={W - 16}
            y={H - 16}
            textAnchor="end"
            fontSize="10"
            fill="#cbd5e1"
            fontFamily="JetBrains Mono, monospace"
          >
            {`SPAN ${spanM.toFixed(2)} m`}
          </text>
        )}
        {isColumn && (
          <text
            x={W - 16}
            y={H - 16}
            textAnchor="end"
            fontSize="10"
            fill="#cbd5e1"
            fontFamily="JetBrains Mono, monospace"
          >
            {`HEIGHT ${spanM.toFixed(2)} m`}
          </text>
        )}
      </svg>
    </div>
  );
}

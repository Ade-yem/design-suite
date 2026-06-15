"use client";

/**
 * @file ConnectedMembers.tsx
 * @description Lists members structurally connected to the selected one, with
 * the force/reaction each transfers across the joint. Clicking a row jumps the
 * drawer selection (and canvas selection) to that member.
 *
 * Connectivity is derived from plan-space geometry by
 * `lib/analysis/connectivity.ts`.
 */

import React, { useMemo } from "react";
import { ArrowRight, Link2 } from "lucide-react";
import { useCanvasStore } from "@/stores/canvasStore";
import { useAnalysisStore } from "@/stores/analysisStore";
import {
  findConnectedMembers,
  relationLabel,
} from "@/lib/analysis/connectivity";
import type { GeometricMember } from "@/types/canvas";

const TYPE_DOT: Record<GeometricMember["member_type"], string> = {
  beam: "bg-indigo-500",
  column: "bg-amber-500",
  slab: "bg-emerald-500",
  wall: "bg-slate-500",
  footing: "bg-orange-600",
  staircase: "bg-teal-500",
  void: "bg-red-500",
};

export function ConnectedMembers({ memberId }: { memberId: string }) {
  const members = useCanvasStore((s) => s.members);
  const memberAnalysisMap = useAnalysisStore((s) => s.memberAnalysisMap);
  const openForMember = useAnalysisStore((s) => s.openForMember);
  const selectOnCanvas = useCanvasStore((s) => s.selectMember);
  const hoverOnCanvas = useCanvasStore((s) => s.hoverMember);

  const connections = useMemo(
    () => findConnectedMembers(memberId, members, memberAnalysisMap),
    [memberId, members, memberAnalysisMap]
  );

  if (connections.length === 0) {
    return (
      <div className="px-4 py-3 text-[11px] text-muted-foreground italic">
        No connected members detected from the geometry.
      </div>
    );
  }

  const jumpTo = (id: string) => {
    selectOnCanvas(id);
    openForMember(id);
  };

  return (
    <div>
      <div className="flex items-center gap-1.5 px-4 pt-3 pb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Link2 className="w-3 h-3" />
        Connected members ({connections.length})
      </div>
      <div className="px-2 pb-2 space-y-1">
        {connections.map((c) => (
          <button
            key={c.member_id}
            onClick={() => jumpTo(c.member_id)}
            onMouseEnter={() => hoverOnCanvas(c.member_id)}
            onMouseLeave={() => hoverOnCanvas(null)}
            className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left group"
          >
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${TYPE_DOT[c.member_type]}`}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-xs font-semibold text-foreground">
                  {c.member_id}
                </span>
                <span className="text-[10px] text-muted-foreground truncate">
                  {c.member_type} · {relationLabel(c.relation)} · {c.location}
                </span>
              </div>
            </div>
            {c.force && (
              <span className="font-mono text-[10px] text-foreground/80 shrink-0">
                {c.force.value.toFixed(1)} {c.force.unit}
              </span>
            )}
            <ArrowRight className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}

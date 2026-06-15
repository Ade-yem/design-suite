"use client";

/**
 * @file MemberAnalysisDrawer.tsx
 * @description Per-member analysis & calculation verification drawer.
 *
 * Opens over the workspace when an engineer clicks a member after analysis is
 * complete. Surfaces the full picture for one member:
 *   • pseudo-3D member view (Member3DView)
 *   • tabbed diagrams: Overview, BMD, SFD, Deflection, Loads, Rebar, Calc sheet
 *   • connected members and the force each transfers (ConnectedMembers)
 *   • download of every rendered diagram and the calculation sheet
 *
 * Data comes from `analysisStore` (analysis + design results) and member
 * geometry from `canvasStore`.
 */

import React, { useMemo } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCanvasStore } from "@/stores/canvasStore";
import {
  useAnalysisStore,
  type DiagramTab,
} from "@/stores/analysisStore";
import type { MemberCheckStatus } from "@/types/analysis";
import {
  BMDRenderer,
  SFDRenderer,
  DeflectionRenderer,
} from "./DiagramRenderer";
import { Member3DView } from "./Member3DView";
import { OverviewTab } from "./tabs/OverviewTab";
import { LoadsTab } from "./tabs/LoadsTab";
import { RebarTab } from "./tabs/RebarTab";
import { CalcSheetTab } from "./tabs/CalcSheetTab";
import { ConnectedMembers } from "./ConnectedMembers";

const TABS: { id: DiagramTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "bmd", label: "BMD" },
  { id: "sfd", label: "SFD" },
  { id: "deflection", label: "Deflection" },
  { id: "loads", label: "Loads" },
  { id: "rebar", label: "Rebar" },
  { id: "calc", label: "Calc" },
];

const STATUS_PILL: Record<
  MemberCheckStatus,
  { label: string; cls: string }
> = {
  pass: { label: "PASS", cls: "bg-status-done/15 text-status-done" },
  fail: { label: "FAIL", cls: "bg-destructive/15 text-destructive" },
  critical: {
    label: "CRITICAL FAIL",
    cls: "bg-destructive/20 text-destructive",
  },
  skipped: { label: "SKIPPED", cls: "bg-muted/40 text-muted-foreground" },
};

/** Representative span/height of a member, in metres. */
function memberSpanM(
  spans?: number[],
  lClear?: number,
  start?: { x: number; y: number } | null,
  end?: { x: number; y: number } | null
): number {
  if (spans && spans.length) return Math.max(...spans);
  if (lClear) return lClear;
  if (start && end) {
    // start/end are mm in DXF space → m
    return Math.hypot(end.x - start.x, end.y - start.y) / 1000;
  }
  return 6;
}

export function MemberAnalysisDrawer() {
  const isDrawerOpen = useAnalysisStore((s) => s.isDrawerOpen);
  const selectedMemberId = useAnalysisStore((s) => s.selectedMemberId);
  const activeTab = useAnalysisStore((s) => s.activeTab);
  const setActiveTab = useAnalysisStore((s) => s.setActiveTab);
  const closeDrawer = useAnalysisStore((s) => s.closeDrawer);
  const memberAnalysisMap = useAnalysisStore((s) => s.memberAnalysisMap);
  const memberDesignMap = useAnalysisStore((s) => s.memberDesignMap);
  const getMemberStatus = useAnalysisStore((s) => s.getMemberStatus);
  const getUtilizationRatio = useAnalysisStore((s) => s.getUtilizationRatio);
  const designResults = useAnalysisStore((s) => s.designResults);

  const members = useCanvasStore((s) => s.members);

  const member = useMemo(
    () => members.find((m) => m.member_id === selectedMemberId) ?? null,
    [members, selectedMemberId]
  );

  if (!isDrawerOpen || !selectedMemberId) return null;

  const analysis = memberAnalysisMap.get(selectedMemberId) ?? null;
  const design = memberDesignMap.get(selectedMemberId) ?? null;
  const status = getMemberStatus(selectedMemberId);
  const util = getUtilizationRatio(selectedMemberId);
  const pill = STATUS_PILL[status];
  const designCode = designResults?.design_code ?? "BS8110";

  const spanM = memberSpanM(
    member?.spans_m,
    member?.meta.L_clear as number | undefined,
    member?.start_point,
    member?.end_point
  );

  return (
    <div className="w-[520px] max-w-[80vw] flex flex-col border-l border-border bg-background shrink-0 h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono text-lg font-bold text-foreground">
            {selectedMemberId}
          </span>
          <span
            className={cn(
              "text-[10px] font-bold uppercase px-2 py-0.5 rounded",
              pill.cls
            )}
          >
            {pill.label}
          </span>
          {util > 0 && (
            <span
              className={cn(
                "text-xs font-mono",
                util > 1 ? "text-destructive" : "text-muted-foreground"
              )}
            >
              util {util.toFixed(2)} {util > 1 ? "> 1.00" : "< 1.00"}
            </span>
          )}
        </div>
        <button
          onClick={closeDrawer}
          className="p-1 hover:bg-muted/60 rounded transition-colors shrink-0"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">
        {/* Pseudo-3D view */}
        {member && (
          <div className="p-3">
            <Member3DView member={member} status={status} spanM={spanM} />
          </div>
        )}

        {/* Tab bar */}
        <div className="flex items-center gap-0.5 px-3 border-b border-border overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 -mb-px transition-colors",
                activeTab === t.id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="p-3">
          {activeTab === "overview" && (
            <OverviewTab analysis={analysis} design={design} />
          )}
          {activeTab === "bmd" &&
            (analysis ? (
              <BMDRenderer
                resultants={analysis.stress_resultants}
                spanM={spanM}
                memberId={selectedMemberId}
              />
            ) : (
              <EmptyDiagram />
            ))}
          {activeTab === "sfd" &&
            (analysis ? (
              <SFDRenderer
                resultants={analysis.stress_resultants}
                reactions={analysis.reactions_kN ?? []}
                spanM={spanM}
                memberId={selectedMemberId}
              />
            ) : (
              <EmptyDiagram />
            ))}
          {activeTab === "deflection" &&
            (analysis ? (
              <DeflectionRenderer
                resultants={analysis.stress_resultants}
                slsChecks={analysis.SLS_checks}
                spanM={spanM}
                memberId={selectedMemberId}
              />
            ) : (
              <EmptyDiagram />
            ))}
          {activeTab === "loads" && (
            <LoadsTab analysis={analysis} spanM={spanM} />
          )}
          {activeTab === "rebar" && <RebarTab design={design} />}
          {activeTab === "calc" && (
            <CalcSheetTab
              analysis={analysis}
              design={design}
              designCode={designCode}
            />
          )}
        </div>

        {/* Connected members */}
        <div className="border-t border-border mt-2">
          <ConnectedMembers memberId={selectedMemberId} />
        </div>
      </div>
    </div>
  );
}

function EmptyDiagram() {
  return (
    <p className="text-xs text-muted-foreground italic p-4">
      No analysis result available to plot this diagram.
    </p>
  );
}

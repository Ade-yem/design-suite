"use client";

import { useState } from "react";
import {
  FileSearch,
  CheckCircle2,
  Calculator,
  PenTool,
  Loader2,
  ChevronLeft,
  ListTodo,
  Layers,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { apiClient } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  type Stage,
  GATE_LABELS,
  GATE_STAGE,
  getPipelineStatus,
} from "@/lib/pipelineStatus";

const STAGES: { id: Stage; label: string; icon: React.ElementType }[] = [
  { id: "parsing", label: "Parsing", icon: FileSearch },
  { id: "verification", label: "Verification", icon: CheckCircle2 },
  { id: "calculation", label: "Calculation", icon: Calculator },
  { id: "drafting", label: "Final Drafting", icon: PenTool },
];

interface PipelineRailProps {
  /** The project whose pipeline this rail drives. */
  projectId: string;
  /** The coarse stage the pipeline is currently in. */
  currentStage: Stage;
  /** The fine-grained backend pipeline status (for the active stage's sublabel). */
  pipelineStatus: string;
}

/**
 * PipelineRail — the single persistent surface that narrates pipeline progress
 * and hosts the safety-gate approvals. It replaces the header StageTracker and
 * pulls the gate approve/resume action out of the closeable chat panel so the
 * most important action in the product is always visible.
 */
export function PipelineRail({
  projectId,
  currentStage,
  pipelineStatus,
}: PipelineRailProps) {
  const {
    pendingGate,
    setPendingGate,
    pipelineRailExpanded,
    setPipelineRailExpanded,
    membersPanelExpanded,
    setMembersPanelExpanded,
  } = useUIStore();
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!pipelineRailExpanded) {
    return (
      <div className="w-12 h-full flex flex-col bg-muted/40 border-r border-border shrink-0 items-center py-4 gap-4">
        {/* Pipeline Rail Trigger */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => setPipelineRailExpanded(true)}
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label="Expand Pipeline"
            >
              <ListTodo className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" align="center">
            Expand Pipeline
          </TooltipContent>
        </Tooltip>

        {/* Stacked Members Panel Trigger (only if both are collapsed) */}
        {!membersPanelExpanded && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setMembersPanelExpanded(true)}
                className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Expand Members list"
              >
                <Layers className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" align="center">
              Expand Members list
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    );
  }

  const currentIdx = STAGES.findIndex((s) => s.id === currentStage);
  const statusLabel = getPipelineStatus(pipelineStatus).label;

  // The stage that owns the pending gate, if any.
  const pendingStage = pendingGate ? GATE_STAGE[pendingGate.gate] : null;

  const handleApprove = async () => {
    setApproving(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/pipeline/${projectId}/resume`);
      setPendingGate(null);
    } catch (err: unknown) {
      setError(
        (err as { detail?: string }).detail ?? "Failed to resume pipeline.",
      );
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="w-56 shrink-0 h-full border-r border-border bg-card flex flex-col">
      <div className="h-8 px-3 border-b border-border flex items-center justify-between shrink-0">
        <span className="text-xs font-mono text-muted-foreground">
          Pipeline
        </span>
        <button
          onClick={() => setPipelineRailExpanded(false)}
          className="p-1 hover:bg-muted/60 rounded transition-colors"
          title="Collapse Pipeline rail"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        {STAGES.map((stage, idx) => {
          const isActive = idx === currentIdx;
          const isCompleted = idx < currentIdx;
          const Icon = stage.icon;
          // The geometry gate is approved on the canvas (auto-resumes); the rail
          // only surfaces an actionable approval for the downstream WS gates.
          const gateHere =
            pendingGate && pendingStage === stage.id ? pendingGate : null;
          const isGeometryGate = gateHere?.gate === "geometry_gate";

          return (
            <div key={stage.id} className="flex flex-col">
              <div className="flex items-center gap-2.5">
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-md transition-colors shrink-0",
                    isActive && "bg-primary/15 text-primary",
                    isCompleted && "bg-success/15 text-success",
                    !isActive && !isCompleted && "text-muted-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <p
                    className={cn(
                      "text-xs font-medium leading-tight",
                      isActive && "text-primary",
                      isCompleted && "text-success",
                      !isActive && !isCompleted && "text-muted-foreground",
                    )}
                  >
                    {stage.label}
                  </p>
                  {isActive && (
                    <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                      {statusLabel}
                    </p>
                  )}
                </div>
              </div>

              {/* Gate action slot for this stage */}
              {gateHere && (
                <div className="ml-9 mt-2 rounded-md border border-primary/40 bg-primary/5 px-2.5 py-2 space-y-2">
                  <p className="text-[10px] font-medium text-primary">
                    Review Required
                  </p>
                  <p className="text-[10px] text-muted-foreground leading-snug">
                    {GATE_LABELS[gateHere.gate] ?? gateHere.label}
                  </p>
                  {error && (
                    <p className="text-[10px] text-destructive">{error}</p>
                  )}
                  {isGeometryGate ? (
                    <p className="text-[10px] text-muted-foreground italic">
                      Confirm the layout on the canvas to continue.
                    </p>
                  ) : (
                    <button
                      onClick={handleApprove}
                      disabled={approving}
                      className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-primary text-primary-foreground text-[11px] font-medium hover:bg-primary/90 transition-colors disabled:opacity-60"
                    >
                      {approving && (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      )}
                      Approve &amp; Continue
                    </button>
                  )}
                </div>
              )}

              {/* Vertical connector */}
              {idx < STAGES.length - 1 && (
                <div
                  className={cn(
                    "ml-3.5 my-1 w-px h-4",
                    isCompleted ? "bg-success" : "bg-border",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

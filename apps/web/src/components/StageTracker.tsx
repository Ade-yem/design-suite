import { FileSearch, CheckCircle2, Calculator, PenTool } from "lucide-react";
import { cn } from "@/lib/utils";

export type Stage = "parsing" | "verification" | "calculation" | "drafting";

const stages: { id: Stage; label: string; icon: React.ElementType }[] = [
  { id: "parsing", label: "Parsing", icon: FileSearch },
  { id: "verification", label: "Verification", icon: CheckCircle2 },
  { id: "calculation", label: "Calculation", icon: Calculator },
  { id: "drafting", label: "Final Drafting", icon: PenTool },
];

// Maps backend pipeline_status labels to the frontend Stage type.
const STATUS_TO_STAGE: Record<string, Stage> = {
  created: "parsing",
  file_uploaded: "parsing",
  geometry_verified: "verification",
  loading_defined: "calculation",
  analysis_complete: "calculation",
  design_complete: "drafting",
  report_generated: "drafting",
};

export function pipelineStatusToStage(status: string): Stage {
  return STATUS_TO_STAGE[status] ?? "parsing";
}

interface StageTrackerProps {
  currentStage: Stage;
}

export function StageTracker({ currentStage }: StageTrackerProps) {
  const currentIdx = stages.findIndex((s) => s.id === currentStage);

  return (
    <div className="flex items-center gap-1 px-2">
      {stages.map((stage, idx) => {
        const isActive = idx === currentIdx;
        const isCompleted = idx < currentIdx;
        const Icon = stage.icon;

        return (
          <div key={stage.id} className="flex items-center">
            <div
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                isActive && "bg-primary/15 text-primary",
                isCompleted && "text-success",
                !isActive && !isCompleted && "text-muted-foreground"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">{stage.label}</span>
            </div>
            {idx < stages.length - 1 && (
              <div
                className={cn(
                  "w-8 h-px mx-1",
                  isCompleted ? "bg-success" : "bg-border"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

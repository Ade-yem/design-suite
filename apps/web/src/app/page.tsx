"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppHeader } from "@/components/AppHeader";
import { ChatSidebar } from "@/components/ChatSidebar";
import { CanvasViewport } from "@/components/CanvasViewport";
import { pipelineStatusToStage } from "@/components/StageTracker";
import { useProjectStore } from "@/stores/projectStore";

export default function WorkspacePage() {
  const router = useRouter();
  const { activeProject, refreshActiveProject, updateActiveProjectStatus } =
    useProjectStore();

  // Redirect to dashboard if no project selected
  useEffect(() => {
    if (!activeProject) {
      router.push("/dashboard");
    }
  }, [activeProject, router]);

  // Refresh project status on mount so StageTracker reflects DB state
  useEffect(() => {
    if (activeProject) {
      refreshActiveProject();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.project_id]);

  if (!activeProject) return null;

  const currentStage = pipelineStatusToStage(activeProject.pipeline_status);

  const handleGateReached = (gate: string) => {
    // Map gate names to the status that follows confirmation
    const gateStatusMap: Record<string, { status: string; ordinal: number }> = {
      geometry_gate: { status: "geometry_verified", ordinal: 2 },
      loading_gate: { status: "loading_defined", ordinal: 3 },
      design_gate: { status: "design_complete", ordinal: 5 },
      drawing_gate: { status: "report_generated", ordinal: 6 },
    };
    const next = gateStatusMap[gate];
    if (next) {
      updateActiveProjectStatus(next.status, next.ordinal);
    }
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <AppHeader currentStage={currentStage} />
      <div className="flex-1 flex min-h-0">
        <div className="w-80 shrink-0">
          <ChatSidebar
            projectId={activeProject.project_id}
            onGateReached={handleGateReached}
          />
        </div>
        <div className="flex-1 min-w-0">
          <CanvasViewport
            projectId={activeProject.project_id}
            onParsed={() => refreshActiveProject()}
          />
        </div>
      </div>
    </div>
  );
}

"use client";

import { JSX, useEffect, useRef, useState } from "react";
import { Upload, X, Loader2, Compass } from "lucide-react";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { ChatSidebar } from "@/components/ChatSidebar";
import {
  CanvasViewport,
  type CanvasViewportHandle,
} from "@/components/canvas/CanvasViewport";
import { ProjectSidebar } from "@/components/ProjectSidebar";
import { ProjectPrompt } from "@/components/ProjectPrompt";
import { NewProjectModal } from "@/components/NewProjectModal";
import { pipelineStatusToStage } from "@/components/StageTracker";
import { useProjectStore } from "@/stores/projectStore";
import { useUIStore } from "@/stores/uiStore";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/project";

/**
 * UploadNudge component props.
 */
interface UploadNudgeProps {
  projectName: string;
  onBrowse: () => void;
  onDismiss: () => void;
}

/**
 * Renders a helpful onboarding nudge at the top of the workspace
 * to guide users to upload their DXF/PDF drawing when a new project is created.
 *
 * @param {UploadNudgeProps} props - Component properties.
 * @returns {JSX.Element} The rendered UploadNudge element.
 */
function UploadNudge({
  projectName,
  onBrowse,
  onDismiss,
}: UploadNudgeProps): JSX.Element {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-primary/10 border-b border-primary/20 animate-fade-in-up shrink-0">
      <Upload className="h-3.5 w-3.5 text-primary shrink-0" />
      <p className="flex-1 text-xs text-foreground">
        <span className="font-medium">{projectName}</span> created.{" "}
        <span className="text-muted-foreground">
          Upload a DXF or PDF drawing to begin structural analysis.
        </span>
      </p>
      <button
        onClick={onBrowse}
        className="shrink-0 px-3 py-1 bg-primary text-primary-foreground text-xs font-medium rounded-md hover:bg-primary/90 transition-colors"
      >
        Upload Drawing
      </button>
      <button
        onClick={onDismiss}
        className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/**
 * WorkspaceLoadingPlaceholder component.
 * Renders a high-fidelity, blueprint-themed engineering CAD canvas loader
 * to display while the application is in a loading state.
 *
 * @returns {JSX.Element} The rendered CAD workspace loader placeholder component.
 */
function WorkspaceLoadingPlaceholder(): JSX.Element {
  return (
    <div className="fixed inset-0 bg-canvas-bg flex items-center justify-center z-100">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-12 h-12 border-2 border-primary border-t-transparent rounded-full animate-spin glow-blue" />
        <p className="text-muted-foreground text-sm font-mono tracking-wider">
          LOADING ENVIRONMENT...
        </p>
      </div>
    </div>
  );
}

/**
 * WorkspacePage root client component.
 * Sets up the multi-agent integrated development environment, isolating
 * custom toolbars, high-fidelity canvas contexts, and side-by-side conversational interfaces.
 *
 * @returns {JSX.Element} The rendered WorkspacePage element.
 */
export default function WorkspacePage(): JSX.Element {
  const {
    activeProject,
    refreshActiveProject,
    updateActiveProjectStatus,
    setActiveProject,
    isLoading,
  } = useProjectStore();
  const { chatOpen, setChatOpen, setGatePending } = useUIStore();

  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [showUploadNudge, setShowUploadNudge] = useState(false);

  const canvasRef = useRef<CanvasViewportHandle>(null);

  useKeyboardShortcuts({
    onNewProject: () => setShowNewProjectModal(true),
  });

  useEffect(() => {
    if (activeProject) {
      refreshActiveProject();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.project_id]);

  const currentStage = activeProject
    ? pipelineStatusToStage(activeProject.pipeline_status)
    : "parsing";

  const handleGateReached = (gate: string) => {
    const gateStatusMap: Record<string, { status: string; ordinal: number }> = {
      geometry_gate: { status: "geometry_verified", ordinal: 2 },
      loading_gate: { status: "loading_defined", ordinal: 3 },
      design_gate: { status: "design_complete", ordinal: 5 },
      drawing_gate: { status: "report_generated", ordinal: 6 },
    };
    const next = gateStatusMap[gate];
    if (next) updateActiveProjectStatus(next.status, next.ordinal);

    // A reached gate blocks the pipeline on the engineer's approval — the single
    // most important action in the product. Force the chat (which hosts the
    // approval) open and flag the gate so the header can draw attention to it,
    // so the action can't stay hidden behind a closed panel.
    setChatOpen(true);
    setGatePending(true);
  };

  const handleCreated = (project: Project) => {
    setActiveProject(project);
    setShowNewProjectModal(false);
    setShowUploadNudge(true);
  };

  return (
    <div className="h-screen flex overflow-hidden">
      <ProjectSidebar />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {isLoading ? (
          <WorkspaceLoadingPlaceholder />
        ) : activeProject ? (
          <>
            <WorkspaceHeader currentStage={currentStage} />

            {/* Upload nudge — shown immediately after project creation */}
            {showUploadNudge && (
              <UploadNudge
                projectName={activeProject.name}
                onBrowse={() => {
                  canvasRef.current?.triggerFilePicker();
                  setShowUploadNudge(false);
                }}
                onDismiss={() => setShowUploadNudge(false)}
              />
            )}

            <div className="flex-1 flex min-h-0 overflow-hidden">
              <div className="flex-1 min-w-0 overflow-hidden">
                <CanvasViewport
                  ref={canvasRef}
                  projectId={activeProject.project_id}
                  onParsed={() => refreshActiveProject()}
                  onUploadStart={() => setShowUploadNudge(false)}
                />
              </div>
              <div
                className={cn(
                  "shrink-0 overflow-hidden",
                  "transition-[width] duration-200 ease-out",
                  chatOpen ? "w-80" : "w-0",
                )}
              >
                <div className="w-80 h-full">
                  <ChatSidebar
                    projectId={activeProject.project_id}
                    onGateReached={handleGateReached}
                    onClose={() => setChatOpen(false)}
                  />
                </div>
              </div>
            </div>
          </>
        ) : (
          <ProjectPrompt />
        )}
      </div>

      {showNewProjectModal && (
        <NewProjectModal
          onClose={() => setShowNewProjectModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}

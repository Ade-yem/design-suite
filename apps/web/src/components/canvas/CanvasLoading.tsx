import { BlueprintIcon } from "@/components/BlueprintIcon";
import { JSX } from "react";

/**
 * WorkspaceLoadingPlaceholder component.
 * Renders a high-fidelity, blueprint-themed engineering CAD canvas loader
 * to display while the application is in a loading state.
 *
 * @returns {JSX.Element} The rendered CAD workspace loader placeholder component.
 */
export function CanvasLoading(): JSX.Element {
  return (
    <div className="fixed inset-0 bg-canvas-bg flex items-center justify-center z-100">
      <div className="flex flex-col items-center space-y-4">
        <BlueprintIcon className="w-16 h-16" state="working" />
        <p className="text-muted-foreground text-sm font-mono tracking-wider">
          Loading your workspace
        </p>
      </div>
    </div>
  );
}
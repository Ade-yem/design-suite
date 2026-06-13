"use client";

import Image from "next/image";
import { ChevronRight, Download, Eye, Lock } from "lucide-react";
import { useArtifactStore, type Artifact } from "@/stores/artifactStore";

const STAGE_LABELS: Record<Artifact["stage"], string> = {
  parsing: "Parsed Geometry",
  verification: "Verified Layout",
  loading: "Load Combinations",
  analysis: "Analysis Results",
  design: "Design Schedule",
  drawing: "Drawing Set",
};

const STATUS_STYLES: Record<Artifact["status"], { bg: string; text: string }> = {
  signed_off: { bg: "bg-status-done/10", text: "text-status-done" },
  in_review: { bg: "bg-status-in-progress/10", text: "text-status-in-progress" },
  pending: { bg: "bg-muted/30", text: "text-muted-foreground" },
};

export const ArtifactsDrawer: React.FC = () => {
  const { artifacts, isDrawerExpanded, setDrawerExpanded } = useArtifactStore();

  if (!isDrawerExpanded) {
    return null;
  }

  return (
    <div className="w-72 flex flex-col border-l border-border bg-muted/20 overflow-hidden shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="text-xs font-semibold text-foreground/80">
          ARTIFACTS
          <span className="ml-2 text-foreground/50">{artifacts.length} stage{artifacts.length !== 1 ? "s" : ""}</span>
        </div>
        <button
          onClick={() => setDrawerExpanded(false)}
          className="p-1 hover:bg-muted/60 rounded transition-colors"
          title="Collapse Artifacts"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Artifact Cards */}
      <div className="flex-1 overflow-y-auto space-y-2 p-3">
        {artifacts.length === 0 ? (
          <p className="text-xs text-foreground/50 italic">
            As gates are approved, artifacts will appear here.
          </p>
        ) : (
          artifacts.map((artifact) => (
            <ArtifactCard key={artifact.id} artifact={artifact} />
          ))
        )}
      </div>
    </div>
  );
};

interface ArtifactCardProps {
  artifact: Artifact;
}

const ArtifactCard: React.FC<ArtifactCardProps> = ({ artifact }) => {
  const stageLabel = STAGE_LABELS[artifact.stage];
  const statusStyle = STATUS_STYLES[artifact.status];
  const statusLabel = artifact.status === "signed_off" ? "SIGNED OFF" : artifact.status === "in_review" ? "IN REVIEW" : "PENDING";

  const date = new Date(artifact.createdAt);
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const timeStr = date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

  // Cards are immutable when signed off
  const isLocked = artifact.status === "signed_off";

  return (
    <div className={`border border-border/50 rounded p-3 ${statusStyle.bg}`}>
      {/* Stage + Status */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1">
          <p className="text-xs font-semibold text-foreground">{stageLabel}</p>
          <p className={`text-[10px] font-mono ${statusStyle.text}`}>{statusLabel}</p>
        </div>
        {isLocked && (
          <Lock className="h-3.5 w-3.5 text-foreground/40 shrink-0 mt-0.5" />
        )}
      </div>

      {/* Timestamp + Author */}
      <div className="text-[10px] text-foreground/60 mb-3">
        <p className="font-mono">{dateStr} {timeStr}</p>
        <p>by {artifact.author}</p>
      </div>

      {/* Preview */}
      {artifact.preview && (
        <div className="mb-3 bg-muted/40 rounded aspect-video overflow-hidden relative">
          <Image
            src={artifact.preview}
            alt={stageLabel}
            fill
            className="object-cover"
            unoptimized
          />
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        {artifact.viewUrl && (
          <button
            onClick={() => window.open(artifact.viewUrl, "_blank")}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 text-xs rounded border border-border/50 text-foreground/70 hover:text-foreground hover:bg-muted/40 transition-colors"
            title="View artifact"
          >
            <Eye className="h-3 w-3" />
            View
          </button>
        )}
        {artifact.downloadUrl && (
          <button
            onClick={() => window.open(artifact.downloadUrl, "_blank")}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 text-xs rounded border border-border/50 text-foreground/70 hover:text-foreground hover:bg-muted/40 transition-colors"
            title="Download artifact"
          >
            <Download className="h-3 w-3" />
            Download
          </button>
        )}
      </div>
    </div>
  );
};

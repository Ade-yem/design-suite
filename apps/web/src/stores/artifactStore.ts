import { create } from "zustand";
import { persist } from "zustand/middleware";
import { apiClient } from "@/lib/api";

/**
 * Artifact represents a stage output (geometry snapshot, load diagram, etc.)
 * frozen at a gate approval point.
 */
export interface Artifact {
  id: string;
  stage: "parsing" | "verification" | "loading" | "analysis" | "design" | "drawing";
  status: "signed_off" | "in_review" | "pending";
  createdAt: string;
  author: string;
  preview?: string;
  downloadUrl?: string;
  viewUrl?: string;
}

interface ArtifactState {
  artifacts: Artifact[];
  isDrawerExpanded: boolean;
}

interface ArtifactActions {
  addArtifact: (artifact: Artifact) => void;
  updateArtifact: (id: string, patch: Partial<Artifact>) => void;
  setDrawerExpanded: (expanded: boolean) => void;
  clearArtifacts: () => void;
  fetchArtifacts: (projectId: string) => Promise<void>;
}

export type ArtifactStore = ArtifactState & ArtifactActions;

export const useArtifactStore = create<ArtifactStore>()(
  persist(
    (set) => ({
      artifacts: [],
      isDrawerExpanded: true,

      addArtifact: (artifact) =>
        set((state) => ({
          artifacts: [...state.artifacts, artifact],
        })),

      updateArtifact: (id, patch) =>
        set((state) => ({
          artifacts: state.artifacts.map((a) =>
            a.id === id ? { ...a, ...patch } : a
          ),
        })),

      setDrawerExpanded: (expanded) => set({ isDrawerExpanded: expanded }),

      clearArtifacts: () => set({ artifacts: [] }),

      fetchArtifacts: async (projectId: string) => {
        try {
          const response = await apiClient.get(`/api/v1/artifacts/${projectId}`);
          const apiArtifacts = response.data as Array<{
            artifact_id: string;
            stage: string;
            status: string;
            created_at: string;
            author: string | null;
            preview_url?: string;
            download_url?: string;
          }>;

          // Map backend response to frontend interface
          const artifacts: Artifact[] = apiArtifacts.map((a) => ({
            id: a.artifact_id,
            stage: a.stage as Artifact["stage"],
            status: a.status as Artifact["status"],
            createdAt: a.created_at,
            author: a.author || "Unknown",
            preview: a.preview_url,
            downloadUrl: a.download_url,
          }));

          set({ artifacts });
        } catch (err) {
          // Gracefully handle 404 (no artifacts yet) or network errors
          console.warn("Failed to fetch artifacts:", err);
        }
      },
    }),
    {
      name: "artifactStore",
    }
  )
);

import { create } from "zustand";
import { persist } from "zustand/middleware";

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
    }),
    {
      name: "artifactStore",
    }
  )
);

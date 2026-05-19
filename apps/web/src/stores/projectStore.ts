import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Project, ProjectListItem, CreateProjectPayload } from "@/types/project";
import { apiClient } from "@/lib/api";

interface ProjectState {
  activeProject: Project | null;
  projects: ProjectListItem[];
  isLoading: boolean;
  error: string | null;
}

interface ProjectActions {
  setActiveProject: (project: Project) => void;
  clearActiveProject: () => void;
  fetchProjects: () => Promise<void>;
  createProject: (data: CreateProjectPayload) => Promise<Project>;
  refreshActiveProject: () => Promise<void>;
  updateActiveProjectStatus: (status: string, ordinal: number) => void;
}

export type ProjectStore = ProjectState & ProjectActions;

export const useProjectStore = create<ProjectStore>()(
  persist(
    (set, get) => ({
      activeProject: null,
      projects: [],
      isLoading: false,
      error: null,

      setActiveProject: (project) => set({ activeProject: project }),

      clearActiveProject: () => set({ activeProject: null }),

      fetchProjects: async () => {
        set({ isLoading: true, error: null });
        try {
          const { data } = await apiClient.get<ProjectListItem[]>("/api/v1/projects/");
          set({ projects: data, isLoading: false });
        } catch (err: unknown) {
          const detail = (err as { detail?: string }).detail ?? "Failed to load projects.";
          set({ error: detail, isLoading: false });
        }
      },

      createProject: async (payload) => {
        const { data } = await apiClient.post<Project>("/api/v1/projects/", payload);
        set((state) => ({
          projects: [
            {
              project_id: data.project_id,
              name: data.name,
              reference: data.reference,
              pipeline_status: data.pipeline_status,
              updated_at: data.updated_at,
            },
            ...state.projects,
          ],
        }));
        return data;
      },

      refreshActiveProject: async () => {
        const active = get().activeProject;
        if (!active) return;
        try {
          const { data } = await apiClient.get<Project>(`/api/v1/projects/${active.project_id}`);
          set({ activeProject: data });
        } catch {
          // silently ignore — stale data is acceptable
        }
      },

      updateActiveProjectStatus: (status, ordinal) => {
        set((state) => {
          if (!state.activeProject) return {};
          return {
            activeProject: {
              ...state.activeProject,
              pipeline_status: status,
              pipeline_status_ordinal: ordinal,
            },
          };
        });
      },
    }),
    {
      name: "structai-project-session",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ activeProject: state.activeProject }),
    }
  )
);

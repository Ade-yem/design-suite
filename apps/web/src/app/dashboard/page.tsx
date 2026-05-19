"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Hexagon,
  Plus,
  Folder,
  ChevronRight,
  Loader2,
  X,
} from "lucide-react";
import { useProjectStore } from "@/stores/projectStore";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import type { Project, CreateProjectPayload } from "@/types/project";

const DESIGN_CODES = ["BS8110", "EC2"] as const;

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function statusColor(status: string): string {
  if (status === "created") return "text-muted-foreground";
  if (status === "report_generated") return "text-green-400";
  return "text-primary";
}

export default function DashboardPage() {
  const router = useRouter();
  const { projects, isLoading, error, fetchProjects, createProject, setActiveProject } =
    useProjectStore();
  const { clearAuth } = useAuthStore();

  const [showNewForm, setShowNewForm] = useState(false);
  const [formData, setFormData] = useState<CreateProjectPayload>({
    name: "",
    reference: "",
    client: "",
    design_code: "BS8110",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleOpenProject = async (projectId: string) => {
    try {
      const { data } = await apiClient.get<Project>(`/api/v1/projects/${projectId}`);
      setActiveProject(data);
      router.push("/");
    } catch {
      // fallback: navigate anyway — page.tsx will refresh
      router.push("/");
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Project name is required.");
      return;
    }
    if (!formData.reference.trim()) {
      setFormError("Reference is required.");
      return;
    }
    setFormError(null);
    setCreating(true);
    try {
      const project = await createProject(formData);
      setActiveProject(project);
      router.push("/");
    } catch (err: unknown) {
      setFormError((err as { detail?: string }).detail ?? "Failed to create project.");
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas-bg text-foreground">
      {/* Header */}
      <header className="h-12 flex items-center justify-between px-6 border-b border-border bg-card">
        <div className="flex items-center gap-2.5">
          <Hexagon className="h-5 w-5 text-primary" />
          <span className="text-sm font-semibold tracking-tight">StructAI</span>
          <span className="text-xs text-muted-foreground font-mono">Copilot</span>
        </div>
        <button
          onClick={() => clearAuth()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors font-mono"
        >
          Sign out
        </button>
      </header>

      {/* Body */}
      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold">Projects</h1>
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Select a project or create a new one to begin.
            </p>
          </div>
          <button
            onClick={() => setShowNewForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 px-4 py-3 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm">
            {error}
          </div>
        )}

        {/* Project list */}
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm py-12 justify-center">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Loading projects…</span>
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <Folder className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p className="text-sm">No projects yet.</p>
            <p className="text-xs mt-1 font-mono">Click &ldquo;New Project&rdquo; to get started.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {projects.map((p) => (
              <button
                key={p.project_id}
                onClick={() => handleOpenProject(p.project_id)}
                className="w-full flex items-center gap-4 px-4 py-3.5 rounded-lg bg-card border border-border hover:border-primary/40 hover:bg-card/80 transition-all text-left group"
              >
                <Folder className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{p.name}</p>
                  <p className="text-xs text-muted-foreground font-mono mt-0.5">{p.reference}</p>
                </div>
                <span className={`text-xs font-mono capitalize ${statusColor(p.pipeline_status)}`}>
                  {statusLabel(p.pipeline_status)}
                </span>
                <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </main>

      {/* New project modal */}
      {showNewForm && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-xl w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-sm font-semibold">New Project</h2>
              <button
                onClick={() => { setShowNewForm(false); setFormError(null); }}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="px-6 py-5 space-y-4">
              {formError && (
                <p className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2">
                  {formError}
                </p>
              )}

              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-mono">Project Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))}
                  placeholder="e.g. Greenfield Office Block — Block A"
                  className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-mono">Job Reference *</label>
                <input
                  type="text"
                  value={formData.reference}
                  onChange={(e) => setFormData((d) => ({ ...d, reference: e.target.value }))}
                  placeholder="e.g. JOB-2026-001"
                  className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-mono">Client</label>
                <input
                  type="text"
                  value={formData.client}
                  onChange={(e) => setFormData((d) => ({ ...d, client: e.target.value }))}
                  placeholder="e.g. Acme Property Developments Ltd"
                  className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-mono">Design Code</label>
                <div className="flex gap-2">
                  {DESIGN_CODES.map((code) => (
                    <button
                      key={code}
                      type="button"
                      onClick={() => setFormData((d) => ({ ...d, design_code: code }))}
                      className={`flex-1 py-2 rounded-md text-sm font-mono font-medium border transition-colors ${
                        formData.design_code === code
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                      }`}
                    >
                      {code}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => { setShowNewForm(false); setFormError(null); }}
                  className="flex-1 py-2 rounded-md text-sm border border-border text-muted-foreground hover:text-foreground transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
                >
                  {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

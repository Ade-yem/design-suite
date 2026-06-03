"use client";

import { useState, useEffect } from "react";
import { Plus, Folder, Loader2, FolderOpen, ChevronRight, Layers } from "lucide-react";
import { useProjectStore } from "@/stores/projectStore";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { apiClient } from "@/lib/api";
import { getPipelineStatus } from "@/lib/pipelineStatus";
import { NewProjectModal } from "./NewProjectModal";
import type { Project, ProjectListItem } from "@/types/project";

// ── Greeting ──────────────────────────────────────────────────────────────────

interface Greeting {
  heading: string;
  sub: string;
}

function staticGreeting(name: string | null, hasProjects: boolean): Greeting {
  const hour = new Date().getHours();
  const first = name?.split(" ")[0] ?? null;
  const suffix = first ? `, ${first}` : "";

  if (hour >= 5 && hour < 12) {
    return {
      heading: `Good morning${suffix}.`,
      sub: hasProjects ? "Here's what's on your board." : "Ready to start your first project?",
    };
  }
  if (hour >= 12 && hour < 17) {
    return {
      heading: `Good afternoon${suffix}.`,
      sub: hasProjects ? "Pick up where you left off." : "Start something new today.",
    };
  }
  if (hour >= 17 && hour < 21) {
    return {
      heading: `Good evening${suffix}.`,
      sub: hasProjects ? "Let's make some progress." : "A good time to start something new.",
    };
  }
  return {
    heading: first ? `Still at it, ${first}?` : "Working late?",
    sub: hasProjects ? "Your projects are ready." : "Start a new project below.",
  };
}

function useGreeting(projectCount: number): { greeting: Greeting | null; loading: boolean } {
  const { user } = useAuthStore();
  const [greeting, setGreeting] = useState<Greeting | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const localHour = new Date().getHours();
    const params: Record<string, string | number> = {
      local_hour: localHour,
      project_count: projectCount,
    };
    if (user?.full_name) params.user_name = user.full_name;

    apiClient
      .get<Greeting>("/api/v1/greeting", { params })
      .then(({ data }) => {
        if (!cancelled) setGreeting(data);
      })
      .catch(() => {
        if (!cancelled)
          setGreeting(staticGreeting(user?.full_name ?? null, projectCount > 0));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { greeting, loading };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function statusMeta(status: string): { label: string; dot: string } {
  const meta = getPipelineStatus(status);
  return { label: meta.label, dot: meta.dotClass };
}

// ── Project card ──────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  openingId,
  onOpen,
}: {
  project: ProjectListItem;
  openingId: string | null;
  onOpen: (id: string) => void;
}) {
  const { label, dot } = statusMeta(project.pipeline_status);
  const isOpening = openingId === project.project_id;

  return (
    <button
      onClick={() => onOpen(project.project_id)}
      disabled={!!openingId}
      className="group w-full flex items-center gap-4 px-4 py-3.5 rounded-xl bg-card border border-border hover:border-border/80 hover:bg-card/60 transition-all text-left disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      {/* Icon */}
      <div className="shrink-0 h-9 w-9 rounded-lg bg-muted flex items-center justify-center group-hover:bg-muted/60 transition-colors">
        {isOpening ? (
          <Loader2 className="h-4 w-4 text-primary animate-spin" />
        ) : (
          <Folder className="h-4 w-4 text-muted-foreground" />
        )}
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate leading-snug">{project.name}</p>
        <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate">{project.reference}</p>
      </div>

      {/* Status + time */}
      <div className="shrink-0 flex flex-col items-end gap-1">
        <span className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
          <span className="text-xs text-muted-foreground">{label}</span>
        </span>
        <span className="text-[10px] text-muted-foreground/60 font-mono">
          {relativeTime(project.updated_at)}
        </span>
      </div>

      <ChevronRight className="shrink-0 h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
    </button>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-6 text-center">
      <div className="relative">
        <div className="h-20 w-20 rounded-2xl border border-border bg-card flex items-center justify-center">
          <Layers className="h-9 w-9 text-muted-foreground/30" />
        </div>
        <div className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-primary flex items-center justify-center shadow-md">
          <Plus className="h-3.5 w-3.5 text-primary-foreground" />
        </div>
      </div>

      <div className="space-y-1.5 max-w-xs">
        <p className="text-sm font-medium">No projects yet</p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Create your first project and upload a DXF or PDF drawing to begin structural analysis.
        </p>
      </div>

      <button
        onClick={onNew}
        className="flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors"
      >
        <Plus className="h-4 w-4" />
        New Project
      </button>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProjectPrompt() {
  const { projects, setActiveProject } = useProjectStore();
  const { setSidebarExpanded } = useUIStore();
  const [showModal, setShowModal] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const { greeting, loading: greetingLoading } = useGreeting(projects.length);

  const handleOpenProject = async (projectId: string) => {
    if (openingId) return;
    setOpeningId(projectId);
    try {
      const { data } = await apiClient.get<Project>(`/api/v1/projects/${projectId}`);
      setActiveProject(data);
      setSidebarExpanded(false);
    } catch {
      // silently ignore
    } finally {
      setOpeningId(null);
    }
  };

  const handleCreated = (project: Project) => {
    setActiveProject(project);
    setSidebarExpanded(false);
    setShowModal(false);
  };

  return (
    <div className="flex-1 bg-background flex flex-col overflow-hidden">

      {/* ── Greeting + action header ── */}
      <div className="px-10 pt-12 pb-6 shrink-0 flex items-end justify-between">
        <div className="min-h-14">
          {greetingLoading ? (
            <div className="space-y-2.5 animate-pulse">
              <div className="h-7 w-52 bg-muted rounded-lg" />
              <div className="h-4 w-72 bg-muted/50 rounded-md" />
            </div>
          ) : greeting ? (
            <div className="animate-fade-in-up">
              <h1 className="text-2xl font-semibold tracking-tight leading-tight">
                {greeting.heading}
              </h1>
              <p className="text-sm text-muted-foreground mt-1.5">{greeting.sub}</p>
            </div>
          ) : null}
        </div>

        {/* New project button — always visible in header */}
        <button
          onClick={() => setShowModal(true)}
          className="shrink-0 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors ml-8"
        >
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* ── Divider ── */}
      <div className="mx-10 border-t border-border shrink-0" />

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-10 py-8">
        <div className="max-w-2xl">

          {projects.length > 0 ? (
            <div className="space-y-3">
              {/* Section label + count */}
              <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  Projects
                </span>
                <span className="text-[10px] font-mono text-muted-foreground/60">
                  {projects.length} total
                </span>
              </div>

              <ul className="space-y-1.5">
                {projects.map((p) => (
                  <li key={p.project_id}>
                    <ProjectCard
                      project={p}
                      openingId={openingId}
                      onOpen={handleOpenProject}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <EmptyState onNew={() => setShowModal(true)} />
          )}
        </div>
      </div>

      {showModal && (
        <NewProjectModal onClose={() => setShowModal(false)} onCreated={handleCreated} />
      )}
    </div>
  );
}

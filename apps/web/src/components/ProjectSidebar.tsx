"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import {
  Hexagon,
  ChevronLeft,
  Search,
  Folder,
  FolderOpen,
  Plus,
  LogOut,
  User,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/stores/projectStore";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { apiClient } from "@/lib/api";
import { NewProjectModal } from "./NewProjectModal";
import type { Project } from "@/types/project";

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function statusColor(status: string): string {
  if (status === "created") return "text-muted-foreground";
  if (status === "report_generated") return "text-success";
  return "text-primary";
}

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

interface SidebarTooltipProps {
  label: string;
  children: React.ReactNode;
}

function SidebarTooltip({ label, children }: SidebarTooltipProps) {
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  const handleMouseEnter = () => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      // Position the tooltip 10px to the right of the trigger button, vertically centered
      setCoords({
        x: rect.right + 10,
        y: rect.top + rect.height / 2,
      });
    }
  };

  const handleMouseLeave = () => {
    setCoords(null);
  };

  return (
    <div
      ref={triggerRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className="relative flex items-center justify-center w-full"
    >
      {children}
      {mounted &&
        coords &&
        createPortal(
          <div
            style={{
              position: "fixed",
              left: coords.x,
              top: coords.y,
              transform: "translateY(-50%)",
            }}
            className="z-9999 pointer-events-none bg-popover border border-border text-popover-foreground text-xs px-2.5 py-1.5 rounded-md whitespace-nowrap shadow-lg font-sans animate-fade-in-right"
          >
            {label}
          </div>,
          document.body,
        )}
    </div>
  );
}

export function ProjectSidebar() {
  const router = useRouter();
  const {
    projects,
    activeProject,
    setActiveProject,
    fetchProjects,
    isLoading,
  } = useProjectStore();
  const { user, clearAuth } = useAuthStore();
  const { sidebarExpanded, setSidebarExpanded, toggleSidebar } = useUIStore();

  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    if (sidebarExpanded && search) {
      searchRef.current?.focus();
    }
  }, [sidebarExpanded, search]);

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.reference.toLowerCase().includes(search.toLowerCase()),
  );

  const handleOpenProject = async (projectId: string) => {
    if (openingId) return;
    setOpeningId(projectId);
    try {
      const { data } = await apiClient.get<Project>(
        `/api/v1/projects/${projectId}`,
      );
      setActiveProject(data);
      setSidebarExpanded(false);
      router.push("/");
    } catch {
      router.push("/");
    } finally {
      setOpeningId(null);
    }
  };

  const handleCreated = (project: Project) => {
    setActiveProject(project);
    setSidebarExpanded(false);
    setShowModal(false);
    router.push("/");
  };

  const handleSignOut = () => {
    clearAuth();
    router.push("/login");
  };

  const handleExpandAndSearch = () => {
    setSidebarExpanded(true);
    setTimeout(() => searchRef.current?.focus(), 210);
  };

  return (
    <>
      <aside
        className={cn(
          "h-full flex flex-col bg-card border-r border-border shrink-0 overflow-hidden",
          "transition-[width] duration-200 ease-out",
          sidebarExpanded ? "w-60" : "w-12",
        )}
      >
        {/* Logo + collapse toggle */}
        <div
          className={cn(
            "h-12 flex items-center border-b border-border shrink-0",
            sidebarExpanded ? "px-4 gap-2 justify-between" : "justify-center",
          )}
        >
          {sidebarExpanded ? (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <Hexagon className="h-5 w-5 text-primary shrink-0" />
                <span className="text-sm font-semibold tracking-tight whitespace-nowrap">
                  StructAI
                </span>
                <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
                  Copilot
                </span>
              </div>
              <button
                onClick={() => setSidebarExpanded(false)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
                aria-label="Collapse sidebar"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
            </>
          ) : (
            <SidebarTooltip label="Expand sidebar">
              <button
                onClick={() => setSidebarExpanded(true)}
                className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Expand sidebar"
              >
                <Hexagon className="h-5 w-5 text-primary" />
              </button>
            </SidebarTooltip>
          )}
        </div>

        {/* Search */}
        <div
          className={cn(
            "py-2 border-b border-border shrink-0",
            sidebarExpanded ? "px-2" : "flex justify-center px-0",
          )}
        >
          {sidebarExpanded ? (
            <div className="flex items-center gap-2 bg-muted rounded-md px-2.5 py-1.5">
              <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search projects..."
                role="searchbox"
                aria-label="Search projects"
                className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground min-w-0"
              />
            </div>
          ) : (
            <SidebarTooltip label="Search projects (⌘K)">
              <button
                onClick={handleExpandAndSearch}
                className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Search projects"
              >
                <Search className="h-3.5 w-3.5" />
              </button>
            </SidebarTooltip>
          )}
        </div>

        {/* Project list */}
        <div
          className={cn(
            "py-2 border-b border-border shrink-0",
            sidebarExpanded ? "px-2" : "flex justify-center px-0",
          )}
        >
          {sidebarExpanded ? (
            <div className="flex-1 overflow-y-auto scrollbar-thin py-2 min-h-0">
              <p className="px-4 pb-1 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                Projects
              </p>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-5 w-5 text-primary animate-spin" />
                </div>
              ) : (
                <ul
                  className={cn(
                    "space-y-px",
                    sidebarExpanded
                      ? "px-2 flex-1 min-h-0 flex flex-col"
                      : "px-1.5",
                  )}
                >
                  {filtered.length === 0 && sidebarExpanded && (
                    <li className="px-2 py-4 text-xs text-muted-foreground text-center font-mono">
                      {search ? "No matches" : "No projects yet"}
                    </li>
                  )}

                  {filtered.map((p) => {
                    const isActive = activeProject?.project_id === p.project_id;
                    const isOpening = openingId === p.project_id;

                    return (
                      <li key={p.project_id}>
                        {sidebarExpanded ? (
                          <button
                            onClick={() => handleOpenProject(p.project_id)}
                            disabled={!!openingId}
                            className={cn(
                              "w-full flex items-center gap-2 py-2 rounded-md text-left transition-colors group disabled:opacity-60",
                              isActive
                                ? "bg-primary/10 border-l-2 border-primary text-foreground pl-1.5 pr-2"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground px-2",
                            )}
                          >
                            {isOpening ? (
                              <Loader2 className="h-4 w-4 text-primary shrink-0 animate-spin" />
                            ) : isActive ? (
                              <FolderOpen className="h-4 w-4 text-primary shrink-0" />
                            ) : (
                              <Folder className="h-4 w-4 shrink-0 group-hover:text-primary transition-colors" />
                            )}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate leading-tight">
                                {p.name}
                              </p>
                              <p className="text-[10px] font-mono text-muted-foreground truncate">
                                {p.reference}
                              </p>
                            </div>
                            <span
                              className={cn(
                                "text-[10px] font-mono capitalize shrink-0 hidden group-hover:hidden",
                                statusColor(p.pipeline_status),
                              )}
                            >
                              {statusLabel(p.pipeline_status)}
                            </span>
                          </button>
                        ) : (
                          <SidebarTooltip label={p.name}>
                            <button
                              onClick={() => handleOpenProject(p.project_id)}
                              disabled={!!openingId}
                              className={cn(
                                "w-full flex items-center justify-center p-2 rounded-md transition-colors disabled:opacity-60",
                                isActive
                                  ? "bg-primary/10 text-primary"
                                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
                              )}
                              aria-label={p.name}
                            >
                              {isOpening ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : isActive ? (
                                <FolderOpen className="h-4 w-4" />
                              ) : (
                                <Folder className="h-4 w-4" />
                              )}
                            </button>
                          </SidebarTooltip>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : (
            <SidebarTooltip label="Open projects (⌘I)">
              <button
                onClick={() => setSidebarExpanded(true)}
                className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Open projects"
              >
                <Folder className="h-3.5 w-3.5" />
              </button>
            </SidebarTooltip>
          )}
        </div>

        {/* New project */}
        <div
          className={cn(
            "py-2 border-t border-border shrink-0",
            sidebarExpanded ? "px-2" : "flex justify-center",
          )}
        >
          {sidebarExpanded ? (
            <button
              onClick={() => setShowModal(true)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <Plus className="h-3.5 w-3.5 shrink-0" />
              New Project
            </button>
          ) : (
            <SidebarTooltip label="New Project (⌘N)">
              <button
                onClick={() => setShowModal(true)}
                className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="New Project"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </SidebarTooltip>
          )}
        </div>

        {/* Profile + sign out */}
        <div
          className={cn(
            "py-2 border-t border-border shrink-0 mt-auto",
            sidebarExpanded
              ? "px-2 space-y-0.5"
              : "flex flex-col items-center gap-0.5",
          )}
        >
          {sidebarExpanded ? (
            <>
              <button
                onClick={() => router.push("/profile")}
                className="w-full flex items-center gap-2.5 px-2 py-2 rounded-md hover:bg-muted transition-colors group"
              >
                <div className="h-6 w-6 rounded-md bg-primary flex items-center justify-center shrink-0">
                  <span className="text-[10px] font-semibold text-primary-foreground">
                    {getInitials(user?.full_name ?? null)}
                  </span>
                </div>
                <span className="flex-1 text-xs font-medium truncate text-muted-foreground group-hover:text-foreground transition-colors">
                  {user?.full_name ?? user?.email ?? "Profile"}
                </span>
                <User className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-2.5 px-2 py-2 rounded-md text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5 shrink-0" />
                Sign out
              </button>
            </>
          ) : (
            <>
              <SidebarTooltip label={user?.full_name ?? "Profile"}>
                <button
                  onClick={() => router.push("/profile")}
                  className="p-1.5 rounded-md hover:bg-muted transition-colors"
                  aria-label="Profile"
                >
                  <div className="h-6 w-6 rounded-md bg-primary flex items-center justify-center">
                    <span className="text-[10px] font-semibold text-primary-foreground">
                      {getInitials(user?.full_name ?? null)}
                    </span>
                  </div>
                </button>
              </SidebarTooltip>
              <SidebarTooltip label="Sign out">
                <button
                  onClick={handleSignOut}
                  className="p-2 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  aria-label="Sign out"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </SidebarTooltip>
            </>
          )}
        </div>
      </aside>

      {showModal && (
        <NewProjectModal
          onClose={() => setShowModal(false)}
          onCreated={handleCreated}
        />
      )}
    </>
  );
}

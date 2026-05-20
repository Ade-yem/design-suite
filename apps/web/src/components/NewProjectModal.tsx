"use client";

import { useState } from "react";
import { X, Loader2 } from "lucide-react";
import { useProjectStore } from "@/stores/projectStore";
import type { CreateProjectPayload, Project } from "@/types/project";

const DESIGN_CODES = ["BS8110", "EC2"] as const;

interface NewProjectModalProps {
  onClose: () => void;
  onCreated: (project: Project) => void;
  initialName?: string;
}

export function NewProjectModal({ onClose, onCreated, initialName = "" }: NewProjectModalProps) {
  const { createProject } = useProjectStore();
  const [formData, setFormData] = useState<CreateProjectPayload>({
    name: initialName,
    reference: "",
    client: "",
    design_code: "BS8110",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError("Project name is required.");
      return;
    }
    if (!formData.reference.trim()) {
      setFormError("Job reference is required.");
      return;
    }
    setFormError(null);
    setCreating(true);
    try {
      const project = await createProject(formData);
      onCreated(project);
    } catch (err: unknown) {
      setFormError((err as { detail?: string }).detail ?? "Failed to create project.");
      setCreating(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card border border-border rounded-xl w-full max-w-md shadow-xl animate-fade-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-sm font-semibold">New Project</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Close"
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
              onClick={onClose}
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
  );
}

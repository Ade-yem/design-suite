/**
 * @file pipelineStatus.ts
 * @description Single source of truth for the pipeline's status vocabulary.
 *
 * The backend exposes seven pipeline statuses (see apps/api/schemas/project.py).
 * Historically each surface — the dashboard cards, the sidebar list, and the
 * header stage tracker — described those statuses with its own labels, colours,
 * and stage groupings, so the same project read three different ways. This module
 * defines each status once: a friendly label, the coarse pipeline stage it belongs
 * to, an ordinal for ordering, and the colour classes used to render it. Every
 * surface consumes this map.
 */

/** Coarse pipeline stages shown in the header tracker. */
export type Stage = "parsing" | "verification" | "calculation" | "drafting";

export interface PipelineStatusMeta {
  /** Friendly, human-facing label. */
  label: string;
  /** The coarse stage this status rolls up into. */
  stage: Stage;
  /** Ordering position across the full pipeline (0–6). */
  ordinal: number;
  /** Tailwind background class for a status dot. */
  dotClass: string;
  /** Tailwind text-colour class for an inline status label. */
  textClass: string;
}

/**
 * The full status map, keyed by the backend `pipeline_status` string.
 *
 * NOTE: dot colours intentionally keep the existing raw Tailwind palette for now;
 * promoting them to semantic design tokens is a separate (later) token-discipline
 * pass. The win here is that the values live in exactly one place.
 */
export const PIPELINE_STATUS: Record<string, PipelineStatusMeta> = {
  created: {
    label: "Created",
    stage: "parsing",
    ordinal: 0,
    dotClass: "bg-muted-foreground",
    textClass: "text-muted-foreground",
  },
  file_uploaded: {
    label: "File uploaded",
    stage: "parsing",
    ordinal: 1,
    dotClass: "bg-blue-400",
    textClass: "text-primary",
  },
  geometry_verified: {
    label: "Geometry OK",
    stage: "verification",
    ordinal: 2,
    dotClass: "bg-blue-500",
    textClass: "text-primary",
  },
  loading_defined: {
    label: "Loads defined",
    stage: "calculation",
    ordinal: 3,
    dotClass: "bg-violet-500",
    textClass: "text-primary",
  },
  analysis_complete: {
    label: "Analysis done",
    stage: "calculation",
    ordinal: 4,
    dotClass: "bg-amber-500",
    textClass: "text-primary",
  },
  design_complete: {
    label: "Design complete",
    stage: "drafting",
    ordinal: 5,
    dotClass: "bg-orange-500",
    textClass: "text-primary",
  },
  report_generated: {
    label: "Report ready",
    stage: "drafting",
    ordinal: 6,
    dotClass: "bg-green-500",
    textClass: "text-success",
  },
};

/** Fallback for an unrecognised status string. */
function fallback(status: string): PipelineStatusMeta {
  return {
    label: status.replace(/_/g, " "),
    stage: "parsing",
    ordinal: 0,
    dotClass: "bg-muted-foreground",
    textClass: "text-muted-foreground",
  };
}

/** Look up the metadata for a pipeline status, with a safe fallback. */
export function getPipelineStatus(status: string): PipelineStatusMeta {
  return PIPELINE_STATUS[status] ?? fallback(status);
}

/** Map a backend pipeline status to its coarse header stage. */
export function pipelineStatusToStage(status: string): Stage {
  return getPipelineStatus(status).stage;
}

/**
 * Human-facing description of each safety gate, shared by the pipeline rail
 * (which hosts the approval) and the chat (which points the engineer to it).
 */
export const GATE_LABELS: Record<string, string> = {
  geometry_gate: "Confirm parsed geometry to proceed to loading",
  loading_gate: "Confirm load combinations to proceed to analysis",
  design_gate: "Confirm reinforcement schedule to proceed to drafting",
  drawing_gate: "Confirm final drawing set",
};

/** The coarse stage that owns each safety gate's approval. */
export const GATE_STAGE: Record<string, Stage> = {
  geometry_gate: "verification",
  loading_gate: "calculation",
  design_gate: "drafting",
  drawing_gate: "drafting",
};

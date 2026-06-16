"use client";

/**
 * @file RebarTab.tsx
 * @description Reinforcement / design results for the selected member, from
 * GET /api/v1/design/{project_id}/results. Shows required vs provided steel
 * area, bar descriptions, shear links, and the deflection check. Degrades to
 * an empty state when design has not yet been run for the project.
 */

import React, { useState } from "react";
import { CheckCircle2, XCircle, Pencil } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { useProjectStore } from "@/stores/projectStore";
import { useAnalysisStore } from "@/stores/analysisStore";
import type { DesignMemberResult, ShearLinkSpec } from "@/types/analysis";

/** Standard reinforcement bar diameters (mm). */
const BAR_DIAMETERS = [12, 16, 20, 25, 32, 40];

/**
 * Inline editor for overriding a member's reinforcement / section, then
 * re-running the design via PUT /api/v1/design/{project_id}/member/{member_id}.
 */
function RebarEditor({ memberId }: { memberId: string }) {
  const projectId = useProjectStore((s) => s.activeProject?.project_id);
  const fetchDesign = useAnalysisStore((s) => s.fetchDesign);
  const [open, setOpen] = useState(false);
  const [barDia, setBarDia] = useState<number>(20);
  const [depth, setDepth] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const apply = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      const { data } = await apiClient.put(
        `/api/v1/design/${projectId}/member/${memberId}`,
        {
          meta_updates: { bar_dia_mm: barDia },
          h_mm: depth ? Number(depth) : undefined,
          reason: `Rebar override: ${barDia}mm bars` + (depth ? `, h=${depth}mm` : ""),
        }
      );
      // Refresh design results so every tab reflects the recompute.
      await fetchDesign(projectId);
      // Best-effort drawing refresh; ignore if drawings are not generated yet.
      apiClient
        .post(`/api/v1/drawings/${projectId}/member/${memberId}/regenerate`)
        .catch(() => undefined);

      const status = data?.result?.status;
      if (status && status !== "OK" && status !== "pass") {
        toast.warning(`Design re-checked: ${status}. Review the updated result.`);
      } else {
        toast.success("Reinforcement updated and re-checked.");
      }
      if (data?.warning) toast.warning(data.warning);
      setOpen(false);
    } catch {
      toast.error("Could not apply the reinforcement override.");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        disabled={!projectId}
        className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border border-border/50 text-foreground/80 hover:bg-muted/40 transition-colors disabled:opacity-50"
      >
        <Pencil className="w-3 h-3" />
        Edit reinforcement
      </button>
    );
  }

  return (
    <div className="border border-border/50 rounded-md p-2.5 bg-muted/20 space-y-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        Override &amp; re-check
      </div>
      <label className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted-foreground">Main bar ⌀ (mm)</span>
        <select
          value={barDia}
          onChange={(e) => setBarDia(Number(e.target.value))}
          className="bg-background border border-border/60 rounded px-2 py-1 font-mono"
        >
          {BAR_DIAMETERS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted-foreground">Section depth h (mm)</span>
        <input
          type="number"
          value={depth}
          placeholder="unchanged"
          onChange={(e) => setDepth(e.target.value)}
          className="w-24 bg-background border border-border/60 rounded px-2 py-1 font-mono"
        />
      </label>
      <div className="flex items-center gap-1.5 pt-1">
        <button
          onClick={apply}
          disabled={saving}
          className="flex-1 text-xs px-2.5 py-1 rounded bg-primary text-primary-foreground hover:opacity-90 transition disabled:opacity-50"
        >
          {saving ? "Applying…" : "Apply & re-check"}
        </button>
        <button
          onClick={() => setOpen(false)}
          disabled={saving}
          className="text-xs px-2.5 py-1 rounded border border-border/50 hover:bg-muted/40 transition"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function AreaRow({
  label,
  req,
  prov,
  desc,
}: {
  label: string;
  req?: number;
  prov?: number;
  desc?: string;
}) {
  if (req == null && prov == null && !desc) return null;
  const adequate = req != null && prov != null ? prov >= req : true;
  return (
    <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
        {label}
      </div>
      <div className="flex items-center justify-between font-mono text-xs">
        <span className="text-muted-foreground">
          req {req != null ? `${req.toFixed(0)} mm²` : "—"}
        </span>
        <span
          className={adequate ? "text-status-done" : "text-destructive"}
        >
          prov {prov != null ? `${prov.toFixed(0)} mm²` : "—"}
        </span>
      </div>
      {desc && <div className="text-xs text-foreground mt-1.5">{desc}</div>}
    </div>
  );
}

function isShearLinkSpec(
  v: DesignMemberResult["shear_links"]
): v is ShearLinkSpec {
  return typeof v === "object" && v !== null && "diameter_mm" in v;
}

export function RebarTab({
  design,
  memberId,
}: {
  design: DesignMemberResult | null;
  memberId?: string | null;
}) {
  if (!design) {
    return (
      <div className="p-4 text-center">
        <p className="text-xs text-muted-foreground italic">
          Reinforcement design has not been run for this member yet.
        </p>
        <p className="text-[10px] text-muted-foreground mt-1">
          Approve the analysis gate to proceed to the design phase.
        </p>
      </div>
    );
  }

  const dc = design.deflection_check;
  const links = design.shear_links;

  return (
    <div className="space-y-3">
      {/* Status banner */}
      <div
        className={`flex items-center gap-2 rounded-md p-2.5 text-xs font-medium ${
          design.status === "pass"
            ? "bg-status-done/10 text-status-done"
            : "bg-destructive/10 text-destructive"
        }`}
      >
        {design.status === "pass" ? (
          <CheckCircle2 className="w-4 h-4" />
        ) : (
          <XCircle className="w-4 h-4" />
        )}
        {design.status === "pass"
          ? "Section adequate — all checks pass"
          : "Section inadequate — review required"}
        {design.utilization_ratio != null && (
          <span className="ml-auto font-mono">
            util {design.utilization_ratio.toFixed(2)}
          </span>
        )}
      </div>

      {/* Tension / compression steel */}
      <AreaRow
        label="Tension reinforcement"
        req={design.As_req}
        prov={design.As_prov}
        desc={design.reinforcement_description}
      />
      <AreaRow
        label="Compression reinforcement"
        req={design.As_prime_req}
        prov={design.As_prime_prov}
        desc={design.compression_reinforcement_description}
      />

      {/* Shear links */}
      {links && (
        <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Shear links
          </div>
          <div className="text-xs text-foreground font-mono">
            {isShearLinkSpec(links)
              ? `${links.legs}-leg ⌀${links.diameter_mm} @ ${links.spacing_mm} mm c/c`
              : links}
          </div>
          {isShearLinkSpec(links) && links.description && (
            <div className="text-[10px] text-muted-foreground mt-1">
              {links.description}
            </div>
          )}
        </div>
      )}

      {/* Deflection check */}
      {dc && (
        <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Deflection check
          </div>
          <div className="flex items-center justify-between font-mono text-xs">
            <span>
              actual {dc.actual_mm.toFixed(1)} mm / limit{" "}
              {dc.limit_mm.toFixed(1)} mm
            </span>
            <span
              className={
                dc.status === "pass" ? "text-status-done" : "text-destructive"
              }
            >
              {dc.status.toUpperCase()}
            </span>
          </div>
        </div>
      )}

      {/* Warnings */}
      {design.warnings && design.warnings.length > 0 && (
        <div className="space-y-1">
          {design.warnings.map((w, i) => (
            <div
              key={i}
              className="text-[11px] text-status-in-progress bg-status-in-progress/10 rounded p-2"
            >
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Reinforcement override + re-check */}
      {memberId && (
        <div className="pt-1">
          <RebarEditor memberId={memberId} />
        </div>
      )}
    </div>
  );
}

"use client";

/**
 * @file RebarTab.tsx
 * @description Reinforcement / design results for the selected member, from
 * GET /api/v1/design/{project_id}/results. Shows required vs provided steel
 * area, bar descriptions, shear links, and the deflection check. Degrades to
 * an empty state when design has not yet been run for the project.
 */

import React from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import type { DesignMemberResult, ShearLinkSpec } from "@/types/analysis";

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

export function RebarTab({ design }: { design: DesignMemberResult | null }) {
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
    </div>
  );
}

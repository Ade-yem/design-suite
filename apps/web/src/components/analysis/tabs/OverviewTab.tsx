"use client";

/**
 * @file OverviewTab.tsx
 * @description Summary of the key analysis results for the selected member:
 * peak stress resultants, analysis method, governing pattern, SLS status,
 * and any warnings/flags raised by the solver.
 */

import React from "react";
import { AlertTriangle, Flag } from "lucide-react";
import type {
  MemberFullAnalysisResult,
  DesignMemberResult,
} from "@/types/analysis";

interface MetricProps {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "fail";
}

function Metric({ label, value, sub, tone = "default" }: MetricProps) {
  return (
    <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={`font-mono text-sm font-semibold ${
          tone === "fail" ? "text-destructive" : "text-foreground"
        }`}
      >
        {value}
      </div>
      {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

export function OverviewTab({
  analysis,
  design,
}: {
  analysis: MemberFullAnalysisResult | null;
  design: DesignMemberResult | null;
}) {
  if (!analysis) {
    return (
      <p className="text-xs text-muted-foreground italic p-4">
        No analysis result available for this member.
      </p>
    );
  }

  const sr = analysis.stress_resultants;
  const sls = analysis.SLS_checks;

  return (
    <div className="space-y-4">
      {/* Key result grid */}
      <div className="grid grid-cols-2 gap-2">
        <Metric
          label="M sagging"
          value={`${sr.M_max_sagging_kNm.toFixed(1)} kNm`}
        />
        <Metric
          label="M hogging"
          value={`${sr.M_max_hogging_kNm.toFixed(1)} kNm`}
        />
        <Metric label="Shear V" value={`${sr.V_max_kN.toFixed(1)} kN`} />
        <Metric label="Axial N" value={`${sr.N_axial_kN.toFixed(1)} kN`} />
        <Metric
          label="Max deflection"
          value={`${sr.deflection_max_mm.toFixed(1)} mm`}
          sub={sls ? `limit ${sls.deflection_limit_mm.toFixed(1)} mm` : undefined}
          tone={sls?.status === "fail" ? "fail" : "default"}
        />
        <Metric
          label="Method"
          value={analysis.analysis_method.replace(/_/g, " ")}
          sub={analysis.governing_pattern ?? undefined}
        />
      </div>

      {/* Reactions */}
      {analysis.reactions_kN?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Support reactions
          </div>
          <div className="flex flex-wrap gap-2">
            {analysis.reactions_kN.map((r, i) => (
              <span
                key={i}
                className="font-mono text-xs px-2 py-1 rounded bg-muted/40 border border-border/40"
              >
                R{i + 1} = {r.toFixed(1)} kN
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Design summary line, if available */}
      {design && (
        <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Design outcome
          </div>
          <div className="text-xs text-foreground">
            {design.reinforcement_description ??
              (design.status === "pass" ? "Section adequate" : "Review required")}
          </div>
        </div>
      )}

      {/* Warnings */}
      {analysis.warnings?.length > 0 && (
        <div className="space-y-1">
          {analysis.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-xs text-status-in-progress bg-status-in-progress/10 rounded p-2"
            >
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Flags */}
      {analysis.flags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {analysis.flags.map((f, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-muted/50 border border-border/40 text-muted-foreground"
            >
              <Flag className="w-2.5 h-2.5" />
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

/**
 * @file LoadsTab.tsx
 * @description Shows the loads acting on the selected member: the governing
 * load combination, per-support reactions (ULS), and any loading context the
 * analysis result exposes (governing pattern, flags). The analysis envelope
 * does not always carry the full load-combination breakdown, so this tab
 * degrades gracefully to the data that is present.
 */

import React from "react";
import { Layers } from "lucide-react";
import type { MemberFullAnalysisResult } from "@/types/analysis";

export function LoadsTab({
  analysis,
  spanM,
}: {
  analysis: MemberFullAnalysisResult | null;
  spanM: number;
}) {
  if (!analysis) {
    return (
      <p className="text-xs text-muted-foreground italic p-4">
        No load data available for this member.
      </p>
    );
  }

  const sr = analysis.stress_resultants;
  const reactions = analysis.reactions_kN ?? [];
  const totalReaction = reactions.reduce((a, b) => a + Math.abs(b), 0);

  // Back-calculate an equivalent UDL from total reaction over the span,
  // as an indicative applied line load (w ≈ ΣR / L).
  const equivalentUdl = spanM > 0 ? totalReaction / spanM : 0;

  return (
    <div className="space-y-4">
      {/* Governing combination */}
      <div className="border border-border/50 rounded-md p-3 bg-muted/20">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Governing load case
        </div>
        <div className="font-mono text-sm text-foreground">
          {analysis.governing_pattern ?? "1.4 Gk + 1.6 Qk"}
        </div>
        <div className="text-[10px] text-muted-foreground mt-1">
          ULS combination · span {spanM.toFixed(2)} m
        </div>
      </div>

      {/* Equivalent applied load */}
      <div className="grid grid-cols-2 gap-2">
        <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Equiv. line load
          </div>
          <div className="font-mono text-sm font-semibold text-foreground">
            {equivalentUdl.toFixed(1)} kN/m
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            ΣR / span (indicative)
          </div>
        </div>
        <div className="border border-border/50 rounded-md p-2.5 bg-muted/20">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Total applied
          </div>
          <div className="font-mono text-sm font-semibold text-foreground">
            {totalReaction.toFixed(1)} kN
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            sum of reactions
          </div>
        </div>
      </div>

      {/* Reaction table */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
          Support reactions
        </div>
        <div className="rounded-md border border-border/50 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-muted/40 text-muted-foreground">
                <th className="text-left font-medium px-3 py-1.5">Support</th>
                <th className="text-right font-medium px-3 py-1.5">
                  Reaction (kN)
                </th>
              </tr>
            </thead>
            <tbody>
              {reactions.length === 0 ? (
                <tr>
                  <td
                    colSpan={2}
                    className="px-3 py-2 text-muted-foreground italic"
                  >
                    No reactions reported.
                  </td>
                </tr>
              ) : (
                reactions.map((r, i) => (
                  <tr key={i} className="border-t border-border/40">
                    <td className="px-3 py-1.5 font-mono">R{i + 1}</td>
                    <td className="px-3 py-1.5 font-mono text-right">
                      {r.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Resulting peak effects */}
      <div className="border border-border/50 rounded-md p-3 bg-muted/20">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
          <Layers className="w-3 h-3" />
          Resulting peak effects
        </div>
        <div className="grid grid-cols-3 gap-2 font-mono text-xs">
          <div>
            <span className="text-muted-foreground">M</span>{" "}
            {sr.M_max_sagging_kNm.toFixed(1)} kNm
          </div>
          <div>
            <span className="text-muted-foreground">V</span>{" "}
            {sr.V_max_kN.toFixed(1)} kN
          </div>
          <div>
            <span className="text-muted-foreground">δ</span>{" "}
            {sr.deflection_max_mm.toFixed(1)} mm
          </div>
        </div>
      </div>
    </div>
  );
}

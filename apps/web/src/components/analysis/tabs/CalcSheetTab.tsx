"use client";

/**
 * @file CalcSheetTab.tsx
 * @description Renders the member's full calculation audit trail
 * (`calculation_trace`) as an engineering calc sheet — one block per step with
 * its description, formula, input variables, result, and code clause. Provides
 * a "Download Sheet" action that exports a self-contained, print-friendly HTML
 * document of the trace.
 */

import React, { useCallback, useState } from "react";
import { Download, FileText, FileDown } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { downloadFromApi } from "@/lib/download";
import { useProjectStore } from "@/stores/projectStore";
import type {
  CalculationTraceStep,
  MemberFullAnalysisResult,
  DesignMemberResult,
} from "@/types/analysis";

/**
 * Formats a raw calculation value (primitive, array, or object) into a human-readable string.
 * Handles floats by rounding to 3 decimal places and formats structured objects/arrays cleanly.
 *
 * @param v - The raw value to format.
 * @returns The formatted string representation of the value.
 */
function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "boolean") return v ? "true" : "false";
  
  if (Array.isArray(v)) {
    return `[${v.map(formatValue).join(", ")}]`;
  }
  
  if (typeof v === "object") {
    return Object.entries(v)
      .map(([key, val]) => `${key}: ${formatValue(val)}`)
      .join(", ");
  }
  
  return String(v);
}

/**
 * Renders a single calculation trace step inside a styled container.
 * Handles rendering of step numbers, clause references, formulas, input values, and results.
 * For object results, it renders them as a list of styled inline key-value tags.
 *
 * @param props - Component properties.
 * @param props.step - The calculation step to render.
 * @returns A React component representing the calculation step.
 */
function StepBlock({ step }: { step: CalculationTraceStep }) {
  const isObjectResult =
    step.result !== null &&
    typeof step.result === "object" &&
    !Array.isArray(step.result);

  return (
    <div className="border border-border/50 rounded-md overflow-hidden">
      <div className="flex items-start gap-2 px-3 py-2 bg-muted/30 border-b border-border/40">
        <span className="font-mono text-[10px] font-bold text-primary mt-0.5">
          {String(step.step).padStart(2, "0")}
        </span>
        <span className="text-xs font-medium text-foreground flex-1">
          {step.description}
        </span>
        {step.clause && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
            {step.clause}
          </span>
        )}
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {step.formula && (
          <div className="font-mono text-[11px] text-foreground/90 bg-muted/20 rounded px-2 py-1">
            {step.formula}
          </div>
        )}
        {step.inputs && Object.keys(step.inputs).length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-0.5">
            {Object.entries(step.inputs).map(([k, v]) => (
              <span key={k} className="font-mono text-[10px] text-muted-foreground">
                {k} = {formatValue(v)}
              </span>
            ))}
          </div>
        )}
        <div className="font-mono text-xs flex items-baseline gap-1.5">
          <span className="text-muted-foreground">⇒ </span>
          {isObjectResult ? (
            <div className="flex flex-wrap gap-x-2 gap-y-1">
              {Object.entries(step.result as Record<string, unknown>).map(([key, val]) => (
                <span
                  key={key}
                  className="px-1.5 py-0.5 rounded bg-primary/5 border border-primary/10 text-primary font-semibold text-[11px]"
                >
                  {key} = {formatValue(val)}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-foreground font-semibold">
              {formatValue(step.result)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/** Build a standalone, print-friendly HTML calc sheet for download. */
function buildSheetHtml(
  memberId: string,
  designCode: string,
  steps: CalculationTraceStep[]
): string {
  const rows = steps
    .map(
      (s) => `
    <div class="step">
      <div class="step-head">
        <span class="num">${String(s.step).padStart(2, "0")}</span>
        <span class="desc">${s.description}</span>
        ${s.clause ? `<span class="clause">${s.clause}</span>` : ""}
      </div>
      ${s.formula ? `<div class="formula">${s.formula}</div>` : ""}
      ${
        s.inputs
          ? `<div class="inputs">${Object.entries(s.inputs)
              .map(([k, v]) => `<span>${k} = ${formatValue(v)}</span>`)
              .join("")}</div>`
          : ""
      }
      <div class="result">⇒ ${formatValue(s.result)}</div>
    </div>`
    )
    .join("");

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Calculation Sheet — ${memberId}</title>
<style>
  body { font-family: 'Inter', system-ui, sans-serif; color: #111; margin: 40px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  .meta { color: #666; font-size: 12px; margin-bottom: 24px; }
  .step { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 10px; page-break-inside: avoid; }
  .step-head { display: flex; align-items: center; gap: 8px; background: #f5f5f5; padding: 6px 10px; border-bottom: 1px solid #eee; }
  .num { font-family: monospace; font-weight: bold; color: #2563eb; }
  .desc { flex: 1; font-weight: 600; font-size: 13px; }
  .clause { font-family: monospace; font-size: 10px; background: #e0e7ff; color: #3730a3; padding: 2px 6px; border-radius: 4px; }
  .formula { font-family: monospace; font-size: 12px; background: #fafafa; padding: 6px 10px; }
  .inputs { display: flex; flex-wrap: wrap; gap: 12px; padding: 4px 10px; font-family: monospace; font-size: 11px; color: #666; }
  .result { font-family: monospace; font-size: 13px; padding: 6px 10px; font-weight: 600; }
</style></head>
<body>
  <h1>Calculation Sheet — Member ${memberId}</h1>
  <div class="meta">Design code: ${designCode} · Generated ${new Date().toLocaleString()}</div>
  ${rows}
</body></html>`;
}

export function CalcSheetTab({
  analysis,
  design,
  designCode,
}: {
  analysis: MemberFullAnalysisResult | null;
  design: DesignMemberResult | null;
  designCode: string;
}) {
  // Merge analysis trace with any design notes (rendered as trailing steps).
  const steps = React.useMemo((): CalculationTraceStep[] => {
    const arr: CalculationTraceStep[] = [...(analysis?.calculation_trace ?? [])];
    if (design?.notes?.length) {
      const base = arr.length;
      design.notes.forEach((note, i) => {
        arr.push({
          step: base + i + 1,
          description: note,
          result: null,
        });
      });
    }
    return arr;
  }, [analysis, design]);

  const projectId = useProjectStore((s) => s.activeProject?.project_id);
  const projectRef = useProjectStore((s) => s.activeProject?.reference);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  const handleDownload = useCallback(() => {
    if (!analysis) return;
    const html = buildSheetHtml(analysis.member_id, designCode, steps);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${analysis.member_id}_calc_sheet.html`;
    a.click();
    URL.revokeObjectURL(url);
  }, [analysis, designCode, steps]);

  // Generate a proper PDF calc sheet server-side (WeasyPrint), then download it.
  const handleDownloadPdf = useCallback(async () => {
    if (!projectId) return;
    setDownloadingPdf(true);
    try {
      const { data } = await apiClient.post(
        `/api/v1/reports/${projectId}/from-project`,
        null,
        { params: { report_type: "calculation_sheets", fmt: "pdf" } }
      );
      await downloadFromApi(
        `/api/v1/reports/${data.report_id}/download`,
        `${projectRef || projectId}_calc_sheet.pdf`
      );
    } catch (err) {
      const status = (err as { status?: number })?.status;
      toast.error(
        status === 503
          ? "PDF export is unavailable on the server (WeasyPrint not installed)."
          : "Could not generate the PDF report."
      );
    } finally {
      setDownloadingPdf(false);
    }
  }, [projectId, projectRef]);

  if (!analysis || steps.length === 0) {
    return (
      <div className="p-4 text-center">
        <FileText className="w-5 h-5 mx-auto text-muted-foreground mb-2" />
        <p className="text-xs text-muted-foreground italic">
          No calculation trace is available for this member.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          <FileText className="w-3 h-3" />
          {steps.length} steps · {designCode}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border border-border/50 text-foreground/80 hover:bg-muted/40 transition-colors"
          >
            <Download className="w-3 h-3" />
            HTML
          </button>
          <button
            onClick={handleDownloadPdf}
            disabled={downloadingPdf || !projectId}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border border-border/50 text-foreground/80 hover:bg-muted/40 transition-colors disabled:opacity-50"
            title="Generate a PDF calculation report"
          >
            <FileDown className="w-3 h-3" />
            {downloadingPdf ? "Generating…" : "PDF"}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {steps.map((s, i) => (
          <StepBlock key={i} step={s} />
        ))}
      </div>
    </div>
  );
}

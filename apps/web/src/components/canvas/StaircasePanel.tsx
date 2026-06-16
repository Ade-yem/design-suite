"use client";

import * as React from "react";
import { useEffect, useState } from "react";
import { Save, Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api";
import { DrawingCanvas, type MemberDrawing } from "@/components/drawing/DrawingCanvas";
import type { GeometricMember, MemberMeta } from "@/types/canvas";

interface StaircasePanelProps {
  projectId: string;
  member: GeometricMember;
  /** Persist a meta/classification patch (reuses canvasStore.updateMember). */
  onSave: (patch: { member_type?: GeometricMember["member_type"]; meta?: Partial<MemberMeta> }) => void;
  onClose: () => void;
}

const INPUT = "w-20 bg-muted text-foreground text-xs rounded border border-border px-2 py-1 focus:outline-hidden focus:ring-1 focus:ring-primary";
const LABEL = "text-[10px] text-muted-foreground font-mono";

function n(v: string): number | undefined {
  if (v.trim() === "") return undefined;
  const x = parseFloat(v);
  return Number.isFinite(x) && x > 0 ? x : undefined;
}

/**
 * Dedicated staircase editor + visualiser.
 *
 * A staircase can't be drawn in the plan, so it is anchored on its stairwell
 * (a void the engineer reclassifies) and edited here: parametric geometry on the
 * left, the backend-generated flight section/elevation on the right. Geometry is
 * derived from the building storey height on the server; values entered here
 * override it.
 */
export function StaircasePanel({
  projectId,
  member,
  onSave,
  onClose,
}: StaircasePanelProps): React.ReactElement {
  const meta = member.meta;
  const isVoid = member.member_type === "void";

  const [fields, setFields] = useState<Record<string, string>>({});
  const [view, setView] = useState<"elevation" | "section">("elevation");
  const [drawing, setDrawing] = useState<MemberDrawing | null>(null);
  const [loadingDrawing, setLoadingDrawing] = useState(false);

  useEffect(() => {
    const s = (v: unknown) => (v === undefined || v === null ? "" : String(v));
    setFields({
      riser: s(meta.riser),
      tread: s(meta.tread),
      waist: s(meta.waist),
      width: s(meta.width),
      num_steps: s(meta.num_steps),
    });
  }, [member, meta]);

  // Fetch the generated flight drawing (available once the member is designed).
  useEffect(() => {
    if (member.member_type !== "staircase") return;
    let cancelled = false;
    setLoadingDrawing(true);
    apiClient
      .get(`/api/v1/drawings/${projectId}/member/${member.member_id}`)
      .then((res) => {
        if (!cancelled) setDrawing(res.data as MemberDrawing);
      })
      .catch(() => {
        if (!cancelled) setDrawing(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingDrawing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, member.member_id, member.member_type]);

  const set = (k: string, v: string) => setFields((p) => ({ ...p, [k]: v }));

  const handleSave = () => {
    const patch: Partial<MemberMeta> = {};
    const put = (k: keyof MemberMeta, raw: string) => {
      const v = n(raw);
      if (v !== undefined) (patch[k] as number) = v;
    };
    put("riser", fields.riser);
    put("tread", fields.tread);
    put("waist", fields.waist);
    put("width", fields.width);
    put("num_steps", fields.num_steps);
    onSave({ meta: patch });
  };

  return (
    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[92%] max-w-3xl max-h-[72vh] overflow-hidden bg-card/95 border border-border shadow-xl rounded-xl backdrop-blur-md animate-fade-in-up flex flex-col">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-primary">{member.member_id}</span>
          <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground uppercase font-mono">
            staircase
          </span>
        </div>
        <button onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground">
          Deselect
        </button>
      </div>

      {isVoid ? (
        <div className="p-6 flex flex-col items-center gap-3 text-center">
          <p className="text-xs text-muted-foreground max-w-sm">
            This opening can host a staircase. Define a flight here to size and
            detail it from the building storey height.
          </p>
          <button
            onClick={() => onSave({ member_type: "staircase" })}
            className="px-4 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/95 font-medium"
          >
            Define staircase here
          </button>
        </div>
      ) : (
        <div className="flex flex-1 min-h-0 divide-x divide-border">
          {/* Parametric inputs */}
          <div className="w-52 shrink-0 p-3 flex flex-col gap-2 overflow-y-auto">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Flight geometry</span>
            {typeof meta.storey_height_m === "number" && (
              <p className="text-[10px] text-muted-foreground">
                Derived from storey height {String(meta.storey_height_m)} m. Override below.
              </p>
            )}
            {([
              ["riser", "Riser R (mm)"],
              ["tread", "Going G (mm)"],
              ["waist", "Waist (mm)"],
              ["width", "Width (mm)"],
              ["num_steps", "Treads"],
            ] as const).map(([key, label]) => (
              <div key={key} className="flex items-center justify-between gap-2">
                <label className={LABEL}>{label}</label>
                <input
                  type="number"
                  min="0"
                  value={fields[key] ?? ""}
                  onChange={(e) => set(key, e.target.value)}
                  className={INPUT}
                />
              </div>
            ))}
            <button
              onClick={handleSave}
              className="mt-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/95 font-medium"
            >
              <Save className="h-3.5 w-3.5" />
              Apply &amp; Stage
            </button>
          </div>

          {/* Drawing */}
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border">
              {(["elevation", "section"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`text-[11px] px-2 py-0.5 rounded capitalize ${
                    view === v ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
            <div className="flex-1 min-h-0 p-3 grid place-items-center bg-muted/20">
              {loadingDrawing ? (
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              ) : drawing ? (
                <DrawingCanvas drawing={drawing} view={view} className="max-h-[44vh]" />
              ) : (
                <p className="text-[11px] text-muted-foreground text-center max-w-xs">
                  The flight drawing appears here once the staircase has been
                  analysed and designed.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

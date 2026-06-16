"use client";

import * as React from "react";
import { useState, useEffect } from "react";
import { Trash2, Save } from "lucide-react";
import type { GeometricMember, MemberMeta, MemberType } from "@/types/canvas";

/** Patch emitted when the engineer applies edits. Mirrors canvasStore.updateMember. */
export interface MemberPropertyPatch {
  member_type?: MemberType;
  meta?: Partial<MemberMeta>;
}

interface PropertyInspectorProps {
  /** The currently selected structural member to inspect or modify */
  selectedMember: GeometricMember;
  /** Callback triggered when the engineer deselects the current member */
  onDeselect: () => void;
  /** Callback triggered to delete the selected member from the layout */
  onDelete: () => void;
  /** Callback triggered to stage a classification/geometry patch back onto the layout */
  onSave: (patch: MemberPropertyPatch) => void;
}

/** Member types the engineer can reclassify between (parser occasionally mislabels). */
const RECLASSIFY_OPTIONS: MemberType[] = [
  "beam",
  "column",
  "slab",
  "wall",
  "footing",
  "staircase",
  "void",
];

const SECTION_TYPES = ["rectangular", "flanged"];
const SUPPORT_CONDITIONS = ["simple", "continuous", "cantilever"];
const SLAB_SYSTEMS = ["solid", "ribbed", "waffle", "flat"];
const SLAB_TYPES = ["one-way", "two-way"];
const EDGE_CONDITIONS = ["interior", "edge", "corner"];

const INPUT_CLASS =
  "bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary";
const LABEL_CLASS = "text-[10px] text-muted-foreground font-mono";

/** Parse a numeric string; return undefined for blank/NaN so we never clobber a value with 0. */
function num(v: string): number | undefined {
  if (v.trim() === "") return undefined;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * PropertyInspector — adaptive, per-member-type editor.
 *
 * Surfaces the geometry + classification parameters the design engine actually
 * consumes (not just width/depth/span): member-type reclassification, beam
 * section/support, and — critically — the slab **structural system**
 * (solid / ribbed / waffle / flat) with the system-specific fields each
 * implies. Edits are staged locally and only persisted at "Verify & Lock".
 */
export function PropertyInspector({
  selectedMember,
  onDeselect,
  onDelete,
  onSave,
}: PropertyInspectorProps): React.ReactElement {
  const m = selectedMember;
  const meta = m.meta;

  // Form state — strings for inputs, with the live member_type and a few booleans.
  const [memberType, setMemberType] = useState<MemberType>(m.member_type);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [initialFields, setInitialFields] = useState<Record<string, string>>({});
  const [isDrop, setIsDrop] = useState<boolean>(Boolean(meta.is_drop_panel));
  const [braced, setBraced] = useState<boolean>(meta.braced !== false);

  useEffect(() => {
    // Sync form state when the selected member changes.
    setMemberType(m.member_type);
    setIsDrop(Boolean(meta.is_drop_panel));
    setBraced(meta.braced !== false);
    const s = (v: unknown) => (v === undefined || v === null ? "" : String(v));
    const seeded: Record<string, string> = {
      b_mm: s(meta.b_mm),
      h_mm: s(meta.h_mm),
      L_clear: s(meta.L_clear),
      section_type: s(meta.section_type ?? "rectangular"),
      support_condition: s(meta.support_condition ?? "simple"),
      bf: s(meta.bf),
      hf: s(meta.hf),
      slab_system: s(meta.slab_system ?? "solid"),
      slab_type: s(meta.slab_type ?? "one-way"),
      Lx: s(meta.Lx),
      Ly: s(meta.Ly),
      panel_type: s(meta.panel_type),
      rib_width: s(meta.rib_width),
      rib_spacing: s(meta.rib_spacing),
      topping_thickness: s(meta.topping_thickness),
      column_c: s(meta.column_c),
      drop_thickness_extra: s(meta.drop_thickness_extra),
      drop_lx: s(meta.drop_lx),
      drop_ly: s(meta.drop_ly),
      edge_condition: s(meta.edge_condition ?? "interior"),
      l_ex: s(meta.l_ex),
      l_ey: s(meta.l_ey),
      l_w: s(meta.l_w),
      l_e: s(meta.l_e),
    };
    setFields(seeded);
    setInitialFields(seeded);
  }, [m, meta]);

  const set = (key: string, value: string) =>
    setFields((prev) => ({ ...prev, [key]: value }));

  // ── Dirty tracking ──────────────────────────────────────────────────────
  // Compare against the seeded baseline so default reveals don't read as edits.
  const reclassified = memberType !== m.member_type;
  const dirty =
    reclassified ||
    isDrop !== Boolean(meta.is_drop_panel) ||
    braced !== (meta.braced !== false) ||
    Object.keys(fields).some((k) => fields[k] !== (initialFields[k] ?? ""));

  const handleSave = () => {
    const patch: MemberPropertyPatch = {};
    const nextMeta: Partial<MemberMeta> = {};

    const putNum = (key: keyof MemberMeta, raw: string) => {
      const n = num(raw);
      if (n !== undefined && n > 0) (nextMeta[key] as number) = n;
    };
    const putStr = (key: keyof MemberMeta, raw: string) => {
      if (raw.trim() !== "") (nextMeta[key] as string) = raw;
    };

    // Common dimensions.
    putNum("b_mm", fields.b_mm);
    putNum("h_mm", fields.h_mm);

    if (memberType === "beam") {
      putStr("section_type", fields.section_type);
      putStr("support_condition", fields.support_condition);
      putNum("L_clear", fields.L_clear);
      if (fields.section_type === "flanged") {
        putNum("bf", fields.bf);
        putNum("hf", fields.hf);
      }
    } else if (memberType === "slab") {
      putStr("slab_system", fields.slab_system);
      putStr("slab_type", fields.slab_type);
      putNum("Lx", fields.Lx);
      putNum("Ly", fields.Ly);
      if (fields.slab_system === "ribbed" || fields.slab_system === "waffle") {
        putNum("rib_width", fields.rib_width);
        putNum("rib_spacing", fields.rib_spacing);
        putNum("topping_thickness", fields.topping_thickness);
      } else if (fields.slab_system === "flat") {
        putNum("column_c", fields.column_c);
        putStr("edge_condition", fields.edge_condition);
        nextMeta.is_drop_panel = isDrop;
        if (isDrop) {
          putNum("drop_thickness_extra", fields.drop_thickness_extra);
          putNum("drop_lx", fields.drop_lx);
          putNum("drop_ly", fields.drop_ly);
        }
      }
    } else if (memberType === "column") {
      nextMeta.braced = braced;
      putNum("l_ex", fields.l_ex);
      putNum("l_ey", fields.l_ey);
    } else if (memberType === "wall") {
      putNum("l_w", fields.l_w);
      putNum("l_e", fields.l_e);
    }

    if (Object.keys(nextMeta).length > 0) patch.meta = nextMeta;
    if (reclassified) patch.member_type = memberType;
    onSave(patch);
  };

  // ── Field renderers ─────────────────────────────────────────────────────
  const numberField = (key: string, label: string, step = "1") => (
    <div className="flex flex-col gap-1" key={key}>
      <label className={LABEL_CLASS}>{label}</label>
      <input
        type="number"
        step={step}
        min="0"
        value={fields[key] ?? ""}
        onChange={(e) => set(key, e.target.value)}
        className={INPUT_CLASS}
      />
    </div>
  );

  const selectField = (key: string, label: string, options: string[]) => (
    <div className="flex flex-col gap-1" key={key}>
      <label className={LABEL_CLASS}>{label}</label>
      <select
        value={fields[key] ?? options[0]}
        onChange={(e) => set(key, e.target.value)}
        className={INPUT_CLASS}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );

  // Read-only positional context.
  const coord = (p: GeometricMember["start_point"]) =>
    p ? `(${Math.round(p.x)}, ${Math.round(p.y)})` : "—";

  return (
    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[92%] max-w-2xl max-h-[70vh] overflow-y-auto bg-card/95 border border-border shadow-xl rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md animate-fade-in-up">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-primary">{m.member_id}</span>
          <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground uppercase font-mono">
            {memberType}
          </span>
          {dirty && (
            <span className="text-[10px] bg-amber-500/15 text-amber-600 dark:text-amber-400 px-2 py-0.5 rounded font-medium">
              Staged · applies at Verify &amp; Lock
            </span>
          )}
        </div>
        <button
          onClick={onDeselect}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Deselect
        </button>
      </div>

      {/* Classification (all types) */}
      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col gap-1">
          <label className={LABEL_CLASS}>Classification</label>
          <select
            value={memberType}
            onChange={(e) => setMemberType(e.target.value as MemberType)}
            className={INPUT_CLASS}
          >
            {RECLASSIFY_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
        {numberField("b_mm", memberType === "wall" ? "Thickness (mm)" : "Width b (mm)")}
        {numberField("h_mm", "Depth/Thickness h (mm)")}
      </div>

      {/* Beam fields */}
      {memberType === "beam" && (
        <div className="grid grid-cols-3 gap-3">
          {selectField("section_type", "Section", SECTION_TYPES)}
          {selectField("support_condition", "Support", SUPPORT_CONDITIONS)}
          {numberField("L_clear", "Clear Span L (m)", "0.01")}
          {fields.section_type === "flanged" && numberField("bf", "Flange width bf (mm)")}
          {fields.section_type === "flanged" && numberField("hf", "Flange thick. hf (mm)")}
        </div>
      )}

      {/* Slab fields */}
      {memberType === "slab" && (
        <div className="grid grid-cols-3 gap-3">
          {selectField("slab_system", "Structural system", SLAB_SYSTEMS)}
          {selectField("slab_type", "Spanning", SLAB_TYPES)}
          {numberField("Lx", "Span Lx (mm)")}
          {numberField("Ly", "Span Ly (mm)")}

          {(fields.slab_system === "ribbed" || fields.slab_system === "waffle") && (
            <>
              {numberField("rib_width", "Rib width (mm)")}
              {numberField("rib_spacing", "Rib spacing (mm)")}
              {numberField("topping_thickness", "Topping (mm)")}
            </>
          )}

          {fields.slab_system === "flat" && (
            <>
              {numberField("column_c", "Column dim (mm)")}
              {selectField("edge_condition", "Panel", EDGE_CONDITIONS)}
              <div className="flex flex-col gap-1 justify-end">
                <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={isDrop}
                    onChange={(e) => setIsDrop(e.target.checked)}
                  />
                  Drop panel
                </label>
              </div>
              {isDrop && numberField("drop_thickness_extra", "Drop extra h (mm)")}
              {isDrop && numberField("drop_lx", "Drop ext. lx (mm)")}
              {isDrop && numberField("drop_ly", "Drop ext. ly (mm)")}
            </>
          )}
        </div>
      )}

      {/* Column fields */}
      {memberType === "column" && (
        <div className="grid grid-cols-3 gap-3 items-end">
          {numberField("l_ex", "Eff. length lex (mm)")}
          {numberField("l_ey", "Eff. length ley (mm)")}
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground pb-1.5">
            <input
              type="checkbox"
              checked={braced}
              onChange={(e) => setBraced(e.target.checked)}
            />
            Braced against sway
          </label>
        </div>
      )}

      {/* Wall fields */}
      {memberType === "wall" && (
        <div className="grid grid-cols-3 gap-3">
          {numberField("l_w", "Wall length lw (mm)")}
          {numberField("l_e", "Eff. height le (mm)")}
        </div>
      )}

      {/* Read-only positional context */}
      <div className="rounded-lg bg-muted/40 border border-border/60 px-3 py-2 text-[10px] text-muted-foreground font-mono grid grid-cols-2 gap-x-4 gap-y-1">
        <span>start: {coord(m.start_point)}</span>
        <span>end: {coord(m.end_point)}</span>
        {m.center_point && <span>center: {coord(m.center_point)}</span>}
        {m.spans_m && m.spans_m.length > 0 && (
          <span>spans: {m.spans_m.map((s) => s.toFixed(2)).join(", ")} m</span>
        )}
        {m.storey && <span>storey: {m.storey}</span>}
        {typeof meta.layer === "string" && <span>layer: {meta.layer}</span>}
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-border mt-1">
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-destructive border border-destructive/20 rounded hover:bg-destructive/10 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete Member
        </button>
        <button
          onClick={handleSave}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/95 transition-colors font-medium shadow-xs"
        >
          <Save className="h-3.5 w-3.5" />
          Apply &amp; Stage
        </button>
      </div>
    </div>
  );
}

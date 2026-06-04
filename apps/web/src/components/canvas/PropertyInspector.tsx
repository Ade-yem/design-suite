"use client";

import * as React from "react";
import { useState, useEffect } from "react";
import { Trash2, Save } from "lucide-react";
import type { GeometricMember } from "@/types/canvas";

/**
 * Props for the PropertyInspector component.
 */
interface PropertyInspectorProps {
  /** The currently selected structural member to inspect or modify */
  selectedMember: GeometricMember;
  /** Callback triggered when the engineer deselects the current member */
  onDeselect: () => void;
  /** Callback triggered to delete the selected member from the layout */
  onDelete: () => void;
  /** Callback triggered to save updated cross-sectional dimensions back to the layout */
  onSave: (width: number, depth: number, span: number | undefined) => void;
}

/**
 * PropertyInspector component.
 * Renders an absolute-positioned overlays dashboard at the bottom of the canvas
 * allowing engineers to view, update, and persist dimensional modifications (width, depth, span)
 * of classified structural members.
 *
 * @param {PropertyInspectorProps} props - Component properties.
 * @returns {React.ReactElement} The rendered PropertyInspector component.
 */
export function PropertyInspector({
  selectedMember,
  onDeselect,
  onDelete,
  onSave,
}: PropertyInspectorProps): React.ReactElement {
  const [width, setWidth] = useState(String(selectedMember.meta.b_mm ?? ""));
  const [depth, setDepth] = useState(String(selectedMember.meta.h_mm ?? ""));
  const [span, setSpan] = useState(String(selectedMember.meta.L_clear ?? ""));

  useEffect(() => {
    // Sync form state with selected member. Safe to setState here as this is synchronizing
    // external prop state to internal form state, not causing cascading renders.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWidth(String(selectedMember.meta.b_mm ?? ""));
    setDepth(String(selectedMember.meta.h_mm ?? ""));
    setSpan(String(selectedMember.meta.L_clear ?? ""));
  }, [selectedMember]);

  const handleSave = () => {
    const wVal = parseFloat(width);
    const dVal = parseFloat(depth);
    const sVal = parseFloat(span);

    onSave(
      isNaN(wVal) ? 0 : wVal,
      isNaN(dVal) ? 0 : dVal,
      isNaN(sVal) ? undefined : sVal,
    );
  };

  const isSpanDisabled =
    selectedMember.member_type === "column" ||
    selectedMember.member_type === "footing";

  return (
    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[90%] max-w-2xl bg-card/95 border border-border shadow-xl rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md animate-fade-in-up">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-primary">
            {selectedMember.member_id}
          </span>
          <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground uppercase font-mono">
            {selectedMember.member_type}
          </span>
        </div>
        <button
          onClick={onDeselect}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Deselect
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-muted-foreground font-mono">
            Width b (mm)
          </label>
          <input
            type="number"
            value={width}
            onChange={(e) => setWidth(e.target.value)}
            className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-muted-foreground font-mono">
            Depth/Thickness h (mm)
          </label>
          <input
            type="number"
            value={depth}
            onChange={(e) => setDepth(e.target.value)}
            className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-muted-foreground font-mono">
            Clear Span L (m)
          </label>
          <input
            type="number"
            step="0.01"
            value={span}
            onChange={(e) => setSpan(e.target.value)}
            disabled={isSpanDisabled}
            className="bg-muted text-foreground text-xs rounded border border-border px-2 py-1.5 disabled:opacity-50 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
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
          Apply & Save Property
        </button>
      </div>
    </div>
  );
}

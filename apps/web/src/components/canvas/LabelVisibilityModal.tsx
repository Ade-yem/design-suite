"use client";

/**
 * @file LabelVisibilityModal.tsx
 * @description Floating modal panel for controlling member label visibility on the canvas.
 *
 * Two-section layout:
 *   1. **Member Types** — one toggle row per MemberType with the count of members in that
 *      type shown as a badge.  Toggling a type hides/shows all labels for that type.
 *   2. **Individual Members** — a searchable flat list of all member IDs.  Each item has its
 *      own toggle.  Individual overrides apply even when the member's type is visible.
 *
 * The component reads and writes directly to the `canvasStore` via the callback props
 * passed from `CanvasViewport`.  It is self-contained and does not fetch from the network.
 *
 * Keyboard: closes on `Escape`.
 *
 * @module components/canvas/LabelVisibilityModal
 */

import * as React from "react";
import { useState, useEffect, useCallback, useMemo } from "react";
import { X, RotateCcw, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GeometricMember, MemberType } from "@/types/canvas";

// ── Member type display metadata ─────────────────────────────────────────────

const MEMBER_TYPE_META: Record<MemberType, { label: string; colour: string }> = {
  beam:      { label: "Beams",      colour: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40" },
  column:    { label: "Columns",    colour: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  slab:      { label: "Slabs",      colour: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  wall:      { label: "Walls",      colour: "bg-slate-500/20 text-slate-300 border-slate-500/40" },
  footing:   { label: "Footings",   colour: "bg-yellow-600/20 text-yellow-300 border-yellow-600/40" },
  staircase: { label: "Staircases", colour: "bg-purple-500/20 text-purple-300 border-purple-500/40" },
  void:      { label: "Voids",      colour: "bg-red-500/20 text-red-300 border-red-500/40" },
};

const ALL_MEMBER_TYPES: MemberType[] = [
  "beam", "column", "slab", "wall", "footing", "staircase", "void",
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface LabelVisibilityModalProps {
  /** All structural members currently on the canvas. */
  members: GeometricMember[];
  /** Set of MemberType strings whose labels are currently hidden. */
  hiddenLabelTypes: Set<MemberType>;
  /** Set of individual member IDs whose labels are currently hidden. */
  hiddenLabelIds: Set<string>;
  /** Toggle the label visibility for an entire member type. */
  onToggleType: (type: MemberType) => void;
  /** Toggle the label visibility for a specific member ID. */
  onToggleMember: (id: string) => void;
  /** Reset all label visibility overrides. */
  onReset: () => void;
  /** Close the modal. */
  onClose: () => void;
}

// ── Toggle row sub-component ──────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
  id,
}: {
  checked: boolean;
  onChange: () => void;
  id: string;
}): React.ReactElement {
  return (
    <button
      id={id}
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={cn(
        "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-primary",
        checked ? "bg-primary" : "bg-muted",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-4.5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * LabelVisibilityModal component.
 *
 * @param {LabelVisibilityModalProps} props
 * @returns {React.ReactElement}
 */
export function LabelVisibilityModal({
  members,
  hiddenLabelTypes,
  hiddenLabelIds,
  onToggleType,
  onToggleMember,
  onReset,
  onClose,
}: LabelVisibilityModalProps): React.ReactElement {
  const [search, setSearch] = useState("");

  // Close on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );
  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Count members per type
  const countByType = useMemo(() => {
    const map: Partial<Record<MemberType, number>> = {};
    for (const m of members) {
      map[m.member_type] = (map[m.member_type] ?? 0) + 1;
    }
    return map;
  }, [members]);

  // Filter individual members by search query
  const filteredMembers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return members;
    return members.filter(
      (m) =>
        m.member_id.toLowerCase().includes(q) ||
        m.member_type.toLowerCase().includes(q),
    );
  }, [members, search]);

  return (
    <div
      id="label-visibility-modal"
      role="dialog"
      aria-label="Member Label Visibility"
      className={cn(
        "absolute top-3 right-16 z-20 w-72",
        "bg-card/95 backdrop-blur-md border border-border rounded-xl shadow-2xl",
        "flex flex-col overflow-hidden",
        "max-h-[calc(100%-1.5rem)]",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <span className="text-sm font-semibold text-foreground tracking-wide">
          Member Labels
        </span>
        <div className="flex items-center gap-1">
          <button
            id="label-modal-reset"
            onClick={onReset}
            title="Reset all visibility"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            id="label-modal-close"
            onClick={onClose}
            title="Close"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 min-h-0">
        {/* Section 1: Member Types */}
        <div className="px-4 pt-3 pb-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
            By Type
          </p>
          <div className="space-y-1">
            {ALL_MEMBER_TYPES.filter((t) => (countByType[t] ?? 0) > 0).map((type) => {
              const meta = MEMBER_TYPE_META[type];
              const isVisible = !hiddenLabelTypes.has(type);
              const count = countByType[type] ?? 0;
              return (
                <div
                  key={type}
                  className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded border",
                        meta.colour,
                      )}
                    >
                      {type.toUpperCase()}
                    </span>
                    <span className="text-xs text-foreground">{meta.label}</span>
                    <span className="text-[10px] text-muted-foreground">({count})</span>
                  </div>
                  <ToggleSwitch
                    id={`label-type-toggle-${type}`}
                    checked={isVisible}
                    onChange={() => onToggleType(type)}
                  />
                </div>
              );
            })}
          </div>
        </div>

        <div className="h-px bg-border mx-4" />

        {/* Section 2: Individual Members */}
        <div className="px-4 pt-3 pb-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
            Individual Members
          </p>

          {/* Search */}
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <input
              id="label-member-search"
              type="text"
              placeholder="Search member ID or type…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={cn(
                "w-full pl-8 pr-3 py-1.5 text-xs rounded-md",
                "bg-muted/60 border border-border text-foreground placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-1 focus:ring-primary/60",
              )}
            />
          </div>

          {/* Member list */}
          <div className="space-y-0.5 max-h-48 overflow-y-auto pr-0.5">
            {filteredMembers.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                No members match "{search}"
              </p>
            ) : (
              filteredMembers.map((m) => {
                const isVisible = !hiddenLabelIds.has(m.member_id);
                const meta = MEMBER_TYPE_META[m.member_type];
                return (
                  <div
                    key={m.member_id}
                    className="flex items-center justify-between py-1 px-2 rounded-md hover:bg-muted/40 transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={cn(
                          "shrink-0 text-[9px] font-mono px-1 py-0.5 rounded border",
                          meta.colour,
                        )}
                      >
                        {m.member_type[0].toUpperCase()}
                      </span>
                      <span className="text-xs font-mono text-foreground truncate">
                        {m.member_id}
                      </span>
                    </div>
                    <ToggleSwitch
                      id={`label-member-toggle-${m.member_id}`}
                      checked={isVisible}
                      onChange={() => onToggleMember(m.member_id)}
                    />
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

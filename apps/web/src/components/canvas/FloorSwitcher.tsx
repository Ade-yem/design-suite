"use client";

import * as React from "react";
import { Layers } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Props for the FloorSwitcher component.
 */
interface FloorSwitcherProps {
  /** Sorted storey codes available (e.g. ["L01", "L02"]). */
  storeys: string[];
  /** The currently active storey, or null when showing all. */
  activeStorey: string | null;
  /** Callback to change the active storey (null = show all floors). */
  onChange: (storey: string | null) => void;
}

/**
 * FloorSwitcher component.
 *
 * A compact floating tab-bar above the canvas that switches the active
 * rendering plane between building storeys. Only relevant once the geometry has
 * been extrapolated into multiple floors; the parent hides it for single-floor
 * plans.
 *
 * @param {FloorSwitcherProps} props - Component properties.
 * @returns {React.ReactElement} The rendered floor switcher.
 */
export function FloorSwitcher({
  storeys,
  activeStorey,
  onChange,
}: FloorSwitcherProps): React.ReactElement {
  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-1">
      <span className="flex items-center gap-1 px-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Layers className="h-3.5 w-3.5" />
        Floor
      </span>
      {storeys.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          title={`Show ${s}`}
          className={cn(
            "px-2.5 py-1 rounded-md text-xs font-mono transition-colors",
            activeStorey === s
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          {s}
        </button>
      ))}
      <button
        onClick={() => onChange(null)}
        title="Show all floors"
        className={cn(
          "px-2.5 py-1 rounded-md text-xs transition-colors",
          activeStorey === null
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
      >
        All
      </button>
    </div>
  );
}

"use client";

import * as React from "react";
import { useState } from "react";
import { CheckCircle2, AlertCircle, RotateCcw, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Props for the GeometryVerificationBar component.
 */
interface GeometryVerificationBarProps {
  /** The current verification status from state: 'idle' | 'submitting' | 'verified' | 'error' | 'pending' */
  verificationStatus: "idle" | "submitting" | "verified" | "error" | "pending";
  /** The total number of detected structural members currently on the canvas */
  memberCount: number;
  /** Callback triggered to confirm layout with optional review notes */
  onConfirm: (notes: string) => Promise<void>;
  /** Callback triggered to reset geometry to original parsed state */
  onReset: () => Promise<void>;
}

/**
 * GeometryVerificationBar component.
 * Renders the sticky Safety Gate 1 review and verification footer, enforcing the
 * mandatory human-in-the-loop sign-off before global frame analysis can begin.
 *
 * @param {GeometryVerificationBarProps} props - Component properties.
 * @returns {React.ReactElement} The rendered verification bar component.
 */
export function GeometryVerificationBar({
  verificationStatus,
  memberCount,
  onConfirm,
  onReset,
}: GeometryVerificationBarProps): React.ReactElement {
  const [notes, setNotes] = useState("");

  const handleConfirm = () => {
    onConfirm(notes);
  };

  const isVerified = verificationStatus === "verified";
  const isSubmitting = verificationStatus === "submitting" || verificationStatus === "pending";
  const isError = verificationStatus === "error";

  return (
    <div
      className={cn(
        "absolute bottom-0 inset-x-0 z-10 border-t flex flex-col md:flex-row items-stretch md:items-center justify-between p-3.5 gap-3 backdrop-blur-md transition-all shadow-lg",
        isVerified
          ? "bg-green-500/10 border-green-500/20"
          : isError
            ? "bg-destructive/10 border-destructive/20"
            : "bg-amber-500/10 border-amber-500/20",
      )}
    >
      <div className="flex items-start gap-3">
        {isVerified ? (
          <CheckCircle2 className="h-5 w-5 text-green-400 mt-0.5 shrink-0" />
        ) : isError ? (
          <AlertCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
        ) : (
          <AlertCircle className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
        )}
        <div className="flex flex-col">
          <p className="text-xs font-semibold">
            {isVerified
              ? "Geometry Verified & Safety Gate Approved"
              : isError
                ? "Geometry Verification Failed"
                : "Geometry Verification Required (Safety Gate 1)"}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {isVerified
              ? "Design parameters locked in. Let the Assistant engineer know in the conversation sidebar to analyze."
              : isError
                ? "An error occurred while confirming geometry. Please review notes and retry."
                : `Verify detected ${memberCount} member locations. Select any beam/column to customize cross-sections.`}
          </p>
        </div>
      </div>

      {!isVerified && (
        <div className="flex items-center gap-2 max-w-md w-full md:w-auto">
          <input
            type="text"
            placeholder="Enter review notes (optional)..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="flex-1 bg-muted/60 text-xs rounded border border-border px-2.5 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-primary w-48 font-mono"
          />
          <button
            onClick={onReset}
            title="Reset geometry to original AI parsed state"
            className="p-1.5 text-muted-foreground hover:text-foreground border border-border rounded hover:bg-muted transition-all"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <button
            onClick={handleConfirm}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded hover:bg-primary/95 transition-all shadow-xs disabled:opacity-50 shrink-0"
          >
            {isSubmitting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
            Confirm Layout
          </button>
        </div>
      )}

      {isVerified && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-green-400 font-medium">
            Ready for Downstream Analysis
          </span>
        </div>
      )}
    </div>
  );
}

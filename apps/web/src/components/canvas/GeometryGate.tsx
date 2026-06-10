"use client";

import { useState } from "react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import type { ScaleInfo, VerificationStatus } from "@/types/canvas";

interface GeometryGateProps {
  scale: ScaleInfo | null;
  scaleFactor: number;
  scaleUnit: "mm" | "m" | "cm";
  onScaleUnitChange: (unit: "mm" | "m" | "cm") => void;
  onConfirmScale: () => Promise<void>;
  isConfirmingScale: boolean;

  verificationStatus: VerificationStatus;
  memberCount: number;
  onConfirmGeometry: (notes?: string) => Promise<void>;
  onResetGeometry: () => void;
  onRegenerateLayout?: () => Promise<void>;
  isRegenerating?: boolean;
}

export const GeometryGate: React.FC<GeometryGateProps> = ({
  scale,
  scaleFactor,
  scaleUnit,
  onScaleUnitChange,
  onConfirmScale,
  isConfirmingScale,
  verificationStatus,
  memberCount,
  onConfirmGeometry,
  onResetGeometry,
  onRegenerateLayout,
  isRegenerating = false,
}) => {
  const [isConfirmingGeometry, setIsConfirmingGeometry] = useState(false);

  // Determine gate state
  const scaleConfirmed = scale?.confirmed ?? false;
  const scaleDetected = scale?.detected ?? false;

  // Step machine: 1 (confirm scale) → 2 (review members) → 3 (sign off)
  const step1Done = scaleConfirmed;
  const step2Done = true; // Always true; step 2 is review, not a gating action
  const step3Enabled = step1Done && step2Done; // Can only sign off if scale confirmed

  // Only show the gate if a scale is present and either detected or confirmed
  const hasScale = scale !== null;
  if ((!hasScale || (!scaleDetected && !scaleConfirmed)) && verificationStatus === "pending") {
    return null;
  }

  // if (verificationStatus === "verified") return null;

  return (
    <div className="absolute bottom-0 inset-x-0 z-20 border-t border-amber-500/30 bg-amber-500/5 backdrop-blur-md">
      <div className="flex items-stretch divide-x divide-amber-500/20">
        {/* Step 1: Confirm Scale */}
        <div className="flex-1 flex flex-col gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            {step1Done ? (
              <Check className="h-4 w-4 text-green-400" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-400" />
            )}
            <span className="text-xs font-semibold text-amber-200">
              Step 1: Confirm Scale
            </span>
          </div>

          {!step1Done && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-200/70">
                Scale auto-detected: {scaleFactor}
              </span>
              <select
                value={scaleUnit}
                onChange={(e) =>
                  onScaleUnitChange(e.target.value as "mm" | "m" | "cm")
                }
                className="bg-muted/60 border border-border text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-amber-400 text-foreground"
              >
                <option value="mm">mm</option>
                <option value="m">m</option>
                <option value="cm">cm</option>
              </select>
              <button
                onClick={onConfirmScale}
                disabled={isConfirmingScale}
                className="ml-auto flex items-center gap-1 px-3 py-1 bg-amber-500 text-amber-950 text-xs font-semibold rounded hover:bg-amber-400 transition-all disabled:opacity-50"
              >
                {isConfirmingScale ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                Confirm
              </button>
            </div>
          )}
        </div>

        {/* Step 2: Review Members */}
        <div className="flex-1 flex flex-col gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <Check className="h-4 w-4 text-green-400" />
            <span className="text-xs font-semibold text-amber-200">
              Step 2: Review {memberCount} Members
            </span>
          </div>
          <span className="text-xs text-amber-200/70">
            Use the Members panel (left) to verify all members are detected correctly.
          </span>
        </div>

        {/* Step 3: Sign Off */}
        <div className="flex-1 flex flex-col gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            {verificationStatus === "verified" ? (
              <Check className="h-4 w-4 text-green-400" />
            ) : (
              <div className="h-4 w-4 rounded-full border border-amber-400" />
            )}
            <span className="text-xs font-semibold text-amber-200">
              Step 3: Sign Off
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onResetGeometry()}
              disabled={!step3Enabled || isConfirmingGeometry || isRegenerating}
              className="px-3 py-1 text-xs rounded border border-amber-500/30 text-amber-200 hover:bg-amber-500/10 transition-all disabled:opacity-40"
            >
              Reset Geometry
            </button>
            {onRegenerateLayout && (
              <button
                onClick={onRegenerateLayout}
                disabled={!step3Enabled || isConfirmingGeometry || isRegenerating}
                className="px-3 py-1 text-xs rounded border border-amber-500/30 text-amber-200 hover:bg-amber-500/10 transition-all disabled:opacity-40 inline-flex items-center gap-1.5"
              >
                {isRegenerating && <Loader2 className="h-3 w-3 animate-spin" />}
                Regenerate Layout
              </button>
            )}
            <button
              onClick={async () => {
                setIsConfirmingGeometry(true);
                try {
                  await onConfirmGeometry();
                } finally {
                  setIsConfirmingGeometry(false);
                }
              }}
              disabled={!step3Enabled || isConfirmingGeometry || isRegenerating}
              className="ml-auto px-4 py-1 bg-blue-600 text-white text-xs font-semibold rounded hover:bg-blue-500 transition-all disabled:opacity-40"
            >
              {isConfirmingGeometry ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Confirming...
                </span>
              ) : (
                "Confirm Layout →"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

"use client";

import * as React from "react";
import { useState, useCallback, useRef, forwardRef, useImperativeHandle } from "react";
import {
  Upload,
  CheckCircle2,
  Loader2,
  AlertCircle,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";
import { useProjectSocket } from "@/hooks/useProjectSocket";

/**
 * Props for the CanvasUploader component.
 */
interface CanvasUploaderProps {
  /** The unique active project ID to bind the uploaded drawing files to */
  projectId: string;
  /** Callback triggered when files successfully parse, returning members list and scale metadata */
  onParsed: () => Promise<void>;
  /** Callback triggered when a new upload starts, notifying the parent component */
  onUploadStart?: () => void;
}

/**
 * Handle type exposed to parent components via ref.
 */
export interface CanvasUploaderHandle {
  /** Triggers the DXF file input element browse trigger */
  triggerDxfPicker: () => void;
}

type UploadState = "idle" | "uploading" | "parsing" | "error";

/**
 * CanvasUploader component.
 * Implements a premium, high-fidelity DXF drawing staging and guidelines UX.
 * Allows structural engineers to stage their primary DXF drawing, review detailed CAD guidelines
 * to ensure parsing success, and trigger the classification pipeline.
 *
 * @param {CanvasUploaderProps} props - Component properties.
 * @param {React.Ref<CanvasUploaderHandle>} ref - Exposed handler interface.
 * @returns {React.ReactElement} The rendered drag-and-drop file uploader staging zone.
 */
export const CanvasUploader = forwardRef<CanvasUploaderHandle, CanvasUploaderProps>(
  function CanvasUploader({ projectId, onParsed, onUploadStart }, ref): React.ReactElement {
    const [uploadState, setUploadState] = useState<UploadState>("idle");
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);

    // Staged DXF file state
    const [stagedDxf, setStagedDxf] = useState<File | null>(null);

    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [progressPct, setProgressPct] = useState<number>(0);
    const [currentStep, setCurrentStep] = useState<string>("Initializing vision agent...");

    // Input trigger ref
    const dxfInputRef = useRef<HTMLInputElement>(null);

    // Establish dynamic WebSocket connection for live progress updates
    useProjectSocket(projectId, {
      onJobUpdate: (msg) => {
        if (activeJobId && msg.job_id === activeJobId) {
          if (msg.status === "complete") {
            onParsed().then(() => {
              setUploadState("idle");
              setActiveJobId(null);
            });
          } else if (msg.status === "failed") {
            setUploadError((msg.errors ?? [])[0] ?? "Parsing failed.");
            setUploadState("error");
            setActiveJobId(null);
          } else {
            setProgressPct(msg.progress_pct);
            setCurrentStep(msg.current_step);
          }
        }
      },
    });

    // Expose control API to parent components
    useImperativeHandle(ref, () => ({
      triggerDxfPicker: () => {
        dxfInputRef.current?.click();
      },
    }));

    /**
     * Stages the selected drawing file, validating the DXF format.
     *
     * @param {FileList} files - The selected or dropped list of files.
     */
    const stageFiles = useCallback((files: FileList) => {
      setUploadError(null);
      Array.from(files).forEach((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        if (ext === "dxf") {
          setStagedDxf(file);
        } else {
          setUploadError("Unsupported file type. Please upload a .dxf drawing.");
        }
      });
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback(() => setIsDragOver(false), []);

    const handleDrop = useCallback(
      (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        if (e.dataTransfer.files) stageFiles(e.dataTransfer.files);
      },
      [stageFiles],
    );

    const handleDxfChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) stageFiles(e.target.files);
    };

    const handleRemoveDxf = (e: React.MouseEvent) => {
      e.stopPropagation();
      setStagedDxf(null);
    };

    /**
     * Initiates DXF form upload and registers the job ID to trigger WebSocket progress updates.
     */
    const handleUploadAndParse = async () => {
      if (!stagedDxf) {
        setUploadError("A primary DXF drawing file is required to initiate geometry extraction.");
        return;
      }

      onUploadStart?.();
      setUploadState("uploading");
      setUploadError(null);
      setProgressPct(0);
      setCurrentStep("Uploading drawing file to pipeline...");

      try {
        const form = new FormData();
        form.append("file", stagedDxf);

        const { data: job } = await apiClient.post<{ job_id: string }>(
          `/api/v1/files/upload/${projectId}`,
          form,
          { headers: { "Content-Type": "multipart/form-data" } },
        );

        setActiveJobId(job.job_id);
        setUploadState("parsing");
        setCurrentStep("Waiting for pipeline worker...");
      } catch (err: unknown) {
        setUploadError((err as { detail?: string }).detail ?? "Upload failed.");
        setUploadState("error");
      }
    };

    const handleRetry = () => {
      setUploadState("idle");
      setUploadError(null);
      setActiveJobId(null);
      setProgressPct(0);
      setCurrentStep("Initializing vision agent...");
    };

    const formatSize = (bytes: number): string => {
      if (bytes === 0) return "0 Bytes";
      const k = 1024;
      const sizes = ["Bytes", "KB", "MB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    };

    return (
      <div
        className={cn(
          "absolute inset-0 flex items-center justify-center p-6 bg-[#0b0f19] transition-colors select-none",
          isDragOver && "bg-primary/5",
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Invisible file input trigger */}
        <input
          ref={dxfInputRef}
          type="file"
          accept=".dxf"
          className="hidden"
          onChange={handleDxfChange}
        />

        {uploadState === "idle" && (
          <div
            className={cn(
              "grid grid-cols-1 md:grid-cols-12 gap-8 p-8 rounded-xl border border-border/60 bg-card/25 backdrop-blur-md shadow-2xl max-w-5xl w-full transition-all",
              isDragOver && "border-primary/45 bg-primary/2 scale-[1.01]"
            )}
          >
            {/* Left Column: File Drop & Actions */}
            <div className="md:col-span-5 flex flex-col justify-between gap-6 border-b md:border-b-0 md:border-r border-border/40 pb-6 md:pb-0 md:pr-8">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold tracking-wider uppercase font-mono text-primary">
                  Initialize Workspace
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Drag and drop your CAD drawing or click the zone to select. A valid DXF file is required to build the 3D geometry.
                </p>
              </div>

              {/* DXF Card Zone */}
              <div
                onClick={() => !stagedDxf && dxfInputRef.current?.click()}
                className={cn(
                  "relative group flex flex-col items-center justify-center gap-4 p-8 rounded-lg border-2 border-dashed transition-all cursor-pointer min-h-[160px]",
                  stagedDxf
                    ? "border-green-500/40 bg-green-500/3 cursor-default"
                    : isDragOver
                      ? "border-primary bg-primary/5 scale-102"
                      : "border-border/80 hover:border-primary/50 hover:bg-muted/10",
                )}
              >
                {stagedDxf ? (
                  <>
                    <div className="h-12 w-12 rounded-full bg-green-500/10 flex items-center justify-center text-green-400">
                      <CheckCircle2 className="h-6 w-6 animate-pulse" />
                    </div>
                    <div className="text-center min-w-0 w-full px-2">
                      <p className="text-xs font-semibold font-mono truncate text-green-400">
                        {stagedDxf.name}
                      </p>
                      <p className="text-[10px] text-muted-foreground font-mono mt-1">
                        CAD DXF Model • {formatSize(stagedDxf.size)}
                      </p>
                    </div>
                    <button
                      onClick={handleRemoveDxf}
                      className="absolute top-3 right-3 p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      title="Remove File"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="h-12 w-12 rounded-full bg-muted/45 flex items-center justify-center text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                      <Upload className="h-5 w-5" />
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-semibold">CAD Drawing (.DXF)</p>
                      <p className="text-[10px] text-muted-foreground mt-1 uppercase tracking-wider font-mono font-bold">
                        Drop file here
                      </p>
                    </div>
                  </>
                )}
              </div>

              {/* Action Trigger */}
              <div className="space-y-3 pt-4 border-t border-border/60">
                <button
                  onClick={handleUploadAndParse}
                  disabled={!stagedDxf}
                  className="w-full py-3 bg-primary text-primary-foreground text-xs font-bold tracking-wider uppercase rounded-lg hover:bg-primary/95 transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Upload className="h-4 w-4" />
                  Parse CAD Geometry
                </button>
                {uploadError && (
                  <div className="flex items-center gap-1.5 justify-center text-xs text-destructive font-mono">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    <span>{uploadError}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Detailed CAD Guidelines */}
            <div className="md:col-span-7 flex flex-col gap-6 pl-0 md:pl-4">
              <div className="space-y-1">
                <h4 className="text-xs font-bold tracking-wider uppercase font-mono text-[#00ffff]">
                  DXF Drawing Guidelines
                </h4>
                <p className="text-[11px] text-muted-foreground">
                  Follow these specifications to ensure high-accuracy automated geometry classification:
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 overflow-y-auto max-h-[350px] pr-2 scrollbar-thin">
                {/* Guideline 1 */}
                <div className="p-3.5 rounded-lg border border-border/40 bg-muted/5 flex gap-3.5 items-start">
                  <div className="p-2 rounded bg-amber-500/10 text-amber-400 mt-0.5 font-mono text-xs font-bold shrink-0">01</div>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">Separate Layout Sheets</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Place different floor plans on separate **DXF Layout tabs** (e.g. Ground Floor, First Floor). Drawings placed side-by-side in Model space will be rejected.
                    </p>
                  </div>
                </div>

                {/* Guideline 2 */}
                <div className="p-3.5 rounded-lg border border-border/40 bg-muted/5 flex gap-3.5 items-start">
                  <div className="p-2 rounded bg-amber-500/10 text-amber-400 mt-0.5 font-mono text-xs font-bold shrink-0">02</div>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">Layer Naming Conventions</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Members must reside on designated layers: Beams on <code className="text-amber-300 font-mono">beam*</code>, Columns on <code className="text-amber-300 font-mono">column*</code> or <code className="text-amber-300 font-mono">c-column*</code>, Slabs on <code className="text-amber-300 font-mono">slab*</code>, and Walls on <code className="text-amber-300 font-mono">wall*</code>.
                    </p>
                  </div>
                </div>

                {/* Guideline 3 */}
                <div className="p-3.5 rounded-lg border border-border/40 bg-muted/5 flex gap-3.5 items-start">
                  <div className="p-2 rounded bg-amber-500/10 text-amber-400 mt-0.5 font-mono text-xs font-bold shrink-0">03</div>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">Consistent Drawing Units</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Ensure the entire drawing uses a uniform scale: either **millimeters (mm)** or **meters (m)**. Mixed units or incorrect coordinate scaling will cause calculation failures.
                    </p>
                  </div>
                </div>

                {/* Guideline 4 */}
                <div className="p-3.5 rounded-lg border border-border/40 bg-muted/5 flex gap-3.5 items-start">
                  <div className="p-2 rounded bg-amber-500/10 text-amber-400 mt-0.5 font-mono text-xs font-bold shrink-0">04</div>
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-foreground">Vertical Centroid Alignment</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Columns that stack vertically must share identical XY coordinates. The system links columns with a tolerance of **300mm** to establish load path stacks.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Parse/Upload Spinner */}
        {(uploadState === "uploading" || uploadState === "parsing") && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/25 backdrop-blur-xs">
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="h-10 w-10 text-primary animate-spin" />
              <p className="text-sm font-medium">
                {uploadState === "uploading"
                  ? "Uploading drawing file to pipeline…"
                  : `Classifying Geometry (${progressPct.toFixed(0)}%)…`}
              </p>
              <p className="text-xs text-muted-foreground font-mono">
                {currentStep}
              </p>
            </div>
          </div>
        )}

        {/* Error Alert Display */}
        {uploadState === "error" && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-4 max-w-sm text-center bg-card/60 p-6 rounded-xl border border-border backdrop-blur-sm">
              <AlertCircle className="h-10 w-10 text-destructive" />
              <p className="text-sm font-medium text-destructive">{uploadError}</p>
              <button
                onClick={handleRetry}
                className="px-4 py-2 bg-muted text-foreground text-sm rounded-lg hover:bg-muted/80 transition-colors"
              >
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    );
  },
);

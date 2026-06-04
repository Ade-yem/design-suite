"use client";

import * as React from "react";
import { useState, useCallback, useRef, forwardRef, useImperativeHandle } from "react";
import {
  Upload,
  FileUp,
  FileText,
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
 * Implements a premium, high-fidelity double-file staging area UX.
 * Allows structural engineers to stage both the Required primary DXF drawing and
 * the Optional reference PDF, verifying their metadata before triggering vision parsing.
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

    // Staged files local state
    const [stagedDxf, setStagedDxf] = useState<File | null>(null);
    const [stagedPdf, setStagedPdf] = useState<File | null>(null);

    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [progressPct, setProgressPct] = useState<number>(0);
    const [currentStep, setCurrentStep] = useState<string>("Initializing vision agent...");

    // Input triggers refs
    const dxfInputRef = useRef<HTMLInputElement>(null);
    const pdfInputRef = useRef<HTMLInputElement>(null);

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
     * Sorts and stages files into their respective DXF or PDF slot based on file extensions.
     *
     * @param {FileList} files - The selected or dropped list of files.
     */
    const stageFiles = useCallback((files: FileList) => {
      setUploadError(null);
      Array.from(files).forEach((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        if (ext === "dxf") {
          setStagedDxf(file);
        } else if (ext === "pdf") {
          setStagedPdf(file);
        } else {
          setUploadError("Unsupported file type. Please upload a .dxf or .pdf drawing.");
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

    const handlePdfChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) stageFiles(e.target.files);
    };

    const handleRemoveDxf = (e: React.MouseEvent) => {
      e.stopPropagation();
      setStagedDxf(null);
    };

    const handleRemovePdf = (e: React.MouseEvent) => {
      e.stopPropagation();
      setStagedPdf(null);
    };

    /**
     * Initiates multi-file form upload and registers the job ID to trigger WebSocket progress updates.
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
      setCurrentStep("Uploading drawing files to pipeline...");

      try {
        const form = new FormData();
        form.append("file", stagedDxf);
        if (stagedPdf) {
          form.append("pdf_file", stagedPdf);
        }

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
        {/* Invisible file input triggers */}
        <input
          ref={dxfInputRef}
          type="file"
          accept=".dxf"
          className="hidden"
          onChange={handleDxfChange}
        />
        <input
          ref={pdfInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handlePdfChange}
        />

        {uploadState === "idle" && (
          <div
            className={cn(
              "flex flex-col items-center gap-6 p-8 rounded-xl border-2 border-dashed transition-all bg-card/40 backdrop-blur-sm shadow-md max-w-2xl w-full",
              isDragOver
                ? "border-primary bg-primary/5 scale-102"
                : "border-border hover:border-muted-foreground",
            )}
          >
            <div className="text-center space-y-1">
              <h3 className="text-sm font-semibold tracking-wide uppercase font-mono text-primary">
                Initialize Drawing Workspace
              </h3>
              <p className="text-xs text-muted-foreground max-w-md">
                Drag and drop your structural drawing files or click cards to browse.
                A DXF vector file is required to build the geometry nodes.
              </p>
            </div>

            {/* Staging grids */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
              {/* DXF Card (Required) */}
              <div
                onClick={() => !stagedDxf && dxfInputRef.current?.click()}
                className={cn(
                  "relative group flex flex-col items-center justify-center gap-3 p-6 rounded-lg border border-dashed transition-all cursor-pointer bg-muted/20",
                  stagedDxf
                    ? "border-green-500/35 bg-green-500/5 cursor-default"
                    : "border-border hover:border-primary/50 hover:bg-muted/40",
                )}
              >
                {stagedDxf ? (
                  <>
                    <div className="h-10 w-10 rounded-full bg-green-500/10 flex items-center justify-center text-green-400">
                      <CheckCircle2 className="h-5 w-5" />
                    </div>
                    <div className="text-center min-w-0 w-full px-2">
                      <p className="text-xs font-semibold font-mono truncate text-green-400">
                        {stagedDxf.name}
                      </p>
                      <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
                        DXF Model • {formatSize(stagedDxf.size)}
                      </p>
                    </div>
                    <button
                      onClick={handleRemoveDxf}
                      className="absolute top-2 right-2 p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      title="Remove File"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                      <Upload className="h-4 w-4" />
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-semibold">CAD Drawing (.DXF)</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5 uppercase tracking-wider font-mono font-bold">
                        Required
                      </p>
                    </div>
                  </>
                )}
              </div>

              {/* PDF Card (Optional) */}
              <div
                onClick={() => !stagedPdf && pdfInputRef.current?.click()}
                className={cn(
                  "relative group flex flex-col items-center justify-center gap-3 p-6 rounded-lg border border-dashed transition-all cursor-pointer bg-muted/20",
                  stagedPdf
                    ? "border-primary/35 bg-primary/5 cursor-default"
                    : "border-border hover:border-primary/50 hover:bg-muted/40",
                )}
              >
                {stagedPdf ? (
                  <>
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <FileText className="h-5 w-5" />
                    </div>
                    <div className="text-center min-w-0 w-full px-2">
                      <p className="text-xs font-semibold font-mono truncate text-primary">
                        {stagedPdf.name}
                      </p>
                      <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
                        Reference PDF • {formatSize(stagedPdf.size)}
                      </p>
                    </div>
                    <button
                      onClick={handleRemovePdf}
                      className="absolute top-2 right-2 p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      title="Remove File"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                      <FileUp className="h-4 w-4" />
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-semibold">Architectural PDF</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5 uppercase tracking-wider font-mono">
                        Optional Overlay
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Action Trigger */}
            <div className="w-full flex flex-col gap-2 pt-2 border-t border-border/60">
              <button
                onClick={handleUploadAndParse}
                disabled={!stagedDxf}
                className="w-full py-2.5 bg-primary text-primary-foreground text-sm font-semibold rounded-lg hover:bg-primary/90 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                <Upload className="h-4 w-4" />
                Initialize AI Geometry Classifier
              </button>
              {uploadError && (
                <div className="flex items-center gap-1.5 justify-center text-xs text-destructive font-mono mt-1">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}
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
                  ? "Uploading drawing files to pipeline…"
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

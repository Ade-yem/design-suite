"use client";

import { useState, useCallback, useRef, forwardRef, useImperativeHandle } from "react";
import {
  Upload,
  FileUp,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Move,
  MousePointer,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";
import type { JobStatus } from "@/types/project";

export interface CanvasViewportHandle {
  triggerFilePicker: () => void;
}

interface ParsedGeometrySummary {
  memberCount: number;
  scale: { factor: number; unit: string };
}

interface CanvasViewportProps {
  projectId: string;
  onParsed?: (summary: ParsedGeometrySummary) => void;
  onUploadStart?: () => void;
}

type UploadState = "idle" | "uploading" | "parsing" | "done" | "error";

const POLL_INTERVAL_MS = 2000;
const ACCEPTED_EXTS = [".dxf", ".pdf"];

export const CanvasViewport = forwardRef<CanvasViewportHandle, CanvasViewportProps>(
  function CanvasViewport({ projectId, onParsed, onUploadStart }, ref) {
    const [isDragOver, setIsDragOver] = useState(false);
    const [uploadState, setUploadState] = useState<UploadState>("idle");
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [parsedSummary, setParsedSummary] = useState<ParsedGeometrySummary | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useImperativeHandle(ref, () => ({
      triggerFilePicker: () => fileInputRef.current?.click(),
    }));

    const uploadAndParse = useCallback(
      async (file: File) => {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        if (!ACCEPTED_EXTS.includes(`.${ext}`)) {
          setUploadError("Unsupported file type. Please upload a .dxf or .pdf file.");
          setUploadState("error");
          return;
        }

        onUploadStart?.();
        setUploadState("uploading");
        setUploadError(null);

        try {
          const form = new FormData();
          form.append("file", file);

          const { data: job } = await apiClient.post<{ job_id: string }>(
            `/api/v1/files/upload/${projectId}`,
            form,
            { headers: { "Content-Type": "multipart/form-data" } }
          );

          setUploadState("parsing");

          const poll = async () => {
            try {
              const { data: status } = await apiClient.get<JobStatus>(
                `/api/v1/jobs/${job.job_id}`
              );

              if (status.status === "complete") {
                let summary: ParsedGeometrySummary = { memberCount: 0, scale: { factor: 1, unit: "mm" } };
                if (status.result_url) {
                  try {
                    const { data: parsed } = await apiClient.get<{
                      members: unknown[];
                      scale: { factor: number; unit: string };
                    }>(status.result_url);
                    summary = {
                      memberCount: (parsed.members ?? []).length,
                      scale: parsed.scale ?? { factor: 1, unit: "mm" },
                    };
                  } catch {
                    // result_url fetch failed; proceed with empty summary
                  }
                }
                setParsedSummary(summary);
                setUploadState("done");
                onParsed?.(summary);
              } else if (status.status === "failed") {
                setUploadError((status.errors ?? [])[0] ?? "Parsing failed.");
                setUploadState("error");
              } else {
                pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
              }
            } catch {
              setUploadError("Lost connection while checking parse status. Please retry.");
              setUploadState("error");
            }
          };

          await poll();
        } catch (err: unknown) {
          setUploadError((err as { detail?: string }).detail ?? "Upload failed.");
          setUploadState("error");
        }
      },
      [projectId, onParsed, onUploadStart]
    );

    const handleDragOver = useCallback((e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(true);
    }, []);

    const handleDragLeave = useCallback(() => setIsDragOver(false), []);

    const handleDrop = useCallback(
      (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) uploadAndParse(file);
      },
      [uploadAndParse]
    );

    const handleFileInput = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) uploadAndParse(file);
      },
      [uploadAndParse]
    );

    const handleRetry = () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
      setUploadState("idle");
      setUploadError(null);
      setParsedSummary(null);
    };

    return (
      <div className="h-full flex flex-col relative">
        {/* Toolbar */}
        <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-1">
          {[
            { icon: MousePointer, label: "Select" },
            { icon: Move, label: "Pan" },
            { icon: ZoomIn, label: "Zoom In" },
            { icon: ZoomOut, label: "Zoom Out" },
            { icon: Maximize2, label: "Fit" },
          ].map(({ icon: Icon, label }) => (
            <button
              key={label}
              title={label}
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>

        {/* Coordinates */}
        <div className="absolute bottom-3 left-3 z-10 flex items-center gap-3 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-1.5">
          <span className="text-xs font-mono text-muted-foreground">
            X: <span className="text-foreground">0.000</span>
          </span>
          <span className="text-xs font-mono text-muted-foreground">
            Y: <span className="text-foreground">0.000</span>
          </span>
          <div className="w-px h-3 bg-border" />
          <span className="text-xs font-mono text-muted-foreground">
            Scale:{" "}
            <span className="text-foreground">
              {parsedSummary ? `1 ${parsedSummary.scale.unit}` : "—"}
            </span>
          </span>
        </div>

        {/* Canvas Area */}
        <div
          className={cn(
            "flex-1 dot-grid bg-canvas-bg relative transition-colors",
            isDragOver && "bg-primary/5"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".dxf,.pdf"
            className="hidden"
            onChange={handleFileInput}
          />

          {uploadState === "idle" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className={cn(
                  "flex flex-col items-center gap-4 p-10 rounded-xl border-2 border-dashed transition-all",
                  isDragOver
                    ? "border-primary bg-primary/5 scale-105"
                    : "border-border hover:border-muted-foreground"
                )}
              >
                <div
                  className={cn(
                    "h-16 w-16 rounded-xl flex items-center justify-center transition-colors",
                    isDragOver ? "bg-primary/15" : "bg-muted"
                  )}
                >
                  {isDragOver ? (
                    <FileUp className="h-8 w-8 text-primary" />
                  ) : (
                    <Upload className="h-8 w-8 text-muted-foreground" />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">
                    {isDragOver ? "Drop DXF or PDF here" : "Upload Drawing"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Drag and drop or click to browse
                  </p>
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors"
                >
                  Browse Files
                </button>
                <p className="text-xs text-muted-foreground font-mono">.dxf, .pdf supported</p>
              </div>
            </div>
          )}

          {(uploadState === "uploading" || uploadState === "parsing") && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-4">
                <Loader2 className="h-10 w-10 text-primary animate-spin" />
                <p className="text-sm font-medium">
                  {uploadState === "uploading" ? "Uploading file…" : "AI parsing geometry…"}
                </p>
                <p className="text-xs text-muted-foreground font-mono">
                  {uploadState === "parsing"
                    ? "Extracting members, spans, and section data"
                    : "Transferring to server"}
                </p>
              </div>
            </div>
          )}

          {uploadState === "error" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-4 max-w-sm text-center">
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

          {uploadState === "done" && parsedSummary && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-2">
                <p className="text-sm text-muted-foreground font-mono">
                  Drawing renderer coming in Phase 5
                </p>
                <p className="text-xs text-muted-foreground">
                  Parsed geometry is ready for analysis.
                </p>
              </div>

              <div className="absolute top-4 left-4 flex items-center gap-2 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />
                <span className="text-xs font-medium">Parsing Complete</span>
                <span className="text-xs font-mono text-muted-foreground">
                  · {parsedSummary.memberCount} member
                  {parsedSummary.memberCount !== 1 ? "s" : ""} detected
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }
);

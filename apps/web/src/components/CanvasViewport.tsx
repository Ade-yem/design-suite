import { useState, useCallback } from "react";
import { Upload, FileUp, ZoomIn, ZoomOut, Maximize2, Move, MousePointer } from "lucide-react";
import { cn } from "@/lib/utils";

export function CanvasViewport() {
  const [isDragOver, setIsDragOver] = useState(false);
  const [hasFile, setHasFile] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    // Simulate file upload
    setHasFile(true);
  }, []);

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
          Scale: <span className="text-foreground">1:100</span>
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
        {!hasFile ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div
              className={cn(
                "flex flex-col items-center gap-4 p-10 rounded-xl border-2 border-dashed transition-all",
                isDragOver
                  ? "border-primary bg-primary/5 scale-105"
                  : "border-border hover:border-muted-foreground"
              )}
            >
              <div className={cn(
                "h-16 w-16 rounded-xl flex items-center justify-center transition-colors",
                isDragOver ? "bg-primary/15" : "bg-muted"
              )}>
                {isDragOver ? (
                  <FileUp className="h-8 w-8 text-primary" />
                ) : (
                  <Upload className="h-8 w-8 text-muted-foreground" />
                )}
              </div>
              <div className="text-center">
                <p className="text-sm font-medium">
                  {isDragOver ? "Drop DXF file here" : "Upload DXF File"}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Drag and drop or click to browse
                </p>
              </div>
              <button
                onClick={() => setHasFile(true)}
                className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors"
              >
                Browse Files
              </button>
              <p className="text-xs text-muted-foreground font-mono">.dxf, .dwg supported</p>
            </div>
          </div>
        ) : (
          <DemoGeometry />
        )}
      </div>
    </div>
  );
}

function DemoGeometry() {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <svg viewBox="0 0 600 400" className="w-[80%] h-[70%] opacity-90">
        {/* Grid lines - subtle */}
        {Array.from({ length: 7 }).map((_, i) => (
          <line key={`gv-${i}`} x1={80 + i * 80} y1={40} x2={80 + i * 80} y2={360} stroke="hsl(217, 33%, 15%)" strokeWidth="0.5" strokeDasharray="4 4" />
        ))}
        {Array.from({ length: 5 }).map((_, i) => (
          <line key={`gh-${i}`} x1={40} y1={60 + i * 70} x2={560} y2={60 + i * 70} stroke="hsl(217, 33%, 15%)" strokeWidth="0.5" strokeDasharray="4 4" />
        ))}

        {/* Beams - engineering blue */}
        <line x1={100} y1={100} x2={300} y2={100} stroke="hsl(217, 91%, 60%)" strokeWidth="3" />
        <line x1={300} y1={100} x2={500} y2={100} stroke="hsl(217, 91%, 60%)" strokeWidth="3" />
        <line x1={100} y1={250} x2={300} y2={250} stroke="hsl(217, 91%, 60%)" strokeWidth="3" />
        <line x1={300} y1={250} x2={500} y2={250} stroke="hsl(217, 91%, 60%)" strokeWidth="3" />

        {/* Columns */}
        {[100, 300, 500].map((x) =>
          [100, 250].map((y) => (
            <g key={`col-${x}-${y}`}>
              <rect x={x - 8} y={y - 8} width={16} height={16} fill="hsl(217, 91%, 60%)" fillOpacity={0.3} stroke="hsl(217, 91%, 60%)" strokeWidth="2" />
              <circle cx={x} cy={y} r={2} fill="hsl(217, 91%, 60%)" />
            </g>
          ))
        )}

        {/* Labels */}
        <text x={200} y={90} fill="hsl(217, 91%, 60%)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle" opacity={0.8}>B-01</text>
        <text x={400} y={90} fill="hsl(217, 91%, 60%)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle" opacity={0.8}>B-02</text>
        <text x={200} y={270} fill="hsl(217, 91%, 60%)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle" opacity={0.8}>B-03</text>
        <text x={400} y={270} fill="hsl(217, 91%, 60%)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle" opacity={0.8}>B-04</text>

        <text x={85} y={95} fill="hsl(142, 71%, 45%)" fontSize="9" fontFamily="JetBrains Mono" textAnchor="end">C-01</text>
        <text x={85} y={245} fill="hsl(142, 71%, 45%)" fontSize="9" fontFamily="JetBrains Mono" textAnchor="end">C-04</text>

        {/* Dimension line */}
        <line x1={100} y1={310} x2={300} y2={310} stroke="hsl(215, 20%, 55%)" strokeWidth="0.8" />
        <line x1={100} y1={305} x2={100} y2={315} stroke="hsl(215, 20%, 55%)" strokeWidth="0.8" />
        <line x1={300} y1={305} x2={300} y2={315} stroke="hsl(215, 20%, 55%)" strokeWidth="0.8" />
        <text x={200} y={325} fill="hsl(215, 20%, 55%)" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle">6000 mm</text>
      </svg>

      {/* Status badge */}
      <div className="absolute top-4 left-4 flex items-center gap-2 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-1.5">
        <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
        <span className="text-xs font-medium">AI Parsing Complete</span>
        <span className="text-xs font-mono text-muted-foreground">· 14 members detected</span>
      </div>
    </div>
  );
}

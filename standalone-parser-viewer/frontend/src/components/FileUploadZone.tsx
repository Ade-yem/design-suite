import * as React from "react";
import { useState, useRef } from "react";
import { Upload, FileCode, FileText, RefreshCw } from "lucide-react";
import type { ParsedGeometry } from "../lib/canvas-drawing";
import { normalizeBackendMember } from "../lib/canvas-drawing";


interface FileUploadZoneProps {
  onUploadStart: () => void;
  onUploadComplete: (data: ParsedGeometry) => void;
  onUploadError: (err: string) => void;
}

export function FileUploadZone({
  onUploadStart,
  onUploadComplete,
  onUploadError,
}: FileUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [dxfFile, setDxfFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const dxfInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const processDroppedFiles = (files: FileList) => {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file.name.toLowerCase().endsWith(".dxf")) {
        setDxfFile(file);
      } else if (file.name.toLowerCase().endsWith(".pdf")) {
        setPdfFile(file);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files) {
      processDroppedFiles(e.dataTransfer.files);
    }
  };

  const handleDxfChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setDxfFile(e.target.files[0]);
    }
  };

  const handlePdfChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setPdfFile(e.target.files[0]);
    }
  };

  const handleClear = () => {
    setDxfFile(null);
    setPdfFile(null);
  };

  const handleUpload = async () => {
    if (!dxfFile) return;

    setLoading(true);
    onUploadStart();

    const formData = new FormData();
    formData.append("dxf_file", dxfFile);
    if (pdfFile) {
      formData.append("pdf_file", pdfFile);
    }

    try {
      const response = await fetch("http://localhost:8002/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errJson = await response.json();
        throw new Error(errJson.detail || "Server failed to process files.");
      }

      const rawData = await response.json();

      const normalizedMembers = (rawData.members || []).map((m: any) =>
        normalizeBackendMember(m)
      );

      const parsedData: ParsedGeometry = {
        members: normalizedMembers,
        scale: rawData.scale || { factor: 0.001, unit: "mm", detected: false, confirmed: false },
        raw_entity_count: rawData.raw_entity_count,
        parse_warnings: rawData.parse_warnings,
        filenames: rawData.filenames,
      };

      onUploadComplete(parsedData);
    } catch (err: any) {
      onUploadError(err.message || "An error occurred during file parsing.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container">
      {/* Dropzone area */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`dropzone ${isDragOver ? "dragover" : ""}`}
        onClick={() => dxfInputRef.current?.click()}
      >
        <input
          ref={dxfInputRef}
          type="file"
          accept=".dxf"
          onChange={handleDxfChange}
          className="hidden"
        />
        
        <Upload style={{ color: "#64748b", marginBottom: "0.75rem" }} size={32} />
        <h3 className="dropzone-title">Upload DXF Drawing File</h3>
        <p className="dropzone-desc">
          Drag and drop your CAD drawing here, or click to browse. DXF file is required.
        </p>
      </div>

      {/* PDF Reference block (Optional) */}
      <div
        className="pdf-attach-bar"
        onClick={() => pdfInputRef.current?.click()}
      >
        <input
          ref={pdfInputRef}
          type="file"
          accept=".pdf"
          onChange={handlePdfChange}
          className="hidden"
        />
        <div className="pdf-info">
          <FileText style={{ color: "#64748b" }} size={20} />
          <div>
            <h4 className="pdf-title">Attach PDF Reference</h4>
            <p className="pdf-desc">Optional PDF file for slab and void extraction</p>
          </div>
        </div>
        <span className="badge-optional">OPTIONAL</span>
      </div>

      {/* File status */}
      {(dxfFile || pdfFile) && (
        <div className="staged-files-card">
          <h4 className="staged-header">Files Staged</h4>
          
          {dxfFile && (
            <div className="staged-file-row">
              <div className="file-name-container">
                <FileCode style={{ color: "#6366f1" }} size={16} />
                <span className="file-name-text" title={dxfFile.name}>
                  {dxfFile.name}
                </span>
              </div>
              <span className="file-size-text">
                {(dxfFile.size / 1024).toFixed(1)} KB
              </span>
            </div>
          )}

          {pdfFile && (
            <div className="staged-file-row">
              <div className="file-name-container">
                <FileText style={{ color: "#10b981" }} size={16} />
                <span className="file-name-text" title={pdfFile.name}>
                  {pdfFile.name}
                </span>
              </div>
              <span className="file-size-text">
                {(pdfFile.size / 1024).toFixed(1)} KB
              </span>
            </div>
          )}

          <div className="button-group">
            <button
              disabled={loading}
              onClick={handleUpload}
              className="btn-primary"
            >
              {loading ? (
                <>
                  <RefreshCw size={12} className="animate-spin" />
                  Parsing...
                </>
              ) : (
                "Parse Drawing"
              )}
            </button>
            <button
              disabled={loading}
              onClick={handleClear}
              className="btn-secondary"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import { FileUploadZone } from "./components/FileUploadZone";
import { CanvasViewport } from "./components/CanvasViewport";
import type { ParsedGeometry } from "./lib/canvas-drawing";
import {
  FileSpreadsheet,
  AlertCircle,
  Database,
  Layers,
  ChevronRight,
  Sparkles,
} from "lucide-react";

export default function App() {
  const [geometry, setGeometry] = useState<ParsedGeometry | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingCache, setLoadingCache] = useState(true);

  // Fetch cached geometry on load
  useEffect(() => {
    async function loadCache() {
      try {
        const response = await fetch("http://localhost:8002/api/parsed");
        if (response.ok) {
          const cachedData = await response.json();
          const { normalizeBackendMember } = await import("./lib/canvas-drawing");
          const normalizedMembers = (cachedData.members || []).map((m: any) =>
            normalizeBackendMember(m)
          );
          
          setGeometry({
            ...cachedData,
            members: normalizedMembers,
          });
        }
      } catch (err) {
        // Cache empty or offline
      } finally {
        setLoadingCache(false);
      }
    }
    loadCache();
  }, []);

  const handleUploadStart = () => {
    setError(null);
    setGeometry(null);
    setSelectedMemberId(null);
  };

  const handleUploadComplete = (data: ParsedGeometry) => {
    setGeometry(data);
    setError(null);
  };

  const handleUploadError = (err: string) => {
    setError(err);
  };

  const selectedMember = geometry?.members.find(
    (m) => m.member_id === selectedMemberId
  );

  return (
    <div className="app-container">
      {/* Sidebar Control Panel (Left) */}
      <div className="sidebar">
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-icon">
            <Sparkles size={20} />
          </div>
          <div className="sidebar-title">
            <h1>Geometry Parser & Viewer</h1>
            <p>Standalone Test Sandbox (No DB / Local Cache)</p>
          </div>
        </div>

        {/* Content Area */}
        <div className="sidebar-content">
          {/* File Upload zone */}
          <FileUploadZone
            onUploadStart={handleUploadStart}
            onUploadComplete={handleUploadComplete}
            onUploadError={handleUploadError}
          />

          {/* Errors */}
          {error && (
            <div className="alert-error">
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
              <div>
                <h5>Parsing Failed</h5>
                <p>{error}</p>
              </div>
            </div>
          )}

          {/* Loading Cache Status */}
          {loadingCache && (
            <div style={{ padding: "0.5rem 0", textAlign: "center", fontSize: "0.75rem", color: "#64748b", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}>
              <Database size={12} className="animate-pulse" />
              Checking persistent local cache...
            </div>
          )}

          {/* Geometry Statistics & Info */}
          {geometry && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {/* Parse Meta Card */}
              <div className="stats-card">
                <div className="stats-row">
                  <span>File Parsed:</span>
                  <span className="stats-value-mono" style={{ textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap", maxWidth: "180px" }} title={geometry.filenames?.dxf}>
                    {geometry.filenames?.dxf}
                  </span>
                </div>
                {geometry.filenames?.pdf && (
                  <div className="stats-row">
                    <span>PDF Reference:</span>
                    <span className="stats-value-mono" style={{ textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap", maxWidth: "180px" }} title={geometry.filenames?.pdf}>
                      {geometry.filenames?.pdf}
                    </span>
                  </div>
                )}
                <div className="stats-row">
                  <span>Detected Members:</span>
                  <span className="stats-value-bold">
                    {geometry.members.length}
                  </span>
                </div>
                <div className="stats-row">
                  <span>Scale Factor:</span>
                  <span className="stats-value-mono">
                    {geometry.scale.factor} ({geometry.scale.unit})
                  </span>
                </div>
              </div>

              {/* Warnings List */}
              {geometry.parse_warnings && geometry.parse_warnings.length > 0 && (
                <div className="alert-warning">
                  <div className="warning-header">
                    <AlertCircle size={12} />
                    <span>Parse Warnings</span>
                  </div>
                  <ul className="warning-list">
                    {geometry.parse_warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Selected Member Detail */}
              {selectedMember ? (
                <div className="inspector-card">
                  <div className="inspector-header">
                    <h3 className="inspector-title">
                      <Layers size={12} style={{ color: "#6366f1" }} />
                      Selected: {selectedMember.member_id}
                    </h3>
                    <span className="inspector-badge">
                      {selectedMember.member_type}
                    </span>
                  </div>

                  <div className="inspector-grid">
                    <div className="inspector-grid-cell">
                      <span className="cell-label">Start Point</span>
                      <span className="cell-value-mono">
                        X: {Math.round(selectedMember.start.x)}, Y: {Math.round(selectedMember.start.y)}
                      </span>
                    </div>
                    <div className="inspector-grid-cell">
                      <span className="cell-label">End Point</span>
                      <span className="cell-value-mono">
                        X: {Math.round(selectedMember.end.x)}, Y: {Math.round(selectedMember.end.y)}
                      </span>
                    </div>
                  </div>

                  {selectedMember.meta && (
                    <div className="metadata-box">
                      <span className="cell-label" style={{ marginBottom: "0.25rem" }}>Metadata Attributes</span>
                      <div className="metadata-grid">
                        {Object.entries(selectedMember.meta).map(([key, val]) => (
                          <div key={key} className="metadata-row">
                            <span className="metadata-key">{key}:</span>
                            <span>{String(val)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ backgroundColor: "rgba(30, 41, 59, 0.2)", border: "1px solid #1e293b", borderRadius: "0.5rem", padding: "1rem", textAlign: "center", fontSize: "0.75rem", color: "#64748b" }}>
                  Click on any member in the canvas viewport to inspect its properties.
                </div>
              )}

              {/* Members List */}
              <div className="list-section">
                <h3 className="list-header-title">
                  Parsed Entities ({geometry.members.length})
                </h3>
                <div className="entities-list-box">
                  {geometry.members.map((m) => (
                    <button
                      key={m.member_id}
                      onClick={() => setSelectedMemberId(m.member_id)}
                      className={`entity-row-btn ${m.member_id === selectedMemberId ? "selected" : ""}`}
                    >
                      <span className="entity-id-text">{m.member_id}</span>
                      <span className="entity-type-badge">{m.member_type}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* JSON View Accordion */}
              <div className="list-section">
                <h3 className="list-header-title">Raw Output JSON</h3>
                <pre className="json-view-pre">
                  {JSON.stringify(geometry, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main CAD Viewport Area (Right) */}
      <div className="main-content">
        {geometry ? (
          <div className="viewport-layout">
            <div className="viewport-header">
              <div className="viewport-file-info">
                <FileSpreadsheet size={14} style={{ color: "#6366f1" }} />
                <span className="file-name-main">{geometry.filenames?.dxf}</span>
                {geometry.filenames?.pdf && (
                  <>
                    <ChevronRight size={12} />
                    <span style={{ color: "#64748b" }}>Ref: {geometry.filenames?.pdf}</span>
                  </>
                )}
              </div>
              <span className="badge-active">Interactive Canvas Active</span>
            </div>
            
            <div style={{ flex: 1, position: "relative" }}>
              <CanvasViewport
                members={geometry.members}
                selectedMemberId={selectedMemberId}
                onSelectMember={setSelectedMemberId}
              />
            </div>
          </div>
        ) : (
          <div className="empty-viewport-card">
            <Layers style={{ color: "#334155", marginBottom: "0.75rem" }} size={48} />
            <h2 className="empty-title">No Geometry Loaded</h2>
            <p className="empty-desc">
              Please stage and parse a DXF CAD drawing from the left panel to activate the interactive canvas viewport.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

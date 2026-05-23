# 🎨 UX Integration Design: Embedding the File Explorer inside `ProjectSidebar`

> **Role:** Lead UI/UX Product Designer & Frontend Architect  
> **Status:** UI Strategy & Integration Review (No code changes implemented)  
> **Target:** `ProjectSidebar.tsx` (collapsible Project Panel)

---

## 1. Integration Philosophy: Nested Folder Tree

Since the `ProjectSidebar` already serves as the navigation control center for selecting projects, the most intuitive, VS Code-like approach is to **nest the drawing files directly inside the active project folder card** in the project list.

This creates a clean **parent-child hierarchical directory structure** that engineers understand instantly:

```
📁 PROJECTS
├── 📁 PRJ-A (Office Block)
├── 📂 PRJ-B (Floor Beam Plan)  ◄── The active project expands to reveal child nodes
│   ├── 📐 Floor-beam.dxf     [⬇️] [🔄]
│   └── 📄 Floor-beam.pdf     [⬇️] [👁️]
└── 📁 PRJ-C (Residential GA)
```

---

## 2. Visual Layout Breakdown (Expanded vs. Collapsed)

### A. When Expanded (`w-60`): The Indented Asset Tree

When a project is set to active (i.e. `isActive = true`), we expand a highly-polished, indented **"Reference Assets" section** directly beneath its label card.

```
+────────────────────────────────────────────────────────+
│ 📂 Floor Beam Plan                              (Active)│
│    Ref: PRJ-B012                                       │
│                                                        │
│    ▼  ACTIVE REFERENCE FILES                           │
│       ├── 📐 Floor-beam.dxf      [⬇️ Download]          │
│       │   Size: 2.4 MB  •  Parsed                      │
│       │                                                │
│       └── 📄 Floor-beam.pdf      [⬇️ Download]          │
│           Size: 1.1 MB  •  Linked                      │
+────────────────────────────────────────────────────────+
```

#### UI Tokens & CSS Design:
* **Indentation:** `pl-8 pr-2 py-1.5 ml-4 border-l border-primary/20 bg-muted/20 rounded-md`
* **Icons:** Lucide icons (`FileCode` for DXF, `FileText` for PDF) styled in low-contrast slate colors (`text-muted-foreground`) to establish visual hierarchy.
* **Download Button:** A clean, round, glassmorphic button (`p-1 hover:bg-primary/10 hover:text-primary rounded-md`) that transitions smoothly on hover.

---

### B. When Collapsed (`w-12`): The Floating "Asset Popover"

When the sidebar is collapsed into a 48px rail, we represent the active project as an open folder icon (`FolderOpen` in `primary` blue).

Instead of forcing the user to expand the sidebar to access files, hovering over or clicking the active project icon opens a sleek, floating **Asset Popover** directly next to the rail:

```
  Collapsed Rail      Floating Asset Popover
┌────────────────┐  ┌────────────────────────────────────────┐
│   [StructAI]   │  │ 📂 FLOOR BEAM PLAN (PRJ-B012)          │
├────────────────┤  ├────────────────────────────────────────┤
│      [🔍]      │  │ 📐 Floor-beam.dxf  (2.4 MB)     [⬇️]     │
├────────────────┤  │ 📄 Floor-beam.pdf  (1.1 MB)     [⬇️]     │
│     [Folder]   │  └────────────────────────────────────────┘
│    ► [Active] ───►  (Slides open next to the sidebar on click)
│     [Folder]   │
├────────────────┤
│      [+]       │
└────────────────┘
```

#### Popover Micro-Interactions:
* **Trigger:** Click or Hover on the Active Folder Icon.
* **Position:** Fixed position `absolute left-full top-1/2 -translate-y-1/2 ml-2 z-[60]`.
* **Animation:** Smooth horizontal slide-in and fade transition (`animate-slide-in-right`).
* **Visual Polish:** Glassmorphism overlay (`bg-background/80 backdrop-blur-md border border-border shadow-xl rounded-lg px-3 py-3 w-64`).

---

## 3. Implementation Touchpoints (`ProjectSidebar.tsx`)

When shifting from review to implementation, the code injection will be localized inside the `ProjectSidebar` component rendering loop around **lines 220–251**:

```tsx
// Inside the filtered.map() loop...
return (
  <li key={p.project_id}>
    {sidebarExpanded ? (
      <div>
        <button
          onClick={() => handleOpenProject(p.project_id)}
          className={cn(/* existing active/inactive classnames */)}
        >
          {/* ... existing folder and metadata labels ... */}
        </button>

        {/* 🚀 NESTED ASSET TREE INJECTION */}
        {isActive && (
          <div className="pl-8 pr-2 py-1.5 ml-4 mt-1 space-y-1.5 border-l border-primary/20 bg-muted/10 rounded-md">
            <div className="flex items-center justify-between text-xs text-muted-foreground group/file">
              <span className="truncate">📐 floor-plan.dxf</span>
              <button 
                onClick={() => downloadAsset(p.project_id, 'dxf')}
                className="opacity-0 group-hover/file:opacity-100 p-1 hover:text-primary transition-opacity"
              >
                <Download className="h-3 w-3" />
              </button>
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground group/file">
              <span className="truncate">📄 floor-plan.pdf</span>
              <button 
                onClick={() => downloadAsset(p.project_id, 'pdf')}
                className="opacity-0 group-hover/file:opacity-100 p-1 hover:text-primary transition-opacity"
              >
                <Download className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}
      </div>
    ) : (
      // Collapsed state popover handling...
      <SidebarTooltip label={p.name}>
        {/* ... collapsed folder button ... */}
      </SidebarTooltip>
    )}
  </li>
);
```

---

## 4. Summary of Benefits
1. **Design Continuity:** Works completely within the existing sidebar layout without requiring new page-level grids or layout adjustments.
2. **Unified Navigation:** Keeps all project-specific metadata (Project Name, Reference, Active Drawings) strictly grouped together.
3. **No Added Clutter:** Drawing files are hidden for inactive projects, keeping the view clean.

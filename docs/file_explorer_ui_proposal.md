# 🎨 UI/UX Design Proposal: Project File Explorer & Download Center

> **Role:** Lead UI/UX Product Designer & Frontend Architect  
> **Status:** UI Strategy Proposal (Design & Interaction Phase — No code)  
> **Target:** AI-Driven Structural IDE (Side-by-Side Canvas + Chat Layout)

---

## 1. The Design Philosophy: "Keep the IDE Uncluttered"

In a professional Engineering IDE, **cognitive load** is the single greatest risk. The screen is already packed with:
1. **Left Panel:** Conversational AI thread, agent step status logs, safety gate buttons.
2. **Right Panel:** Highly interactive visual Canvas showing grids, member profiles, and dimensions.

If we drop massive file lists or raw attachment boxes directly into the chat stream, the conversation stream becomes cluttered, and past uploads get lost as the chat history grows.

Therefore, reference assets should be treated as **persistent project infrastructure**, rather than transitory chat messages.

---

## 2. UI Placement Strategies: 3 Visual Proposals

```
┌────────────────────────────────────────────────────────────────────────┐
│                              THE IDE LAYOUT                            │
├────┬─────────────────────────────┬─────────────────────────────────────┤
│ U  │                             │                                     │
│ T  │                             │                                     │
│ I  │         LEFT PANEL          │             RIGHT PANEL             │
│ L  │     (Conversational AI)     │        (Interactive Canvas)         │
│ I  │                             │                                     │
│ T  │                             │                                     │
│ Y  │                             │                                     │
└────┴─────────────────────────────┴─────────────────────────────────────┘
```

### 🏆 Option A: The "Project Asset Explorer" Sidebar (Recommended)
We introduce a thin, collapsible **Utility Sidebar** on the extreme left-most edge of the screen (similar to the File Explorer in VS Code or the Pages Panel in Figma).

* **How it works:** A 48px wide sidebar containing icon buttons:
  * 💬 **Copilot Chat** (Active view by default)
  * 📁 **Project Files** (The Asset Explorer)
  * ⚙️ **Design Code Settings** (BS 8110 / EC2 parameters)
* Clicking the **Files (📁)** icon opens a sleek, semi-transparent slide-out panel (240px wide) listing all uploaded assets.

```
📁 Project Assets
├── 📐 Geometry (Source)
│   └── Floor-beam.dxf      [⬇️] [🗑️]
└── 📄 Visual (Reference)
    └── Floor-beam.pdf      [⬇️] [👁️]
```

* **Why it's elite UX:**
  * **Zero Screen Clutter:** It hides completely when you are focusing on a design conversation or looking at the canvas.
  * **Always Accessible:** The engineer can download or swap files at any point in the project lifetime without having to scroll up a long chat log.
  * **Future-Proof:** If a project expands to have multiple floor drawings (e.g. `Foundation.dxf`, `First-Floor.dxf`, `Roof-Plan.dxf`), this explorer scales beautifully.

---

### Option B: The "Active Context Header" Drawer
A clean, premium, horizontal "Context Drawer" anchored at the very top of the Left Panel (Conversational AI).

* **How it works:** A glassmorphic bar that spans the top of the chat area, showing badges of the active inputs:
  * `[DXF] Floor-beam.dxf (2.4 MB) ⬇️`
  * `[PDF] Floor-beam.pdf (1.1 MB) ⬇️`
* **Why it's great UX:**
  * **Immediate Context:** High visibility. It constantly reminds the engineer and the AI exactly what drawing set is driving the current design session.
  * **Micro-Actions:** Features a direct `Re-upload / Swap` button to quickly update the project boundaries.

---

### Option C: The Canvas "Layer Manager" Integration
Since the DXF and PDF represent the visual underlays of the drawing space, they can live directly in the **Layer Management Card** on the Canvas (Right Panel).

* **How it works:** Inside the canvas layers toolbar:
  * **Architectural Layout (PDF):** `[Eye Toggle] [Opacity Slider] [Download ⬇️]`
  * **Structural Geometry (DXF):** `[Eye Toggle] [Color Picker] [Download ⬇️]`
* **Why it's great UX:**
  * Highly intuitive for CAD draftspersons who associate drawings directly with active visual layers.

---

## 3. High-Fidelity UI Mockup (Option A - Asset Explorer)

Here is a visual mockup of the proposed File Explorer panel, built with rich design system tokens (Curated slate colors, smooth hover states, and clear typography).

```
┌────────────────────────────────────────────────────────┐
│  📁 PROJECT ASSETS                              [✕]    │
├────────────────────────────────────────────────────────┤
│  Manage and download reference drawings for this floor │
├────────────────────────────────────────────────────────┤
│                                                        │
│  📐 GEOMETRY SOURCE (DXF)                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 📄 Floor-beam.dxf                                │  │
│  │    Size: 2.4 MB  •  Parsed: 100%                 │  │
│  │                                                  │  │
│  │    [ Download ⬇️ ]          [ Re-parse 🔄 ]       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  👁️ VISUAL UNDERLAY (PDF)                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 📄 Floor-beam.pdf                                │  │
│  │    Size: 1.2 MB  •  Status: Connected            │  │
│  │                                                  │  │
│  │    [ Download ⬇️ ]          [ View PDF 👁️ ]       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ➕ UPLOAD NEW REVISION                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Drop new DXF or PDF to update structural layout  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 4. Micro-Interactions & Premium Polishing

1. **Upload Drop-State:** When dragging a new file over the IDE, the File Explorer panel automatically slides open with a glowing border transition and an SVG animation indicating a file drop zone.
2. **Download Click Indicator:** Clicking the Download button triggers a loading spinner on the button itself (instead of a static page jump) that resolves to a checkmark before saving the file, giving premium visual feedback.
3. **Parse Status Badges:** Visual indicator pills (`Parsed`, `Parsing...`, `Connection Error`) styled in soft HSL success green, warning orange, or error red to show geometric parsing health.

---

## 5. Architectural Recommendation

**We should go with Option A (The Utility Sidebar + File Explorer Panel).** 
It represents standard, professional-grade SaaS layout design (similar to VS Code or Figma), keeps the chat conversation completely focused, and provides the engineer with an easy-to-use, unified control center for all project assets.

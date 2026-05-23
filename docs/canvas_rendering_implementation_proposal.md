# 🎨 Engineering Proposal: Interactive Structural Canvas Rendering Engine

This proposal maps out the technical architecture and premium UX design system for rendering, manipulating, and verifying structural members on the **Interactive HTML5 Canvas** inside the `CanvasViewport` component.

It shifts the canvas from a static upload placeholder to a high-fidelity **Structural CAD viewport** utilizing the HTML5 Canvas API for extreme performance and pixel-perfect responsiveness.

---

## 1. Core Canvas Engine Architecture

To guarantee smooth rendering (60 FPS) and exact dimension grounding, the canvas uses a **Transformation Matrix** that translates DXF vector space coordinates (in millimeters) directly to Screen Pixel coordinates.

```
       [ DXF Coordinates (mm) ] 
                 │
                 ▼  (Translate: offsetX, offsetY)
       [ Unified World Coordinates ]
                 │
                 ▼  (Scale: zoomFactor)
       [ Screen Coordinates (Pixels) ]
```

### 📐 Transformation Formulas
For any structural point $P(X_{dxf}, Y_{dxf})$:
$$X_{screen} = (X_{dxf} - X_{min}) \cdot \text{zoom} + \text{pan}_x$$
$$Y_{screen} = \text{height}_{canvas} - \left( (Y_{dxf} - Y_{min}) \cdot \text{zoom} + \text{pan}_y \right)$$
*(Note: $Y$ is inverted to conform with typical CAD coordinate grids where positive $Y$ points upward).*

---

## 2. Visual Representation & Premium Aesthetics

To wow the structural engineer, the canvas avoids default CAD styling (black backgrounds and jagged lines) and adopts a modern, premium **dark-themed engineering workstation grid**.

```
┌─────────────────────────────────────────────────────────────┐
│ 🔍 Select  ✋ Pan  [ Workspace: Floor 1 ]         [Scale: 1:50] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│         C1 █──────────────────█ C2                  │
│            │      Beam B1     │                             │
│            │  (450 x 225 mm)  │                             │
│            │                  │                             │
│                                                             │
│                                                             │
│                                                             │
│  Selected: Beam B1                                          │
│  [ Width: 225 mm ]  [ Height: 450 mm ]      [Confirm Model] │
└─────────────────────────────────────────────────────────────┘
```

### 🎨 Visual Styles & Colors
* **Background Grid**: Deep Slate Grey (`#0b0f19`) with a glassmorphic dot grid (`#1e293b`).
* **Columns (Anchors)**: Glowing Amber (`#f59e0b`) squares or circles with clear ID text labels (e.g. `C1`).
* **Beams**: Sleek Indigo/Indigo-blue (`#6366f1`) semi-transparent rectangles ($30\%$ opacity) outlined with crisp solid borders.
* **Slabs**: Glassmorphic Emerald (`#10b981`) overlay zones ($10\%$ opacity) showing spanning direction arrows.
* **Original DXF background**: Dimmed, light-grey vector lines (`#334155` at $20\%$ opacity) to let structural members pop.
* **Active Selection**: A glowing cyan neon border (`#06b6d4`) with dashed animation outlines.

---

## 3. Interaction Paradigms: Hover, Click, Select, Edit

The engineer must have tactile control over the parsed geometry to make adjustments prior to calculation.

### A. Hover (Visual Feedback)
* **Action**: Moving cursor over a member displays an instant **Glassmorphic Tooltip**.
* **Tooltip Contents**:
  ```yaml
  Member ID: B-12 (Beam)
  Dimensions: 450 x 225 mm
  Clear Span: 4.85 m
  Actions: Click to edit section properties
  ```

### B. Click & Selection
* **Action**: Clicking a member locks the focus, adds the glowing selection indicator, and highlights the member in the **Left Panel Property Editor**.
* **Double-Click**: Prompts a inline overlay popover to quickly adjust key properties (e.g., width, depth, or span) without leaving the Canvas viewport.

### C. Direct Manipulation (Drag-and-Drop & Handles)
* **Stretch Handles**: Selected beams display blue corner handles to drag and extend clear span lengths or shift boundary locations.
* **Nodal snapping**: Moving a column automatically snaps it to the nearest parsed DXF vector intersection or grid line, preventing alignment errors.

---

## 4. Technical Implementation Path in Next.js

We will implement this by replacing the dummy done-state with an interactive canvas renderer using a React-managed state loop.

### State Interfaces
```typescript
export interface Point {
  x: number;
  y: number;
}

export interface GeometricMember {
  member_id: string;
  member_type: "beam" | "column" | "slab" | "wall" | "footing" | "staircase";
  start: Point;  // in dxf coordinate space
  end: Point;    // in dxf coordinate space
  meta: {
    b_mm: number;
    h_mm: number;
    L_clear?: number;
    [key: string]: any;
  };
}
```

### ⚙️ Main Render Hook / Draw Loop
```typescript
const useCanvasDrawing = (
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  members: GeometricMember[],
  zoom: number,
  pan: Point,
  selectedId: string | null,
  hoveredId: string | null
) => {
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // 1. Clear & draw background grid
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawDotGrid(ctx, canvas.width, canvas.height, zoom, pan);

    // 2. Draw parsed members
    members.forEach(member => {
      const isSelected = member.member_id === selectedId;
      const isHovered = member.member_id === hoveredId;

      if (member.member_type === "beam") {
        drawBeam(ctx, member, zoom, pan, isSelected, isHovered);
      } else if (member.member_type === "column") {
        drawColumn(ctx, member, zoom, pan, isSelected, isHovered);
      }
    });

    // 3. Draw active measurements and labels
    drawMeasurements(ctx, members, zoom, pan);
  }, [members, zoom, pan, selectedId, hoveredId]);

  return draw;
};
```

---

## 5. Safety Gate Verification (HITL)

A sticky validation bar is docked at the bottom of the canvas viewport:

```
┌────────────────────────────────────────────────────────────────────────┐
│ ⚠️ Geometry Verification Required. Check parsed locations on layout.    │
│ [ ✏️ Reset Model ]                  [ ✔️ Geometry Verified & Save ]     │
└────────────────────────────────────────────────────────────────────────┘
```

* **Action `[Reset Model]`**: Discards manual canvas changes and restores the initial raw Vision Agent classifications.
* **Action `[Geometry Verified & Save]`**: 
  1. Posts the updated JSON structure to `/api/v1/projects/{id}/members/verify`.
  2. Unlocks the **Assistant Structural Engineer dialogue** in the Chat Panel to capture loading/geotechnical requirements.

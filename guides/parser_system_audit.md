# 🔍 Technical Audit & Remediation Plan: DXF/PDF Parsing Agent

This audit diagnoses the current issues in the **Vision/Parser Agent** pipeline that prevent accurate spatial layout rendering on the interactive frontend canvas.

---

## 1. Feasibility Assessment: DXF vs. PDF

Before jumping into remediation, we must resolve the architectural question: **Is DXF parsing feasible, or should we let the AI figure out the members solely from the PDF?**

| Metric | DXF-Based parsing (Vector) | PDF-Based Parsing (Visual) |
| :--- | :--- | :--- |
| **Precision** | **100% Exact** (millimeter vector endpoints) | **Approximate** (pixel-based estimation) |
| **Scale Safety** | Inherent in coordinates (needs alignment check) | Highly prone to perspective and DPI errors |
| **Information Depth** | Full vector entities, layers, and attributes | Text characters and raster pixels only |
| **Parsing Effort** | Medium (requires layer and geometry sorting) | High (requires heavy vision OCR & visual grounding) |

### 💡 Verdict:
**DXF is 100% feasible and must remain the primary source of truth for the structural model.** 
Relying solely on visual PDFs for coordinates makes rendering an accurate structural grid impossible. However, the current parser is failing because **the raw vector coordinates extracted by the DXF parser are never propagated to the LLM, nor does the LLM know how to structure them.** 

---

## 2. The 4 Core Failure Modes Identified

### 🚨 Failure Mode 1: The unit-misalignment bug (25.4x Scale Error)
* **What Went Wrong**:
  The sample drawing has `$INSUNITS` set to `1` (Inches) in its header metadata, but the engineer drew using **metric coordinates** (where `225` meant $225$ mm, not $225$ inches). Our parser blindly converted these units, multiplying every vector coordinate and bounding box by `25.4`.
* **The Evidence**:
  * A `225` mm column became `5715` mm ($5.7$ meters!).
  * A `3.0` meter beam span (`3000` mm) became `76.2` meters!
  * Visual labels clearly stated `1B11 225x450` (confirming metric intent).

### 🚨 Failure Mode 2: Member Instance Collapse (Only 2 Columns Found)
* **What Went Wrong**:
  The drawing contains 76 column candidates, most of which have nearby text labels `C1` or `C2`. Because the LLM prompt is vague about *instance tracking*, the LLM collapsed all 76 candidates into **two single column definitions** (`C1` and `C2`), mistaking the individual column instances for simple type definitions.
* **The Evidence**:
  `res.txt` output contains exactly **one** `C1` and **one** `C2` column entry, making it impossible to render the other 74 columns in their actual grid layout.

### 🚨 Failure Mode 3: Missing Spatial Coordinates
* **What Went Wrong**:
  The frontend canvas cannot render members without their visual endpoints. However, the current LLM prompt in `parser.py` (lines 356-396) **never asks the LLM to output coordinates** (`start`, `end`, `center_point`) for the members! It only asks for meta values like `b_mm`, `h_mm`, and `L_clear`.
* **The Evidence**:
  None of the members in `res.txt` contain coordinate fields, leaving the canvas engine blind.

### 🚨 Failure Mode 4: Slab and Void Blindness
* **What Went Wrong**:
  Slabs and voids are represented in DXF as closed boundary polylines (or empty voids inside beam enclosures). The pre-processing heuristic `_prepare_candidates_summary` does not correctly isolate slab panels or label voids, and the LLM prompt does not instruct the agent to build the coordinate polygons for slab zones.

---

## 3. Detailed Remediation Plan

To solve these issues once and for all, we must update the parser agent's pipeline:

```
[ DXF Ingestion ] 
       │ 
       ▼
[ Step 1: Human-in-the-Loop Scale Override ] 
       │ (Forces unit confirmation; overrides $INSUNITS to metric)
       ▼
[ Step 2: Spatial Candidate Extraction ] 
       │ (Extracts exact Start/End for Beams, Center for Columns, Polygon for Slabs)
       ▼
[ Step 3: Precise Instance Prompting ] 
       │ (LLM preserves vector coordinates & maps nearby text to each distinct instance)
       ▼
[ Complete Spatial JSON Output ] --> [ Rendered exactly on Canvas ]
```

### 🛠️ Action 1: Fix the Scale Override Logic
We must configure the backend to prioritize the **Human confirmed units** over the raw `$INSUNITS` value. If the engineer selects "Millimetres", we must enforce a scale multiplier of `1.0` regardless of what the CAD header claims.

### 🛠️ Action 2: Propagate Vector Coordinates to the LLM Candidates
We must update `_prepare_candidates_summary` in `parser.py` to include the exact geometry vectors:
* **Beams**: Include `start_dxf: [x1, y1]`, `end_dxf: [x2, y2]`.
* **Columns**: Include `center_dxf: [cx, cy]`, `b_dxf: w`, `h_dxf: h`.
* **Slabs/Voids**: Include `polygon_points: [[x1, y1], [x2, y2], ...]`.

### 🛠️ Action 3: Revise the LLM Prompt for Spatial Preservation
We must rewrite the LLM prompt in `parser.py` to strictly enforce:
1. **Preserve coordinates**: The LLM must copy the candidate's exact coordinates (`start_dxf`, `end_dxf`, etc.) directly to the output member JSON.
2. **Instance Integrity**: Every input candidate must map to a *distinct* member instance (e.g. `C1-1`, `C1-2` or grid-name `C1` at coordinate `[X, Y]`), never collapsed.
3. **Slab & Void Detection**: Extract closed boundaries as slabs and tag negative boundary intersections as voids.

---

## 4. Remediation Pydantic Schema

Here is the exact schema we will use to enforce coordinate preservation:

```python
class SpatialPoint(BaseModel):
    x: float
    y: float

class SpatialMember(BaseModel):
    member_id: str  # e.g., "C1-1", "1B1"
    member_type: Literal["beam", "column", "slab", "wall", "footing"]
    
    # Precise CAD positions for canvas rendering
    start_point: Optional[SpatialPoint] = None  # Beams start
    end_point: Optional[SpatialPoint] = None    # Beams end
    center_point: Optional[SpatialPoint] = None # Columns center
    boundary_polygon: Optional[List[SpatialPoint]] = None # Slabs outline
    is_void: bool = False                       # True for slab voids
    
    meta: Dict[str, Any]
    spans_m: List[float]
```

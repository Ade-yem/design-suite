> **Loads flow downward through a hierarchy. Slabs → Beams → Columns/Walls → Footings. Staircases are a side branch that feeds into beams or landings.**

Every module must respect this hierarchy or the numbers will be wrong.

---

## Loading Module: Full Architecture Overview

### The Load Path Hierarchy
```
Imposed + Dead Loads (Environmental & Occupancy)
            ↓
        SLABS  ←——— STAIRCASES (feed reactions into supporting beams)
            ↓ (tributary distribution)
        BEAMS  ←——— Wall loads (if non-loadbearing partition or cladding)
            ↓ (reactions as point/UDL loads)
    COLUMNS  |  WALLS (loadbearing)
            ↓
        FOOTINGS (accumulate all loads from above)
```

---

### Module 1: Load Type Definitions

This is the base input layer. Every load in the system must be registered here before any analysis begins.

**1.1 Dead Loads (Permanent Actions — Gk)**

| Load Source | How It's Calculated | Unit |
|---|---|---|
| Member self-weight | Auto from geometry × unit weight (RC = 25 kN/m³) | kN/m or kN/m² |
| Slab finishes | User-defined, typical 1.0–2.0 kN/m² | kN/m² |
| Screed / topping | User-defined, typical 0.5–1.5 kN/m² | kN/m² |
| Partitions (fixed) | User-defined or 1.0 kN/m² default (BS 6399) | kN/m² |
| Cladding / facades | User-defined as line load on perimeter beams | kN/m |
| Services / MEP | User-defined, typical 0.5 kN/m² | kN/m² |

**1.2 Imposed Loads (Variable Actions — Qk)**

Driven by occupancy category per BS 6399-1 / EC1 Table 6.1:

| Occupancy | BS 6399 (kN/m²) | EC1 (kN/m²) |
|---|---|---|
| Residential | 1.5 | 2.0 |
| Office | 2.5 | 3.0 |
| Retail | 4.0 | 4.0 |
| Roof (accessible) | 1.5 | 1.0 |
| Roof (non-accessible) | 0.6 | 0.4 |
| Stairs | 3.0 | 3.0 |

This must be a **selectable enum** per zone/slab panel, not a global value.

**1.3 Wind Loads (Wk)** *(Scoped for later — flag only for now)*
- Relevant for walls and lateral stability
- Park this for Phase 2; focus on gravity loads first

**1.4 Notional Horizontal Loads**
- BS 8110: 1.5% of characteristic dead load at each floor
- EC2/EN 1990: via imperfection loads
- Applied to columns and walls for robustness checks

---

### Module 2: Load Combination Engine

This is the most critical module. It must produce **factored design loads** from the characteristic inputs above. The AI never touches this — it is pure hard-coded logic.

**2.1 BS 8110 Combinations**

| Combination | Expression | Use Case |
|---|---|---|
| Ultimate (ULS) — Dominant | 1.4Gk + 1.6Qk | All gravity members |
| Ultimate (ULS) — Dead + Wind | 1.2Gk + 1.2Qk + 1.2Wk | When wind is included |
| Serviceability (SLS) | 1.0Gk + 1.0Qk | Deflection, crack width |

**2.2 EC2 / EN 1990 Combinations**

| Combination | Expression | Use Case |
|---|---|---|
| ULS Fundamental | 1.35Gk + 1.5Qk | All gravity members |
| ULS with Wind | 1.35Gk + 1.5Qk + 1.5×0.6Wk | Combined loading |
| SLS Characteristic | 1.0Gk + 1.0Qk | Deflection |
| SLS Quasi-permanent | 1.0Gk + 0.3Qk | Long-term deflection, creep |
| SLS Frequent | 1.0Gk + 0.5Qk | Crack width checks |

**2.3 Pattern Loading** *(Critical for continuous members)*

For continuous beams and slabs, the worst-case moments are not always from full UDL. The combination engine must generate these arrangements:

```
Arrangement 1: All spans fully loaded         → Max midspan sagging
Arrangement 2: Alternate spans loaded          → Max support hogging  
Arrangement 3: Adjacent spans loaded           → Max shear at supports
```
EC2 Clause 5.1.3 and BS 8110 Clause 3.2.1.2 both mandate this. This directly feeds the continuous beam solver.

---

### Module 3: Member-Specific Load Assembly

Each structural member type has a specific way loads are assembled before analysis. This module handles the translation from "area loads" to "member loads."

**3.1 Slabs**

| Input | Process | Output |
|---|---|---|
| Gk (finishes + screed + services) + self-weight | Sum all dead components | Total Gk (kN/m²) |
| Qk (occupancy) | From occupancy table | Total Qk (kN/m²) |
| Apply combination factors | 1.4Gk + 1.6Qk (BS) or 1.35Gk + 1.5Qk (EC2) | Design load n (kN/m²) |

One-way vs two-way distribution flag must be set here (based on Ly/Lx ratio ≥ 2 = one-way).

**3.2 Beams**

Beams receive loads from three sources that must all be summed:

```
Beam Design Load =
    [1] Slab load (triangular/trapezoidal from tributary area)
  + [2] Self-weight (auto-calculated from b × h × 25 kN/m³)
  + [3] Wall/partition load (line load from any wall sitting on beam)
  + [4] Point loads (column or beam reactions from above, if transfer beam)
```

The **slab-to-beam distribution** rules:
- One-way slab → load goes to short-span beams only as UDL
- Two-way slab → triangular load to short beams, trapezoidal to long beams
- These must be converted to **equivalent UDL** for the beam solver using standard conversion factors

**3.3 Columns**

Columns receive accumulated loads from all floors above. The load assembly is:

```
Column Design Load (N) =
    Σ [Beam reactions at each floor]
  + Σ [Self-weight of column per storey]
  + [Any direct slab load on column head — flat slabs]
```

The module must track **number of storeys** contributing and apply the **EC1 / BS 6399 reduction factor** for imposed loads on columns (load reduction increases with number of floors — you don't design a ground floor column for 10 floors of full occupancy simultaneously).

**3.4 Walls (Loadbearing)**

```
Wall Design Load =
    [Axial load N] from beams/slabs bearing onto wall
  + [Self-weight] of wall per storey (unit weight × thickness × height)
  + [Lateral pressure] if basement retaining wall (scoped for later)
```

Eccentricity of load must be flagged here — beam bearing on one face creates moment in wall, not just axial load. This feeds the wall design module.

**3.5 Footings**

Footings are the **terminal accumulator** — they receive everything:

```
Footing Design Load =
    Column axial load N (from column module above)
  + Column moments Mx, My (if any)
  + Footing self-weight
  + Weight of soil surcharge above footing (if applicable)
  - Upward soil bearing resistance
```

Soil bearing capacity (qa) is a **user input** here — the system cannot determine geotechnical data. This must be explicitly requested.

**3.6 Staircases**

Staircases are treated as simply-supported one-way slabs spanning between landings:

```
Staircase Design Load =
    Self-weight (calculated from going, riser, waist thickness geometry)
  + Finishes (user-defined)
  + Imposed load (3.0 kN/m² per BS 6399 / EC1)
```

The reactions at top and bottom of flight feed as **point loads** into the supporting beams or landing slabs.

---

### Module 4: Load Output Schema

Every member's assembled loads must be serialized into a consistent JSON before being passed to the analysis solver. This is the contract between the Loading Module and the Analysis Engine.

```json
{
  "member_id": "B-12",
  "member_type": "beam",
  "design_code": "BS8110",
  "spans": [
    {
      "span_id": "B-12-S1",
      "length_m": 6.0,
      "loads": {
        "udl_dead_gk": 18.5,
        "udl_imposed_qk": 12.0,
        "udl_factored_n": 45.1,
        "point_loads": [],
        "wall_line_load": 8.0
      },
      "pattern_loading_flag": true
    }
  ],
  "combination_used": "1.4Gk + 1.6Qk",
  "source_slabs": ["SL-04", "SL-05"],
  "notes": "Two-way slab, trapezoidal distribution applied"
}
```

---

### Build Order for This Module

| Phase | Task | Dependency |
|---|---|---|
| **1** | Load type definition schema + occupancy table | None — start here |
| **2** | Load combination engine (BS 8110 + EC2) | Phase 1 |
| **3** | Slab load assembly + one-way/two-way classification | Phase 2 |
| **4** | Beam load assembly (tributary + wall + self-weight) | Phase 3 |
| **5** | Pattern loading generator | Phase 2 + 4 |
| **6** | Column/wall load accumulation (multi-storey) | Phase 4 |
| **7** | Staircase load assembly | Phase 3 |
| **8** | Footing load assembly | Phase 6 |
| **9** | Load output schema serializer | All above |

---

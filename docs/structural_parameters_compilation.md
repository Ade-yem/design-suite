# 🏗️ AI-Driven Structural Design Copilot: Parameter Compilation

This document provides a highly detailed, comprehensive compilation of all expected input and output parameters for structural members across the **Models (`models/bs8110/` & `models/ec2/`)**, **Core Analysis (`core/analysis/`)**, and **Core Design (`core/design/rc/`)** modules.

It covers both supported codes of practice:
* **BS 8110-1:1997** (British Standard for Structural Use of Concrete)
* **Eurocode 2: BS EN 1992-1-1:2004 (EC2)** (European Standard for Design of Concrete Structures)

---

## 1. Core Analysis Schemas (`models/analysis/schema.py`)

All structural analysis solvers (`core/analysis/*_solver.py`) produce outputs conforming to the standardized Pydantic schemas below. These schemas serve as the bridge between global loading engines and localized material design suites.

### StressResultants (Max internal forces)
* **Inputs/Attributes**:
  * `M_max_sagging_kNm` (`float`): Maximum positive (sagging) bending moment (default: `0.0`).
  * `M_max_hogging_kNm` (`float`): Maximum negative (hogging) bending moment (default: `0.0`).
  * `V_max_kN` (`float`): Maximum transverse shear force (default: `0.0`).
  * `N_axial_kN` (`float`): Maximum axial force (compression positive) (default: `0.0`).
  * `deflection_max_mm` (`float`): Maximum service load deflection (default: `0.0`).

### SLSChecks (Serviceability limits)
* **Inputs/Attributes**:
  * `deflection_limit_mm` (`float`): Maximum allowable deflection (e.g., $Span/250$ or $Span/500$).
  * `deflection_actual_mm` (`float`): Computed actual elastic/long-term deflection under service load.
  * `status` (`Literal["PASS", "FAIL"]`): Governing state check result.

### CalculationTraceStep (Verifiable derivation traces)
* **Inputs/Attributes**:
  * `step` (`int`): Sequential step index.
  * `description` (`str`): Summary of the physical or code check being executed.
  * `formula` (`Optional[str]`): Conceptual algebraic formulas used (e.g., `M=wL²/8`).
  * `inputs` (`Dict[str, Any]`): Parameter keys and numerical values substituted into the formula.
  * `result` (`Any`): Computed outcome of the step.
  * `clause_reference` (`Optional[str]`): Building code clause mapping (e.g., `"BS8110 Table 3.5"`).

### MemberAnalysisResult (Consolidated Output)
* **Inputs/Attributes**:
  * `member_id` (`str`): Unique structural identifier.
  * `member_type` (`Literal["beam", "slab", "column", "wall", "footing", "staircase"]`): Structural classification.
  * `analysis_method` (`Literal["closed_form", "coefficients", "matrix_stiffness"]`): Analytical method applied.
  * `stress_resultants` (`StressResultants`): Maximum calculated internal forces.
  * `critical_sections` (`Dict[str, Any]`): Map of localized internal force envelopes at specific spans/supports.
  * `reactions_kN` (`List[float]`): Support reaction forces.
  * `governing_pattern` (`Optional[str]`): Loading configuration pattern name (e.g., `"all_spans_loaded"`).
  * `SLS_checks` (`Optional[SLSChecks]`): Deflection and crack check outcomes.
  * `calculation_trace` (`List[CalculationTraceStep]`): Step-by-step audit logs.
  * `warnings` (`List[str]`): High-priority engineering alerts.
  * `flags` (`List[str]`): Diagnostic flags.

---

## 2. Code-Dependent Section Models & Design Orchestration

### 2.1. Beams (`models/bs8110/beam.py`, `models/ec2/beam.py` & Core Solvers)

Beams support transverse loads over clear spans. Design can be singly-reinforced (tension steel only) or doubly-reinforced (compressive and tensile steel).

> [!NOTE]
> Effective depth `d` and compression-steel depth `d_prime` are *derived* automatically from cover, link diameter, and main bar diameter to avoid engineering input contradictions.

#### 2.1.1. BS 8110 Beam Input Parameters (`BeamSection`)
* **Inputs**:
  * `b` (`float`): Web width (mm).
  * `h` (`float`): Overall section depth (mm).
  * `cover` (`float`): Nominal concrete cover to main bars (mm).
  * `fcu` (`float`): Characteristic concrete cube compressive strength ($N/mm^2$).
  * `fy` (`float`): Yield strength of main tension reinforcement ($N/mm^2$).
  * `fyv` (`float`): Yield strength of shear links/stirrups ($N/mm^2$).
  * `link_dia` (`float`, default: `8.0`): Diameter of shear links (mm).
  * `bar_dia` (`float`, default: `20.0`): Assumed main tension bar diameter (mm).
  * `comp_bar_dia` (`float`, default: `16.0`): Assumed compression bar diameter (mm).
  * `section_type` (`str`, default: `"rectangular"`): `"rectangular"` or `"flanged"`.
  * `support_condition` (`str`, default: `"simple"`): `"simple"`, `"continuous"`, or `"cantilever"`.
  * `bf` (`Optional[float]`, default: `None`): Effective flange width (mm). Required if `section_type == "flanged"`.
  * `hf` (`Optional[float]`, default: `None`): Flange/slab thickness (mm). Required if `section_type == "flanged"`.
  * `beta_b` (`float`, default: `1.0`): Moment redistribution factor ($0.70 \le \beta_b \le 1.0$).
* **Derived Constants**:
  * `d` (`float`): Effective depth = $h - cover - link\_dia - bar\_dia/2$ (mm).
  * `d_prime` (`float`): Centroid depth of compression bars = $cover + link\_dia + comp\_bar\_dia/2$ (mm).
  * `As_min` (`float`): Minimum tensile steel area ($mm^2$) per BS 8110 Table 3.25:
    * Rectangular: $0.13\% bh$ (high yield, $fy \ge 460$) or $0.15\% bh$ (mild steel).
    * Flanged: depends on $b_w / b_f$ ratio ($0.13\% - 0.23\%$).
  * `As_max` (`float`): Maximum steel area ($mm^2$) per Cl 3.12.6.1 ($4\%$ of gross cross-sectional area).

#### 2.1.2. Eurocode 2 Beam Input Parameters (`EC2BeamSection`)
* **Inputs**:
  * `b` (`float`): Web width (mm).
  * `h` (`float`): Overall section depth (mm).
  * `cover` (`float`): Nominal cover to face of links ($c_{nom}$, mm).
  * `fck` (`float`): Characteristic concrete cylinder strength ($N/mm^2$). *(Note: For C30/37, fck = 30)*.
  * `fyk` (`float`, default: `500.0`): Characteristic reinforcement yield strength ($N/mm^2$).
  * `fywk` (`float`, default: `500.0`): Characteristic shear-link yield strength ($N/mm^2$).
  * `link_dia` (`float`, default: `8.0`): Diameter of shear links (mm).
  * `bar_dia` (`float`, default: `20.0`): Assumed main tension bar diameter (mm).
  * `comp_bar_dia` (`float`, default: `16.0`): Assumed compression bar diameter (mm).
  * `section_type` (`str`, default: `"rectangular"`): `"rectangular"` or `"flanged"`.
  * `support_condition` (`str`, default: `"simple"`): `"simple"`, `"continuous"`, or `"cantilever"`.
  * `bf` (`Optional[float]`, default: `None`): Total effective flange width (mm). Required for flanged beams.
  * `hf` (`Optional[float]`, default: `None`): Flange thickness (mm).
  * `delta` (`float`, default: `1.0`): Moment redistribution ratio ($\ge 0.70$).
* **Derived Constants**:
  * `fcd` (`float`): Design concrete cylinder strength = $0.85 \times fck / 1.50$ (N/mm²). *(Assuming $\alpha_{cc} = 0.85$ UK NA)*
  * `fyd` / `fywd` (`float`): Design steel yield strength = $fyk / 1.15$ (N/mm²).
  * `fctm` (`float`): Mean concrete tensile strength ($N/mm^2$) per Table 3.1:
    * $0.30 \times fck^{2/3}$ for $fck \le 50$, or $2.12 \times \ln(1.0 + (fck + 8.0) / 10.0)$ for $fck > 50$.
  * `d` / `d_prime` (`float`): Effective depth and depth to compression reinforcement centroid (mm).
  * `K_lim` (`float`): Limiting K factor for singly-reinforced design = $\max(0.60\delta - 0.18\delta^2 - 0.21, 0.0)$ capped at `0.167` for $\delta \ge 1.0$.
  * `As_min` (`float`): Minimum tension steel ($mm^2$) per Cl 9.2.1.1:
    * $As_{min} = \max(0.26 \frac{f_{ctm}}{f_{yk}} b d, 0.0013 b d)$.
  * `As_max` (`float`): Maximum steel ($mm^2$) per Cl 9.2.1.1(3) = $0.04 \times A_c$ (gross concrete area).

---

### 2.2. Columns (`models/bs8110/column.py` & `models/ec2/column.py`)

Columns are compression members that may also carry moments due to structural eccentricity or wind.

#### 2.2.1. BS 8110 Column Input Parameters (`ColumnSection`)
* **Inputs**:
  * `b` (`float`): Column width perpendicular to minor bending y-axis (mm).
  * `h` (`float`): Column depth perpendicular to major bending x-axis (mm).
  * `l_ex` / `l_ey` (`float`): Effective buckling lengths for major and minor bending axes (mm).
  * `cover` (`float`): Nominal cover to main longitudinal bars (mm).
  * `fcu` (`float`): Concrete cube compressive strength ($N/mm^2$).
  * `fy` (`float`): Main longitudinal bar yield strength ($N/mm^2$).
  * `link_dia` (`float`, default: `8.0`): Column link diameter (mm).
  * `bar_dia` (`float`, default: `16.0`): Assumed main longitudinal bar diameter (mm).
  * `braced` (`bool`, default: `True`): `True` (braced) or `False` (unbraced).
* **Derived Constants**:
  * `d` (`float`): Effective depth (mm).
  * `As_min` (`float`): Minimum longitudinal steel = $0.4\% bh$ ($mm^2$).
  * `As_max` (`float`): Maximum longitudinal steel = $6.0\% bh$ ($mm^2$) (vertically cast).

#### 2.2.2. Eurocode 2 Column Input Parameters (`EC2ColumnSection`)
* **Inputs**:
  * `b` (`float`): Column width perpendicular to minor bending y-axis (mm).
  * `h` (`float`): Column depth perpendicular to major bending x-axis (mm).
  * `l_0x` / `l_0y` (`float`): Effective buckling lengths in major and minor axes (mm).
  * `cover` (`float`): Nominal concrete cover to face of links ($c_{nom}$, mm).
  * `fck` (`float`): Characteristic cylinder concrete strength ($N/mm^2$).
  * `fyk` (`float`, default: `500.0`): Characteristic steel yield strength ($N/mm^2$).
  * `link_dia` (`float`, default: `8.0`): Column link diameter (mm).
  * `bar_dia` (`float`, default: `16.0`): Assumed main longitudinal bar diameter (mm).
  * `braced` (`bool`, default: `True`): `True` (braced) or `False` (unbraced).
* **Derived Constants**:
  * `fcd` (`float`): Design concrete strength = $0.85 \times fck / 1.50$ (N/mm²).
  * `fyd` (`float`): Design steel strength = $fyk / 1.15$ (N/mm²).
  * `i_x` / `i_y` (`float`): Radii of gyration = $h / \sqrt{12}$ and $b / \sqrt{12}$ (mm).
  * `lambda_x` / `lambda_y` (`float`): Slenderness ratios = $l_{0x} / i_x$ and $l_{0y} / i_y$.
  * `As_min_geo` (`float`): Geometric minimum steel = $0.2\% A_c$ ($0.002 b h$) ($mm^2$). *(Note: The design service checks ultimate axial load and enforces $As_{min} = \max(0.10 N_{Ed}/f_{yd}, 0.002 A_c)$)*.
  * `As_max` (`float`): Maximum steel = $4.0\% A_c$ (outside laps) ($mm^2$).

---

### 2.3. Slabs (`models/bs8110/slab.py` & `models/ec2/slab.py`)

Slabs are planar flexural members designed per 1-meter wide strip ($b=1000$ mm). Special slabs include Ribbed/Waffle and Flat slabs.

#### 2.3.1. BS 8110 Slab Input Parameters (`SlabSection`)
* **Inputs**:
  * `h` (`float`): Overall slab thickness (mm).
  * `cover` (`float`): Nominal cover to main bars (mm).
  * `fcu` (`float`): Concrete cube compressive strength ($N/mm^2$).
  * `lx` / `ly` (`float`): Shorter and longer spans on plan (mm).
  * `fy` (`float`): Steel reinforcement yield strength ($N/mm^2$).
  * `slab_type` (`str`, default: `"one-way"`): `"one-way"` or `"two-way"`.
  * `panel_type` (`Optional[str]`, default: `None`): Two-way panel boundary condition key for Table 3.14.
  * `support_condition` (`str`, default: `"simple"`): `"simple"` or `"continuous"`.
  * `beta_b` (`float`, default: `1.0`): Moment redistribution factor ($0.7 \le \beta_b \le 1.0$).
  * `layer` (`str`, default: `"outer"`): designed layer: `"outer"` (short-span) or `"inner"` (long-span).
  * `bar_dia` (`float`, default: `12.0`): Assumed main reinforcement bar diameter (mm).
  * `bar_dia_outer` (`float`, default: `0.0`): Outermost layer bar diameter when `layer == "inner"`.
  * `bar_dia_sec` (`float`, default: `10.0`): Secondary distribution reinforcement diameter (mm).
* **Derived Constants**:
  * `d` (`float`): Effective depth (mm).
    * `layer == "outer"`: $d = h - cover - bar\_dia/2$
    * `layer == "inner"`: $d = h - cover - bar\_dia\_outer - bar\_dia/2$
  * `As_min` (`float`): Min steel = $0.13\% bh$ (high-yield) or $0.24\% bh$ (mild steel) ($mm^2/m$).
  * `As_max` (`float`): Max steel = $4.0\% bh$ ($mm^2/m$).

#### 2.3.2. Eurocode 2 Slab Input Parameters (`EC2SlabSection`)
* **Inputs**:
  * `h` (`float`): Overall slab thickness (mm).
  * `cover` (`float`): Nominal cover to face of main bars ($c_{nom}$, mm).
  * `fck` (`float`): Characteristic cylinder concrete strength ($N/mm^2$).
  * `lx` / `ly` (`float`): Shorter and longer spans on plan (mm).
  * `fyk` (`float`, default: `500.0`): Characteristic yield strength ($N/mm^2$).
  * `slab_type` (`str`, default: `"one-way"`): `"one-way"` or `"two-way"`.
  * `panel_type` (`Optional[str]`, default: `None`): Two-way edge code (e.g. `"SSSS"`, `"CSCS"`).
  * `support_condition` (`str`, default: `"simple"`): `"simple"`, `"continuous"`, or `"cantilever"`.
  * `bar_dia_x` / `bar_dia_y` (`float`, default: `12.0`): Main bar diameters in x (short-span) and y (long-span) (mm).
  * `delta` (`float`, default: `1.0`): Moment redistribution ratio.
  * `is_end_span` (`bool`, default: `False`): `True` if end span of a continuous system (affects deflection).
* **Derived Constants**:
  * `d_x` (`float`): Short-span effective depth (outer layer) = $h - cover - bar\_dia\_x / 2$ (mm).
  * `d_y` (`float`): Long-span effective depth (inner layer) = $h - cover - bar\_dia\_x - bar\_dia\_y / 2$ (mm).
  * `As_min` (`float`): Minimum reinforcement per Cl 9.3.1.1 = $\max(0.26 \frac{f_{ctm}}{f_{yk}} b d_x, 0.0013 b d_x)$ ($mm^2/m$).
  * `As_max` (`float`): Maximum steel = $4.0\% A_c$ ($mm^2/m$).

---

### 2.4. Footings (`models/bs8110/footing.py` & `models/ec2/footing.py`)

Footings distribute ultimate column axial loads and bending moments safely to the underlying soil or piles.

#### 2.4.1. BS 8110 Isolated Pad Footings (`PadFooting`)
* **Inputs (`FoundationBase`)**:
  * `lx` / `ly` (`float`): Footing plan dimensions parallel and perpendicular to plane of bending (mm).
  * `h` (`float`): Overall footing thickness (mm).
  * `fcu` (`float`): Concrete cube compressive strength ($N/mm^2$).
  * `fy` (`float`): Steel reinforcement yield strength ($N/mm^2$).
  * `cover` (`float`): Cover to face of outermost bars (mm) ($\ge 50$ mm for casting against blinding).
  * `column_cx` / `column_cy` (`float`): Column major and minor plan dimensions (mm).
  * `bar_dia` (`float`, default: `16.0`): Assumed main steel bar diameter (mm).
* **Derived Constants**:
  * `d` (`float`): Centroidal effective depth = $h - cover - bar\_dia/2$ (mm).
  * `As_min` (`float`): Slab-like isolated minimum reinforcement ($0.13\% - 0.24\%$) ($mm^2/m$).

#### 2.4.2. Eurocode 2 Isolated Pad Footings (`EC2 PadFooting`)
* **Inputs (`FoundationBase`)**:
  * `lx` / `ly` (`float`): Footing plan dimensions (mm).
  * `h` (`float`): Overall footing thickness (mm).
  * `fck` (`float`): Concrete cylinder compressive strength ($N/mm^2$).
  * `fyk` (`float`, default: `500.0`): Steel yield strength ($N/mm^2$).
  * `cover` (`float`, default: `50.0`): Nominal cover to face of main bars ($c_{nom}$, mm).
  * `column_cx` / `column_cy` (`float`, default: `400.0`): Column major and minor plan dimensions (mm).
  * `bar_dia` (`float`, default: `16.0`): Assumed main steel bar diameter (mm).
* **Derived Constants**:
  * `d` (`float`): Effective depth = $h - cover - bar\_dia/2$ (mm).
  * `As_min` (`float`): Minimum reinforcement per Cl 9.8.2.1 = $\max(0.26 \frac{f_{ctm}}{f_{yk}} b d, 0.0013 b d)$ ($mm^2/m$).

---

### 2.5. Staircases (`models/bs8110/staircase.py` & `models/ec2/staircase.py`)

Staircases are modeled as inclined one-way solid slabs spanning on plan between supports.

#### 2.5.1. BS 8110 Staircases (`StaircaseSection`)
* **Inputs**:
  * `waist` (`float`): Waist thickness — perpendicular to the soffit slope (mm).
  * `tread` / `riser` (`float`): Horizontal tread and vertical riser dimensions (mm).
  * `num_steps` (`int`): Total step count in the flight.
  * `span` (`float`): Effective span measured horizontally on plan (mm).
  * `width` (`float`, default: `1000.0`): Staircase flight width (mm) (usually designed for 1m strip).
  * `cover` (`float`, default: `25.0`): Cover to main tension bars (mm).
  * `fcu` (`float`, default: `30.0`): Concrete strength ($N/mm^2$).
  * `fy` (`float`, default: `500.0`): Main longitudinal rebar yield strength ($N/mm^2$).
  * `support_condition` (`str`, default: `"simple"`): `"simple"` or `"continuous"`.
  * `bar_dia` (`float`, default: `12.0`): Main longitudinal bar diameter (mm).
  * `bar_dia_dist` (`float`, default: `8.0`): Transverse distribution bar diameter (mm).
  * `beta_b` (`float`, default: `1.0`): Moment redistribution factor.
* **Derived Constants**:
  * `angle` (`float`): Slope inclination angle $\alpha = \arctan(riser/tread)$ (rad).
  * `cos_alpha` (`float`): cosine value of slope angle $\cos(\alpha)$.
  * `going` (`float`): Sloped going length = $\sqrt{tread^2 + riser^2}$ (mm).
  * `mean_thickness` (`float`): Average vertical structural thickness = $waist + 0.5 \times riser$ (mm).
  * `d` (`float`): Main effective depth = $waist - cover - bar\_dia/2$ (mm).
  * `d_dist` (`float`): Effective depth for secondary steel = $d - bar\_dia/2 - bar\_dia\_dist/2$ (mm).
  * `As_min` (`float`): Waist-based slab minimum steel area ($0.13\% - 0.24\%$) ($mm^2/m$).

#### 2.5.2. Eurocode 2 Staircases (`EC2StaircaseSection`)
* **Inputs** mirror the BS 8110 model in geometry but update materials:
  * `fck` (`float`): Concrete cylinder compressive strength ($N/mm^2$) replaces `fcu`.
  * `fyk` (`float`): Reinforcement characteristic yield strength ($N/mm^2$) replaces `fy`.
* **Derived Overrides**:
  * `As_min` (`float`): Tension steel minimum conforms to the tensile-strength-based formula (Cl 9.2.1.1):
    * $As_{min} = \max(0.26 \frac{f_{ctm}}{f_{yk}} b d, 0.0013 b d)$ ($mm^2/m$).

---

### 2.6. Walls (`models/bs8110/wall.py` & `models/ec2/wall.py`)

Reinforced concrete walls are vertical load-bearing panels with lengths $l_w \ge 4 \times$ thickness $h$.

#### 2.6.1. BS 8110 Reinforced Concrete Walls (`WallSection`)
* **Inputs**:
  * `h` (`float`): Wall thickness (mm) (min: `75.0` per Cl 3.9.1.2).
  * `l_w` (`float`): Horizontal length of wall panel (mm).
  * `l_e` (`float`): Effective height of wall panel (mm).
  * `fcu` (`float`): Concrete cube compressive strength ($N/mm^2$).
  * `fy` (`float`): Steel reinforcement yield strength ($N/mm^2$).
  * `cover` (`float`): Nominal cover to face of vertical bars (mm).
  * `bar_dia` (`float`, default: `12.0`): Vertical bar diameter (mm).
  * `braced` (`bool`, default: `True`): `True` (braced) or `False` (unbraced).
* **Derived Constants**:
  * `d` (`float`): Effective depth for out-of-plane flexure = $h - cover - bar\_dia/2$ (mm).
  * `As_min_v` (`float`): Min vertical steel area ($mm^2/m$) on both faces combined:
    * $0.25\% bh$ ($fy \ge 460$) or $0.40\% bh$ ($fy \le 250$).
  * `As_min_h` (`float`): Min horizontal steel ($mm^2/m$):
    * $0.25\% bh$ ($fy \ge 460$) or $0.30\% bh$ ($fy \le 250$).
  * `As_max_v` (`float`): Max vertical steel area = $4.0\% bh$ ($mm^2/m$).

#### 2.6.2. Eurocode 2 Reinforced Concrete Walls (`EC2WallSection`)
* **Inputs**:
  * `h` (`float`): Wall thickness (mm) (min: `120.0` recommended under EC2 for load-bearing walls).
  * `l_w` (`float`): Horizontal panel length (mm).
  * `l_e` (`float`): Effective height of panel (mm).
  * `fck` (`float`): Concrete cylinder strength ($N/mm^2$).
  * `fyk` (`float`, default: `500.0`): Characteristic yield strength ($N/mm^2$).
  * `cover` (`float`): Nominal cover to face of vertical bars ($c_{nom}$, mm).
* **Derived Constants**:
  * `As_min_v` (`float`): Minimum vertical reinforcement total per Cl 9.6.2(1) = $0.002 A_c$ ($mm^2/m$).
  * `As_min_h` (`float`): Minimum horizontal reinforcement total per Cl 9.6.3(1) = $\max(25\% As_v, 0.001 A_c)$ ($mm^2/m$).

---

## 3. Design Code Parameter Comparison: BS 8110 vs. Eurocode 2 (EC2)

The table below compiles how material, geometric, safety, and detailing parameters change when transitioning between BS 8110-1:1997 and Eurocode 2 (BS EN 1992-1-1:2004) across all structural members:

| Structural Member | Property / Parameter | BS 8110-1:1997 | Eurocode 2 (BS EN 1992-1-1) |
| :--- | :--- | :--- | :--- |
| **All Members** | **Concrete Strength** | Characteristic cube compressive strength: $f_{cu}$ (e.g., C30 $\rightarrow 30\text{ MPa}$ cube) | Characteristic cylinder strength: $f_{ck}$ (e.g., C30/37 $\rightarrow 30\text{ MPa}$ cylinder / $37\text{ MPa}$ cube) |
| | **Steel Yield Strength** | $fy, fyv$ (Standard: 460 or 500 N/mm²) | $fyk, fywk$ (Standard: 500 N/mm²) |
| | **Material Safety Factors ($\gamma$)** | Embedded in code formulas:<br>- Concrete: $\gamma_c$ implicit in $0.45 f_{cu}$ (aggregates $\gamma_c=1.5$ and block shape)<br>- Steel: $0.95 f_y$ (implicit $\gamma_s=1.05$) | Explicit partial factors:<br>- Concrete: $\gamma_c = 1.50$, design value $f_{cd} = \alpha_{cc} f_{ck} / \gamma_c$<br>- Steel: $\gamma_s = 1.15$, design value $f_{yd} = f_{yk} / \gamma_s$ |
| | **Concrete Cover Definition** | Nominal cover to face of main bars ($c$) | Nominal cover to face of links ($c_{nom}$), calculated as $c_{min} + \Delta c_{dev}$ (Cl 4.4.1) |
| **Beams** | **Redistribution Factor** | $\beta_b$ (moment redistribution factor: $0.70 \le \beta_b \le 1.0$) | $\delta$ (moment redistribution ratio: $0.70 \le \delta \le 1.0$) |
| | **Singly Reinforced Limit** | $K' = 0.156$ (for zero redistribution) | $K_{lim} = 0.167$ (for $\delta = 1.0$ Class B/C, C50) |
| | **Minimum Steel ($As_{min}$)** | Constant percentage of gross area per Table 3.25:<br>- High-yield ($fy \ge 460$): $0.13\% bh$<br>- Mild steel ($fy \le 250$): $0.15\% bh$ | Tensile-strength-based formula (Cl 9.2.1.1):<br>$As_{min} = \max\left(0.26 \frac{f_{ctm}}{f_{yk}} b_t d, 0.0013 b_t d\right)$<br>where $f_{ctm} = 0.30 f_{ck}^{2/3}$ |
| | **Maximum Steel ($As_{max}$)** | $4.0\% bh$ (gross area) | $4.0\% A_c$ (gross concrete area) |
| **Columns** | **Slenderness** | Geometric ratio $l_e / h$ compared against:<br>- Braced: 15<br>- Unbraced: 10 | Radius of gyration-based ratio $\lambda = l_0 / i$ ($i = h/\sqrt{12}$) compared against $\lambda_{lim} = 20 A B C / \sqrt{n}$ |
| | **Minimum Steel ($As_{min}$)** | $0.4\% bh$ ($0.004 bh$) | $As_{min} = \max\left(0.10 \frac{N_{Ed}}{f_{yd}}, 0.002 A_c\right)$ |
| | **Maximum Steel ($As_{max}$)** | $6.0\% bh$ (gross area, vertically cast) | $4.0\% A_c$ (outside laps) or $8.0\% A_c$ (at lap sections) |
| **Slabs** | **Effective Depth (d)** | Single-layer/Centroidal depth based on bar position | Outermost layer ($d_x$) for short span, inner layer ($d_y = h - cover - bar\_dia_x - bar\_dia_y/2$) for long span |
| | **Two-Way Moments** | BS 8110 Table 3.14 Rankine-Grashof coefficients | Rankine-Grashof with Marcus correction coefficients (tabulated in IStructE Manual Table A3) |
| | **Deflection Control** | Basic span/depth ratio (Table 3.9) modified by tension/compression reinforcement factors | Span/depth ratio checked via complex ductility/axial-ratio formula (Cl 7.4.2 Eq. 7.16) |
| **Footings** | **Punching Shear Perimeter** | At $1.5d$ from column face (rounded corners) | At $2.0d$ from column face (rounded corners) |
| | **Punching Beta factor** | $1.0$ (symmetric) or calculated eccentric factors | Explicit eccentricity factors $\beta$ (Cl 6.4.3(3)):<br>- Interior: 1.15<br>- Edge: 1.40<br>- Corner: 1.50 |
| **Walls** | **Slenderness** | stocky if $l_e/h \le 15$ (braced) or $\le 10$ (unbraced) | stocky if $\lambda \le \lambda_{lim}$ |
| | **Minimum vertical steel** | High-yield: $0.25\% bh$ per face ($0.50\%$ total) | $0.2\% A_c$ total (Cl 9.6.2) |

---

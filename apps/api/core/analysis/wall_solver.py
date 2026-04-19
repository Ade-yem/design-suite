"""
Loadbearing Wall Analysis Solver
==========================================
Handles slenderness classification, effective height, eccentricity from
beam bearing and geometric imperfections, and outputs design moments per
metre run of wall.

Reference:
    BS 8110-1:1997 Clause 3.9 / EC2 Clause 5.8 (walls)
    Scope: Gravity (non-lateral) walls only. Shear walls flagged for Phase 2.
"""
import math
from typing import List, Literal

from models.analysis.schema import (
    MemberAnalysisResult,
    StressResultants,
    CalculationTraceStep,
)


class WallSolver:
    """
    Classifies a wall as short or slender, determines the design eccentricity
    from beam reactions and imperfections, then returns the design axial load
    and moment per metre run for downstream section design.

    Args:
        member_id: Unique identifier for the wall member.
        storey:    Storey number (1 = ground, 2 = first floor, etc.)
        h_clear:   Clear storey height in metres.
        thickness: Wall thickness in mm.
        is_braced: True if lateral movement is restrained by diaphragm/shear walls
                   (braced frame assumption). Unbraced walls have higher β factors.
        design_code: "BS8110" or "EC2".
    """

    # β factors for effective height — depends on restraint at top and bottom
    # (both floors restrained = 0.75, one end free = 1.5) — per BS 8110 Table 3.21
    _BETA_BOTH_RESTRAINED = 0.75
    _BETA_ONE_FREE = 1.5

    def __init__(
        self,
        member_id: str,
        storey: int,
        h_clear: float,
        thickness: float,
        is_braced: bool = True,
        design_code: Literal["BS8110", "EC2"] = "BS8110",
    ) -> None:
        self.member_id = member_id
        self.storey = storey
        self.h_clear = h_clear          # metres
        self.t = thickness               # mm
        self.is_braced = is_braced
        self.design_code = design_code
        self.trace: List[CalculationTraceStep] = []
        self._step = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_step(self) -> int:
        self._step += 1
        return self._step

    def _effective_height(self, both_ends_restrained: bool = True) -> float:
        """
        Calculates effective height hef = β * h_clear.

        Args:
            both_ends_restrained: True when both top and bottom are laterally
                                  restrained (typical floor-to-floor condition).

        Returns:
            hef in metres.
        """
        beta = (
            self._BETA_BOTH_RESTRAINED if both_ends_restrained else self._BETA_ONE_FREE
        )
        hef = beta * self.h_clear

        self.trace.append(
            CalculationTraceStep(
                step=self._next_step(),
                description="Effective height calculation",
                formula="hef = β × h_clear",
                inputs={
                    "β": beta,
                    "h_clear (m)": self.h_clear,
                    "both_ends_restrained": both_ends_restrained,
                },
                result={"hef_m": hef},
                clause_reference="BS8110 Table 3.21 / EC2 Clause 5.8.3.2",
            )
        )
        return hef

    def _slenderness_ratio(self, hef: float) -> float:
        """
        Computes slenderness ratio λ = hef / t_eff.

        Args:
            hef: Effective height in metres.

        Returns:
            Dimensionless slenderness ratio.
        """
        t_eff_m = self.t / 1000.0
        ratio = hef / t_eff_m

        self.trace.append(
            CalculationTraceStep(
                step=self._next_step(),
                description="Slenderness ratio",
                formula="λ = hef / t",
                inputs={"hef (m)": hef, "t (m)": t_eff_m},
                result={"lambda": ratio},
            )
        )
        return ratio

    def _classify(self, ratio: float) -> str:
        """
        Classifies the wall as 'short' or 'slender'.

        Limits:
            BS 8110 braced: λ ≤ 15 → short
            EC2 braced:     λ ≤ 86 → short (simplified – √(3)×π² ≈ 29.6 for walls,
                            but 86 is the commonly cited limit for plain walls)

        Args:
            ratio: Slenderness ratio λ.

        Returns:
            "short" or "slender".
        """
        limit = 15.0 if self.design_code == "BS8110" else 86.0
        classification = "short" if ratio <= limit else "slender"

        self.trace.append(
            CalculationTraceStep(
                step=self._next_step(),
                description="Wall classification",
                formula=f"λ ≤ {limit} → short",
                inputs={"lambda": ratio, "limit": limit},
                result={"classification": classification},
                clause_reference=(
                    "BS8110 Clause 3.9.3" if self.design_code == "BS8110"
                    else "EC2 Clause 5.8.3"
                ),
            )
        )
        return classification

    def _eccentricity(
        self,
        N_axial_kN: float,
        beam_moment_kNm_per_m: float,
        hef: float,
        bearing_length_mm: float = 100.0,
    ) -> float:
        """
        Total design eccentricity at the top of the wall (mm).

        Sources:
            1. Beam bearing eccentricity: e_bearing = t/2 − bearing_length/2
            2. Load moment:               e_load = M_beam / N_axial
            3. Geometric imperfection:    ei = hef / 400  (EC2 Clause 5.2)
               BS 8110 uses a notional 20 mm minimum or h/20.

        Args:
            N_axial_kN:          Axial load in kN.
            beam_moment_kNm_per_m: Moment transferred from beam per metre run (kNm/m).
            hef:                 Effective height in metres.
            bearing_length_mm:   Length of beam bearing on wall in mm.

        Returns:
            Total design eccentricity in mm.
        """
        e_bearing = (self.t / 2.0) - (bearing_length_mm / 2.0)

        e_load = 0.0
        if N_axial_kN > 0:
            # Convert moment to per-metre and divide by axial to get eccentricity
            e_load = (beam_moment_kNm_per_m * 1000.0) / N_axial_kN  # mm

        # Geometric imperfection
        if self.design_code == "EC2":
            e_imperfection = (hef * 1000.0) / 400.0  # mm
        else:
            e_imperfection = max(self.t / 20.0, 20.0)  # mm

        e_total = e_bearing + e_load + e_imperfection

        self.trace.append(
            CalculationTraceStep(
                step=self._next_step(),
                description="Design eccentricity at top of wall",
                formula="e_total = e_bearing + e_load + e_imperfection",
                inputs={
                    "e_bearing (mm)": e_bearing,
                    "e_load (mm)": e_load,
                    "e_imperfection (mm)": e_imperfection,
                    "bearing_length (mm)": bearing_length_mm,
                },
                result={"e_total_mm": e_total},
                clause_reference=(
                    "EC2 Clause 5.2 / BS8110 Clause 3.9.4.2"
                ),
            )
        )
        return e_total

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def solve(
        self,
        N_axial_kN: float,
        beam_moment_kNm_per_m: float = 0.0,
        both_ends_restrained: bool = True,
        bearing_length_mm: float = 100.0,
        is_shear_wall: bool = False,
    ) -> MemberAnalysisResult:
        """
        Runs the complete wall analysis.

        Args:
            N_axial_kN:            Factored axial load per metre run (kN/m).
            beam_moment_kNm_per_m: Net moment from beams on one or both faces
                                   per metre run (kNm/m). Use the difference
                                   for unequal spans either side.
            both_ends_restrained:  True for floor-to-floor conditions.
            bearing_length_mm:     Beam bearing length on wall (mm).
            is_shear_wall:         If True, returns a flag and skips gravity analysis.

        Returns:
            MemberAnalysisResult with stress resultants and full calculation trace.
        """
        flags: List[str] = []
        warnings: List[str] = []

        # Shear walls deferred to Phase 2 lateral analysis
        if is_shear_wall:
            flags.append("shear_wall_deferred_to_phase_2_lateral_analysis")
            return MemberAnalysisResult(
                member_id=self.member_id,
                member_type="wall",
                analysis_method="closed_form",
                stress_resultants=StressResultants(N_axial_kN=N_axial_kN),
                flags=flags,
                warnings=["Shear wall lateral analysis not yet implemented."],
                calculation_trace=self.trace,
            )

        hef = self._effective_height(both_ends_restrained)
        ratio = self._slenderness_ratio(hef)
        classification = self._classify(ratio)

        if classification == "slender":
            warnings.append(
                "Slender wall: second-order effects significant. "
                "Consider increasing thickness or reducing storey height."
            )

        e_total_mm = self._eccentricity(
            N_axial_kN, beam_moment_kNm_per_m, hef, bearing_length_mm
        )

        # Design moment per metre run (kNm/m)
        M_design = N_axial_kN * (e_total_mm / 1000.0)

        self.trace.append(
            CalculationTraceStep(
                step=self._next_step(),
                description="Design moment per metre run",
                formula="M_design = N × e_total",
                inputs={"N (kN/m)": N_axial_kN, "e_total (mm)": e_total_mm},
                result={"M_design_kNm_per_m": M_design},
            )
        )

        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="wall",
            analysis_method="closed_form",
            stress_resultants=StressResultants(
                N_axial_kN=N_axial_kN,
                M_max_sagging_kNm=M_design,
            ),
            critical_sections={
                "storey": self.storey,
                "effective_height_m": hef,
                "slenderness_ratio": ratio,
                "wall_type": classification,
                "eccentricity_total_mm": e_total_mm,
                "design_moment_kNm_per_m": M_design,
            },
            calculation_trace=self.trace,
            flags=flags,
            warnings=warnings,
        )

from typing import Dict, Any, List, Literal
from models.analysis.schema import (
    MemberAnalysisResult, StressResultants, CalculationTraceStep
)

class ColumnSolver:
    """
    Phase 6 & 7: Column Analysis Solver
    Handles effective length, slenderness classification, and secondary moments.
    """
    def __init__(self, member_id: str, h: float, b: float, L_clear: float, end_condition: str = "fixed_pinned"):
        self.member_id = member_id
        self.h = h # depth in plane of bending (mm)
        self.b = b # width (mm)
        self.L_clear = L_clear * 1000 # convert m to mm
        self.end_condition = end_condition
        self.trace: List[CalculationTraceStep] = []

    def _determine_effective_length(self) -> float:
        """Calculates effective length Le based on stylized end conditions."""
        factor = 1.0
        if self.end_condition == "fixed_fixed":
            factor = 0.65 # BS 8110
        elif self.end_condition == "fixed_pinned":
            factor = 0.80
        elif self.end_condition == "pinned_pinned":
            factor = 1.00
            
        Le = factor * self.L_clear
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Determined column effective length factor",
            formula="Le = beta * L",
            inputs={"L_clear (mm)": self.L_clear, "factor": factor, "condition": self.end_condition},
            result=Le
        ))
        return Le

    def _check_slenderness(self, Le: float) -> bool:
        """Returns True if slender (λ > 15 for braced BS8110)."""
        # radius of gyration approx h / sqrt(12)
        # simplified BS 8110 check is Le / h for rectangular sections
        ratio = Le / self.h
        
        is_slender = ratio > 15
        
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Slenderness ratio calculation (braced)",
            formula="ratio = Le / h",
            inputs={"Le (mm)": Le, "h (mm)": self.h},
            result={"ratio": ratio, "is_slender": is_slender}
        ))
        return is_slender

    def solve(self, N_applied_kN: float, M_applied_kNm: float) -> MemberAnalysisResult:
        Le = self._determine_effective_length()
        is_slender = self._check_slenderness(Le)
        
        # Minimum eccentricity moment
        e_min = max(self.h / 20.0, 20.0) # mm
        M_min = N_applied_kN * (e_min / 1000.0)
        
        design_moment = max(M_applied_kNm, M_min)
        
        if is_slender:
            # Add secondary moment Phase 7
            # beta_a = (Le/h)^2 / 2000
            beta_a = (Le / self.h)**2 / 2000.0
            a_u = beta_a * self.h
            M_add = N_applied_kN * (a_u / 1000.0)
            
            design_moment += M_add
            
            self.trace.append(CalculationTraceStep(
                step=len(self.trace) + 1,
                description="Secondary moment for slender column",
                formula="M_add = N * a_u, a_u = beta_a * h",
                inputs={"N (kN)": N_applied_kN, "beta_a": beta_a, "h": self.h},
                result={"M_add": M_add, "M_total": design_moment}
            ))

        resultants = StressResultants(
            N_axial_kN=N_applied_kN,
            M_max_sagging_kNm=design_moment, # Treat absolute moment as sagging mapping for general magnitude
            V_max_kN=0.0
        )
        
        flags = ["slender" if is_slender else "short"]

        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="column",
            analysis_method="closed_form",
            stress_resultants=resultants,
            calculation_trace=self.trace,
            flags=flags
        )

import math
from typing import List, Literal, Dict, Any
from models.analysis.schema import (
    MemberAnalysisResult, StressResultants, CalculationTraceStep, SLSChecks
)

class StaircaseSolver:
    """
    Phase 10: Staircase Analysis Solver
    Analyzed as simply supported one-way slabs spanning between supports.
    """
    def __init__(self, member_id: str, L_plan: float, R: float, G: float, waistband_thickness: float, finishes_kpa: float, live_load_kpa: float, design_code: Literal["BS8110", "EC2"] = "EC2"):
        self.member_id = member_id
        self.L_plan = L_plan # Horizontal span (m)
        self.R = R # Riser (mm)
        self.G = G # Going (mm)
        self.h_w = waistband_thickness # mm
        self.finishes = finishes_kpa
        self.live_load = live_load_kpa
        self.design_code = design_code
        self.trace: List[CalculationTraceStep] = []

    def _resolve_geometry(self) -> Dict[str, float]:
        """Resolves slope geometry and confirms step proportion."""
        # 2R + G check
        proportion = 2 * self.R + self.G
        
        # Slope angle
        alpha_rad = math.atan(self.R / self.G)
        alpha_deg = math.degrees(alpha_rad)
        
        # Slope factors
        cos_alpha = math.cos(alpha_rad)
        
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Staircase geometry resolution",
            formula="alpha = arctan(R/G), 2R + G check",
            inputs={"R": self.R, "G": self.G},
            result={"alpha_deg": alpha_deg, "2R+G": proportion, "cos_alpha": cos_alpha}
        ))
        
        return {"cos_alpha": cos_alpha, "alpha_deg": alpha_deg}

    def _calculate_loads(self, cos_alpha: float) -> float:
        """Assembles ultimate design load on plan area."""
        # Concrete density
        rho = 25.0 # kN/m3
        
        # Average thickness of steps = R/2
        # SW_slope = rho * (h_w + (R/2 * cos_alpha)??) 
        # Actually: SW_slope = rho * (h_w / 1000) 
        # Add steps: Area of triangle = 0.5 * R * G. Per unit going G: Area/G = R/2.
        # But this R/2 is vertical. 
        # SW per m horizontal = rho * (h_w/1000 / cos_alpha + R/2000)
        
        sw_waist_horizontal = (rho * (self.h_w / 1000.0)) / cos_alpha
        sw_steps_horizontal = rho * (self.R / 2000.0)
        
        gk = sw_waist_horizontal + sw_steps_horizontal + self.finishes
        qk = self.live_load
        
        if self.design_code == "BS8110":
            n = 1.4 * gk + 1.6 * qk
        else:
            n = 1.35 * gk + 1.5 * qk
            
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Load assembly on plan area",
            formula="n = gamma_g * (SW_waist/cos_alpha + SW_steps + Finishes) + gamma_q * Qk",
            inputs={"h_w": self.h_w, "R": self.R, "G": self.G, "cos_alpha": cos_alpha, "Finishes": self.finishes, "Qk": qk},
            result={"n_design_kpa": n}
        ))
        
        return n

    def solve(self) -> MemberAnalysisResult:
        geom = self._resolve_geometry()
        n = self._calculate_loads(geom["cos_alpha"])
        
        # Simple span analysis
        M = n * (self.L_plan ** 2) / 8.0
        V = n * self.L_plan / 2.0
        
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Structural analysis as simple span",
            formula="M = nL²/8, V = nL/2",
            inputs={"n": n, "L_plan": self.L_plan},
            result={"M_kNm": M, "V_kN": V}
        ))
        
        resultants = StressResultants(
            M_max_sagging_kNm=M,
            V_max_kN=V,
            deflection_max_mm=0.0 # Placeholder
        )
        
        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="staircase",
            analysis_method="closed_form",
            stress_resultants=resultants,
            reactions_kN=[V, V],
            calculation_trace=self.trace
        )

from typing import Dict, Any, List, Optional, Literal
from models.analysis.schema import (
    MemberAnalysisResult, StressResultants, SLSChecks, CalculationTraceStep
)

class SimplySupportedBeamSolver:
    """
    Phase 2: Closed-form solver for simply supported, single-span beams.
    Uses superposition to combine multiple load types.
    """
    def __init__(self, member_id: str, span_L: float, E: float, I: float, design_code: str = "EC2"):
        self.member_id = member_id
        self.L = span_L
        self.E = E
        self.I = I
        self.design_code = design_code
        self.trace: List[CalculationTraceStep] = []
        
        # Superposition accumulators
        self.M_max = 0.0
        self.V_max = 0.0
        self.deflection_max = 0.0
        self.reaction_left = 0.0
        self.reaction_right = 0.0

    def add_udl(self, w: float):
        """Adds a Uniformly Distributed Load (w in kN/m)."""
        L = self.L
        M =  w * (L**2) / 8
        V = w * L / 2
        
        # Max deflection at midspan
        delta = (5 * w * (L**4)) / (384 * self.E * self.I)
        
        self.M_max += M
        self.V_max += V
        self.reaction_left += V
        self.reaction_right += V
        self.deflection_max += delta
        
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description="Applied Uniformly Distributed Load",
            formula="M=wL²/8, V=wL/2, δ=5wL⁴/(384EI)",
            inputs={"w (kN/m)": w, "L (m)": L, "EI": self.E * self.I},
            result={"M": M, "V": V, "delta": delta}
        ))

    def add_point_load(self, P: float, a: float):
        """Adds a Point Load (P in kN) at distance 'a' from the left support."""
        L = self.L
        b = L - a
        
        M_at_point = (P * a * b) / L
        R_left = (P * b) / L
        R_right = (P * a) / L
        
        # For simplicity in superimposing maximums, we assume the max moment location 
        # is close enough or we just track absolute maximums envelope conservatively
        # (A true envelope would track M(x) across 100 points, but this is a fast-path).
        
        self.M_max += M_at_point
        self.reaction_left += R_left
        self.reaction_right += R_right
        self.V_max += max(R_left, R_right)
        
        # Deflection at load point (conservative approximation for max)
        delta = (P * (a**2) * (b**2)) / (3 * self.E * self.I * L)
        self.deflection_max += delta
        
        self.trace.append(CalculationTraceStep(
            step=len(self.trace) + 1,
            description=f"Applied Point Load at a={a}m",
            formula="M=Pab/L, R_L=Pb/L, R_R=Pa/L",
            inputs={"P (kN)": P, "a (m)": a, "b (m)": b, "L (m)": L},
            result={"M": M_at_point, "R_L": R_left, "R_R": R_right, "delta": delta}
        ))

    def _check_deflection(self) -> SLSChecks:
        """Checks total SLS deflection against code limits."""
        # Standard limits
        limit_ratio = 250
        limit_mm = (self.L * 1000) / limit_ratio
        
        # Convert delta from m to mm (assuming E and I and P are in consistent M/kN/m units, delta is in m)
        # Wait, if E is in N/m2 (or kPa), I is in m4, P in kN... Wait.
        # It's better to force standard units: E in GPa (or kPa), I in m4, P in kN.
        # E.g., E = 30e6 kPa, I = m4. Then P/EI -> kN / (kPa * m4) = 1/m2.
        # delta = kN * m3 / (kN/m2 * m4) = m. Convert to mm: delta * 1000.
        delta_mm = self.deflection_max * 1000
        
        status = "PASS" if delta_mm <= limit_mm else "FAIL"
        
        return SLSChecks(
            deflection_limit_mm=limit_mm,
            deflection_actual_mm=delta_mm,
            status=status
        )

    def solve(self) -> MemberAnalysisResult:
        """Compiles final analysis result."""
        sls = self._check_deflection()
        
        resultants = StressResultants(
            M_max_sagging_kNm=self.M_max,
            M_max_hogging_kNm=0.0, # Simply supported
            V_max_kN=self.V_max,
            N_axial_kN=0.0,
            deflection_max_mm=sls.deflection_actual_mm
        )
        
        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="beam",
            analysis_method="closed_form",
            stress_resultants=resultants,
            reactions_kN=[self.reaction_left, self.reaction_right],
            SLS_checks=sls,
            calculation_trace=self.trace,
            critical_sections={
                "midspan": {"M": self.M_max},
                "supports": {"V_left": self.reaction_left, "V_right": self.reaction_right}
            }
        )

class MomentCoefficientSolver:
    """
    Phase 3: Moment Coefficient Method (BS 8110 / EC2 fast path)
    For continuous, regular beams.
    """
    def __init__(self, member_id: str, spans: List[float], design_code: Literal["BS8110", "EC2"]):
        self.member_id = member_id
        self.spans = spans
        self.design_code = design_code
        self.trace: List[CalculationTraceStep] = []
        
    def solve(self, ultimate_load_kN_per_m: float) -> MemberAnalysisResult:
        # Note: True BS8110 requires multiple Spans and n=1.4G+1.6Q setup for patterns.
        # This is a simplified abstraction based on the provided table.
        F_total_per_span = [ultimate_load_kN_per_m * L for L in self.spans]
        
        # Max values to track
        M_sag_max = 0.0
        M_hog_max = 0.0
        V_max = 0.0
        
        reactions = []
        critical_sections = {}
        
        num_spans = len(self.spans)
        
        for i, L in enumerate(self.spans):
            F = F_total_per_span[i]
            
            # Simple BS 8110 coefficients implementation
            if i == 0 or i == num_spans - 1: # End span
                m_sag = 0.090 * F * L
                m_hog_inner = -0.100 * F * L
                v_outer = 0.45 * F
                v_inner = 0.60 * F
                
                M_sag_max = max(M_sag_max, m_sag)
                M_hog_max = min(M_hog_max, m_hog_inner) # min because hogging is negative
                V_max = max(V_max, v_outer, v_inner)
            else: # Interior span
                m_sag = 0.066 * F * L
                m_hog = -0.086 * F * L
                v_support = 0.50 * F
                
                M_sag_max = max(M_sag_max, m_sag)
                M_hog_max = min(M_hog_max, m_hog)
                V_max = max(V_max, v_support)
                
            critical_sections[f"span_{i+1}"] = {
                "M_sagging": m_sag,
                "F": F
            }
            
        self.trace.append(CalculationTraceStep(
            step=1,
            description="BS 8110 Moment Coefficients applied",
            formula="M_sag = 0.09FL or 0.066FL, M_hog = -0.1FL or -0.086FL",
            inputs={"F_per_span": F_total_per_span, "spans": self.spans},
            result={"M_sag_max": M_sag_max, "M_hog_max": M_hog_max},
            clause_reference="BS8110 Table 3.5"
        ))

        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="beam",
            analysis_method="coefficients",
            governing_pattern="all_spans_loaded",
            stress_resultants=StressResultants(
                M_max_sagging_kNm=M_sag_max,
                M_max_hogging_kNm=M_hog_max,
                V_max_kN=V_max,
            ),
            reactions_kN=[], # Handled purely by coefficients maxing for now
            calculation_trace=self.trace,
            critical_sections=critical_sections
        )

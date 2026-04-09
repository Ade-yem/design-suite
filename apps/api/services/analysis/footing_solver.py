from typing import Dict, Any, List, Literal
from models.analysis.schema import (
    MemberAnalysisResult, StressResultants, CalculationTraceStep
)

class PadFootingSolver:
    """
    Phase 8: Isolated Pad Footing Solver
    Sizes the footing and calculates critical stress resultants.
    """
    def __init__(self, member_id: str, col_c1: float, col_c2: float, qa_allowable_kpa: float):
        self.member_id = member_id
        self.col_c1 = col_c1 # mm
        self.col_c2 = col_c2 # mm
        self.qa = qa_allowable_kpa
        self.trace: List[CalculationTraceStep] = []

    def solve(self, N_sls_kN: float, N_uls_kN: float, M_uls_kNm: float = 0.0) -> MemberAnalysisResult:
        # Step 1: Size footing (assume self weight ~ 10% of N_sls)
        sw_est = 0.1 * N_sls_kN
        A_req = (N_sls_kN + sw_est) / self.qa
        
        # Assume square footing
        import math
        B_req = math.sqrt(A_req)
        B = math.ceil(B_req * 10) / 10.0 # Round up to nearest 100mm
        L = B
        
        self.trace.append(CalculationTraceStep(
            step=1,
            description="Serviceability sizing of footing",
            formula="A = (N_sls + sw) / qa",
            inputs={"N_sls": N_sls_kN, "sw_est": sw_est, "qa": self.qa},
            result={"A_req_m2": A_req, "B_m": B, "L_m": L}
        ))
        
        # Step 2: Ultimate Bearing Pressure
        q_uls = N_uls_kN / (B * L)
        
        # With moment (simplification max pressure)
        if M_uls_kNm > 0:
            q_max = q_uls + M_uls_kNm / ((B * L**2) / 6.0)
            q_uls_design = q_max
        else:
            q_uls_design = q_uls
            
        self.trace.append(CalculationTraceStep(
            step=2,
            description="Ultimate bearing pressure",
            formula="q = N/A + M/Z",
            inputs={"N_uls": N_uls_kN, "M_uls": M_uls_kNm, "B": B, "L": L},
            result={"q_uls_design_kPa": q_uls_design}
        ))
        
        # Step 3: Bending Moment (critical section at column face)
        col_c1_m = self.col_c1 / 1000.0
        overhang_m = (L - col_c1_m) / 2.0
        
        M_design = q_uls_design * B * (overhang_m ** 2) / 2.0
        
        self.trace.append(CalculationTraceStep(
            step=3,
            description="Design moment at column face",
            formula="M = q * B * overhang² / 2",
            inputs={"q_uls": q_uls_design, "overhang_m": overhang_m, "B": B},
            result={"M_design_kNm": M_design}
        ))
        
        resultants = StressResultants(
            M_max_sagging_kNm=M_design,
            V_max_kN=q_uls_design * B * overhang_m # Simple beam shear estimate
        )
        
        return MemberAnalysisResult(
            member_id=self.member_id,
            member_type="footing",
            analysis_method="closed_form",
            stress_resultants=resultants,
            calculation_trace=self.trace,
            critical_sections={
                "geometry": {"B_m": B, "L_m": L},
                "pressures": {"q_uls_max": q_uls_design}
            }
        )

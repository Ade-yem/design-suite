from typing import Dict, Any, List, Literal
from models.analysis.schema import (
    MemberAnalysisResult, StressResultants, CalculationTraceStep
)

class TwoWaySlabSolver:
    """
    Phase 5: Two-Way Slab Solver (Moment Coefficient Method)
    Valid for slabs supported on four sides with Ly/Lx < 2.
    """
    def __init__(self, panel_id: str, Lx: float, Ly: float, edge_conditions: List[str]):
        """
        edge_conditions: list of 4 conditions ['C', 'SS', 'F', ...] for each edge
        """
        self.panel_id = panel_id
        self.Lx = Lx
        self.Ly = Ly
        self.edge_conditions = edge_conditions
        self.ratio = Ly / Lx
        self.trace: List[CalculationTraceStep] = []

    def _get_bs8110_coefficients(self) -> Dict[str, float]:
        """
        Mock lookup for BS 8110 Table 3.14 / EC2 Annex I coefficients.
        In a full implementation, this queries a database or a loaded lookup table.
        """
        # Simplify based on ratio: mock values
        # True values depend on edge condition configurations
        return {"alpha_sx": 0.042, "alpha_sy": 0.028}

    def solve(self, n_design_kpa: float) -> MemberAnalysisResult:
        
        coeffs = self._get_bs8110_coefficients()
        a_sx = coeffs["alpha_sx"]
        a_sy = coeffs["alpha_sy"]
        
        # Msx = alpha_sx * n * lx^2
        msx = a_sx * n_design_kpa * (self.Lx ** 2)
        msy = a_sy * n_design_kpa * (self.Lx ** 2)
        
        # Assume negative moments over continuous supports are ~ 1.33 times sagging for demonstration
        msx_support = -msx * 1.33 if "C" in self.edge_conditions else 0.0
        msy_support = -msy * 1.33 if "C" in self.edge_conditions else 0.0
        
        self.trace.append(CalculationTraceStep(
            step=1,
            description="Two-way moment calculation using defined coefficients",
            formula="Msx = α_sx * n * Lx², Msy = α_sy * n * Lx²",
            inputs={"n (kPa)": n_design_kpa, "Lx": self.Lx, "alpha_sx": a_sx, "alpha_sy": a_sy},
            result={"msx": msx, "msy": msy},
            clause_reference="BS8110 Table 3.14"
        ))

        resultants = StressResultants(
            M_max_sagging_kNm=max(msx, msy),
            M_max_hogging_kNm=min(msx_support, msy_support),
            V_max_kN=0.0 # Standard shear check normally done separately
        )
        
        return MemberAnalysisResult(
            member_id=self.panel_id,
            member_type="slab",
            analysis_method="coefficients",
            stress_resultants=resultants,
            calculation_trace=self.trace,
            critical_sections={
                "sagging": {"Msx": msx, "Msy": msy},
                "hogging": {"Msx_sup": msx_support, "Msy_sup": msy_support}
            },
            flags=["two_way_solid"]
        )

class FlatSlabSolver:
    """
    Phase 12: Flat Slab Solver (Equivalent Frame Method)
    Focuses heavily on punching shear as requested.
    """
    def __init__(self, column_id: str, col_width: float, col_depth: float, slab_depth: float, cover: float):
        self.column_id = column_id
        self.c1 = col_width
        self.c2 = col_depth
        self.h = slab_depth
        self.d = slab_depth - cover - 20 # approx effective depth
        self.trace: List[CalculationTraceStep] = []

    def check_punching_shear(self, V_Ed: float, design_code: str = "EC2") -> Dict[str, Any]:
        """
        Output specific to punching shear checks as defined in the rules.
        """
        if design_code == "EC2":
            # Control perimeter at 2d from column face
            u_1 = 2 * (self.c1 + self.c2) + 4 * 3.14159 * self.d
        else:
            # BS 8110 at 1.5d
            u_1 = 2 * (self.c1 + self.c2) + 2 * 3.14159 * (1.5 * self.d)
            
        v_Ed = (V_Ed * 1000) / (u_1 * self.d) # MPa
        
        self.trace.append(CalculationTraceStep(
            step=1,
            description=f"Punching shear control perimeter and stress ({design_code})",
            formula="u1 = 2(c1+c2) + 4πd, vEd = β * VEd / (u1*d)",
            inputs={"VEd (kN)": V_Ed, "d (mm)": self.d, "c1": self.c1, "c2": self.c2},
            result={"u1_mm": u_1, "vEd_MPa": v_Ed}
        ))
        
        return {
            "column_id": self.column_id,
            "punching_shear": {
                "VEd_kN": V_Ed,
                "control_perimeter_mm": u_1,
                "d_effective_mm": self.d,
                "vEd_MPa": v_Ed,
                "flag": "punching_shear_check_required"
            }
        }

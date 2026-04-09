from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal

class CalculationTraceStep(BaseModel):
    """
    A traceable step in any structural calculation for verifiable output.
    """
    step: int = Field(..., description="Step number in the sequence")
    description: str = Field(..., description="Description of the calculation step")
    formula: Optional[str] = Field(None, description="The conceptual or exact formula used")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Variables input into the formula")
    result: Any = Field(..., description="Computed result")
    clause_reference: Optional[str] = Field(None, description="Code clause reference (e.g., BS8110 Table 3.5)")

class SLSChecks(BaseModel):
    """
    Serviceability Limit State check results.
    """
    deflection_limit_mm: float
    deflection_actual_mm: float
    status: Literal["PASS", "FAIL"]

class StressResultants(BaseModel):
    """
    Maximum stress resultants on a member used for downstream design.
    """
    M_max_sagging_kNm: float = 0.0
    M_max_hogging_kNm: float = 0.0
    V_max_kN: float = 0.0
    N_axial_kN: float = 0.0
    deflection_max_mm: float = 0.0

class MemberAnalysisResult(BaseModel):
    """
    Comprehensive analysis output for a single structural member linking geometry to internal forces.
    """
    member_id: str
    member_type: Literal["beam", "slab", "column", "wall", "footing", "staircase"]
    analysis_method: Literal["closed_form", "coefficients", "matrix_stiffness"]
    stress_resultants: StressResultants
    critical_sections: Dict[str, Any] = Field(default_factory=dict)
    reactions_kN: List[float] = Field(default_factory=list)
    governing_pattern: Optional[str] = None
    SLS_checks: Optional[SLSChecks] = None
    calculation_trace: List[CalculationTraceStep] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)

class AnalysisOutputSchema(BaseModel):
    """
    Full schema defining the payload from the Analysis Engine to the Design Suite.
    """
    analysis_id: str = Field(..., description="Unique analysis identifier")
    design_code: Literal["BS8110", "EC2"] = Field(..., description="Design code used for analysis constraints")
    members: List[MemberAnalysisResult] = Field(default_factory=list, description="Results for all analyzed members")

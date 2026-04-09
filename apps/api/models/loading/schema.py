from enum import Enum, auto
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union

class LoadType(str, Enum):
    """Types of loads."""
    DEAD = "dead"           # Gk
    IMPOSED = "imposed"     # Qk
    WIND = "wind"           # Wk
    NOTIONAL = "notional"   # Nh

class SlabType(str, Enum):
    """Types of slabs."""
    SOLID = "solid"
    RIBBED = "ribbed"
    WAFFLE = "waffle"
    FLAT = "flat"

class OccupancyCategory(str, Enum):
    """Occupancy category for imposed loads."""
    RESIDENTIAL = "residential"
    OFFICE = "office"
    RETAIL = "retail"
    ROOF_ACCESSIBLE = "roof_accessible"
    ROOF_NON_ACCESSIBLE = "roof_non_accessible"
    STAIRS = "stairs"
    CUSTOM = "custom"

class DesignCode(str, Enum):
    """Supported design codes for loading combinations."""
    BS8110 = "BS8110"
    EC2 = "EC2"

class LimitState(str, Enum):
    """Limit states for design."""
    ULS_DOMINANT = "ULS_DOMINANT"
    ULS_WIND = "ULS_WIND"
    SLS_CHARACTERISTIC = "SLS_CHARACTERISTIC"
    SLS_QUASI_PERMANENT = "SLS_QUASI_PERMANENT"
    SLS_FREQUENT = "SLS_FREQUENT"

class AreaLoad(BaseModel):
    """Area load model (kN/m²)."""
    name: str = Field(..., description="Description of the load (e.g. 'slab finishes')")
    load_type: LoadType = Field(..., description="Type of load")
    value: float = Field(..., ge=0, description="Characteristic load value in kN/m²")

class LineLoad(BaseModel):
    """Line load model (kN/m)."""
    name: str = Field(..., description="Description of the load (e.g. 'partition wall')")
    load_type: LoadType = Field(..., description="Type of load")
    value: float = Field(..., ge=0, description="Characteristic load value in kN/m")

class PointLoad(BaseModel):
    """Point load model (kN)."""
    name: str = Field(..., description="Description of the load (e.g. 'column reaction')")
    load_type: LoadType = Field(..., description="Type of load")
    value: float = Field(..., ge=0, description="Characteristic load value in kN")
    position: Optional[float] = Field(None, description="Position along the structure in m")

class PunchingShearData(BaseModel):
    """Data for punching shear verification in flat slabs."""
    column_id: str
    axial_load_uls: float = Field(..., description="Factored axial load at column (kN)")
    moments_uls: Dict[str, float] = Field(default_factory=dict, description="Factored moments (Mx, My) at column (kNm)")
    control_perimeter_m: float = Field(..., description="Initial control perimeter length u0 in m")
    slab_d_eff_mm: float = Field(..., description="Effective depth of slab at column strip")

class SpanLoads(BaseModel):
    """Loads applied on a specific span."""
    span_id: str
    length_m: float
    loads: Dict[str, Union[float, List[Dict]]] = Field(
        ...,
        description="Dictionary of applied loads"
    )
    pattern_loading_flag: bool = Field(False)

class MemberLoadOutput(BaseModel):
    """Schema for serialized member load output."""
    member_id: str
    member_type: str
    design_code: DesignCode
    spans: List[SpanLoads]
    combination_used: str
    source_slabs: List[str] = Field(default_factory=list)
    punching_shear_checks: List[PunchingShearData] = Field(default_factory=list)
    notes: Optional[str] = None

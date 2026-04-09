"""
Column Section Model
====================
Structured object for BS 8110-1:1997 column design.
"""
from dataclasses import dataclass, field

@dataclass
class ColumnSection:
    """
    Represents a rectangular column.
    h is the depth (dimension in direction of major bending / x-axis).
    b is the width (dimension in direction of minor bending / y-axis).
    """
    b: float              # Width (mm)
    h: float              # Depth (mm)
    l_ex: float           # Effective buckling length for x-axis (mm)
    l_ey: float           # Effective buckling length for y-axis (mm)
    cover: float          # Nominal concrete cover (mm)
    fcu: float            # Characteristic concrete strength (N/mm²)
    fy: float             # Characteristic main steel strength (N/mm²)
    link_dia: float = 8.0
    bar_dia: float = 16.0 # Assumed main bar diameter
    
    braced: bool = True   # Braced or unbraced
    
    d: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)
    
    def __post_init__(self):
        self.d = self.h - self.cover - self.link_dia - (self.bar_dia / 2.0)
        # Minimum steel — BS 8110 Table 3.25
        # Column: 0.4% bh
        self.As_min = 0.004 * self.b * self.h
        
        # Maximum steel — BS 8110 Cl 3.12.6.2 (6% for vertically cast)
        self.As_max = 0.06 * self.b * self.h
        
        self._validate()

    def _validate(self):
        if self.d <= 0:
            raise ValueError(f"Derived effective depth d = {self.d:.1f} mm <= 0")

    def summary(self) -> str:
        lines = [
            f"ColumnSection ({'Braced' if self.braced else 'Unbraced'})",
            f"  b × h          : {self.b} × {self.h} mm",
            f"  l_ex / l_ey    : {self.l_ex} / {self.l_ey} mm",
            f"  Cover          : {self.cover} mm",
            f"  fcu / fy       : {self.fcu} / {self.fy} N/mm²",
            f"  As,min         : {self.As_min:.1f} mm²",
            f"  As,max         : {self.As_max:.1f} mm²",
        ]
        return "\n".join(lines)

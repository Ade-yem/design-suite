"""
Structural Analysis Module
==========================
Calculates design actions (M, V) for standard beam configurations.
Supports UDLs and Point Loads for simply supported, cantilever, and fixed beams.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class PointLoad:
    P: float  # Load (N)
    a: float  # Distance from left support (mm)


@dataclass
class UDL:
    w: float  # Load intensity (N/mm)


class BeamAnalysis:
    def __init__(self, span: float, support_condition: str = "simple"):
        self.L = span
        self.support_condition = support_condition.lower()
        self.point_loads: List[PointLoad] = []
        self.udls: List[UDL] = []

    def add_point_load(self, P: float, a: float):
        self.point_loads.append(PointLoad(P, a))

    def add_udl(self, w: float):
        self.udls.append(UDL(w))

    def solve(self) -> Dict[str, Any]:
        """
        Calculate maximum design moment (M_max) and shear force (V_max).
        Returns a dict with values and a description of the loading.
        """
        M_max = 0.0
        V_max = 0.0
        V_left = 0.0
        V_right = 0.0

        # ----------------------------------------------------------- Simply Supported
        if self.support_condition == "simple":
            # Reactions and Shear from UDLs
            for udl in self.udls:
                R = (udl.w * self.L) / 2.0
                V_left += R
                V_right += R
                M_max += (udl.w * self.L**2) / 8.0

            # Reactions and Shear from Point Loads
            for pl in self.point_loads:
                R_left = pl.P * (self.L - pl.a) / self.L
                R_right = pl.P * pl.a / self.L
                V_left += R_left
                V_right += R_right
                # Moment at load point
                M_load = (pl.P * pl.a * (self.L - pl.a)) / self.L
                M_max = max(M_max, M_load)

            V_max = max(V_left, V_right)

        # ----------------------------------------------------------- Cantilever
        elif self.support_condition == "cantilever":
            # Max moment and shear at fixed end (left)
            for udl in self.udls:
                V_left += udl.w * self.L
                M_max += (udl.w * self.L**2) / 2.0

            for pl in self.point_loads:
                V_left += pl.P
                M_max += pl.P * pl.a

            V_max = V_left
            # Note: For cantilever, we treat M as negative (hogging) usually
            M_max = -abs(M_max)

        # ----------------------------------------------------------- Continuous / Fixed
        # (Simplified as single-span fixed-fixed for "expert" example)
        elif self.support_condition == "continuous":
            # Using conservative coefficients for a first pass
            # M_max (mid-span sagging) ≈ wL²/12 or wL²/10
            # M_max (support hogging) ≈ wL²/8
            for udl in self.udls:
                V_left += (udl.w * self.L) / 2.0
                M_sag = (udl.w * self.L**2) / 12.0
                M_hog = -(udl.w * self.L**2) / 8.0
                M_max = max(abs(M_sag), abs(M_hog))
                if abs(M_hog) > abs(M_sag):
                    M_max = M_hog

            for pl in self.point_loads:
                # Fixed-fixed point load approximations
                V_left += pl.P / 2.0 # approx
                M_max = max(M_max, (pl.P * self.L) / 8.0)

            V_max = V_left

        return {
            "M_max": round(M_max, 0),
            "V_max": round(V_max, 0),
            "note": (
                f"Analysis ({self.support_condition}): "
                f"L={self.L}mm, {len(self.udls)} UDL(s), {len(self.point_loads)} Point load(s)."
            )
        }

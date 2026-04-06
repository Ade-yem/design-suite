"""
BS 8110-1:1997  –  Column Interaction Diagram Service
======================================================
Generates a series of (M, N) points to plot the interaction envelope for a column.
"""

from typing import List, Tuple
from models.column import ColumnSection
from services.calculations.bs8110.column import calculate_axial_bending_capacity

def generate_interaction_data(
    section: ColumnSection, 
    Asc: float, 
    num_points: int = 50
) -> List[Tuple[float, float]]:
    """
    Generates a list of (M, N) points representing the capacity envelope.
    M is returned in N.mm, N in Newtons.
    """
    points = []
    
    # 1. Pure Axial point (N_max, M=0)
    # Theoretically x = infinity. We'll use a very large x.
    n_pure, m_pure = calculate_axial_bending_capacity(
        100 * section.h, Asc, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy
    )
    # Manual override to ensure M=0 for pure axial if calculation is slightly offset
    points.append((0.0, n_pure))
    
    # 2. Iterate neutral axis depths from h/10 to 1.5h
    # This covers everything from mostly tension to mostly compression.
    x_min = 0.05 * section.h
    x_max = 1.2 * section.h
    
    for i in range(num_points):
        x = x_min + (x_max - x_min) * (i / (num_points - 1))
        n_cap, m_cap = calculate_axial_bending_capacity(
            x, Asc, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy
        )
        points.append((m_cap, n_cap))
        
    # 3. Add a few points for the tension zone (N < 0) if necessary
    # However, for most columns, sagging zone is the focus.
    
    # Sort points by N to ensure a smooth line
    points.sort(key=lambda p: p[1], reverse=True)
    
    return points

def get_special_points(section: ColumnSection, Asc: float) -> dict:
    """
    Returns specific points of interest on the interaction diagram.
    """
    # Balanced point: tension steel just yields
    # eps_yield = fy / (1.15 * 200000)
    # 0.0035 / x = eps_yield / (d - x)
    # x_balanced = 0.0035 * d / (0.0035 + eps_yield)
    fy = section.fy
    eps_yield = fy / (1.15 * 200000.0)
    x_bal = (0.0035 * section.d) / (0.0035 + eps_yield)
    n_bal, m_bal = calculate_axial_bending_capacity(
        x_bal, Asc, section.b, section.h, section.d, section.h - section.d, section.fcu, fy
    )
    
    return {
        "pure_axial": points_to_kn_m(0.0, calculate_axial_bending_capacity(100*section.h, Asc, section.b, section.h, section.d, section.h-section.d, section.fcu, fy)[0]),
        "balanced": points_to_kn_m(m_bal, n_bal)
    }

def points_to_kn_m(m_nmm: float, n_n: float) -> Tuple[float, float]:
    return (round(m_nmm / 1e6, 2), round(n_n / 1e3, 2))

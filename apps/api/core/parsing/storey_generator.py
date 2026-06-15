"""
core/parsing/storey_generator.py
================================
Implements 3D storey extrapolation and vertical column stack linkage algorithms
for multi-storey structural models.
"""

from __future__ import annotations

import copy
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def extrapolate_storeys(
    typical_members: list[dict[str, Any]],
    num_storeys: int,
    storey_height_m: float,
    layouts_processed: list[str],
) -> list[dict[str, Any]]:
    """
    Extrapolates 2D typical floor members into a 3D multi-storey member array.

    - If num_storeys == 1 and only 1 layout is processed, attaches default level
      metadata but preserves original member IDs for backward compatibility.
    - If num_storeys > 1 or multiple layouts exist, duplicates/maps geometry
      and prefixes member IDs with their storey codes (e.g., 'L01-B1').

    Parameters
    ----------
    typical_members : list[dict]
        Parsed 2D members (beams, columns, slabs) from DXF/PDF.
    num_storeys : int
        Number of storeys in the building structure.
    storey_height_m : float
        Typical height of each storey in meters.
    layouts_processed : list[str]
        List of sheet layout tab names processed from the DXF file.

    Returns
    -------
    list[dict]
        Extrapolated list of 3D member dictionaries.
    """
    # Input validation
    if num_storeys < 1:
        raise ValueError(f"num_storeys must be >= 1, got {num_storeys}")
    if storey_height_m <= 0.0:
        raise ValueError(f"storey_height_m must be positive, got {storey_height_m}")

    logger.info(
        "Extrapolating storeys: num_storeys=%d, height=%s, layouts=%s",
        num_storeys, storey_height_m, layouts_processed
    )

    if not typical_members:
        return []

    # If it is a simple single-storey project, add metadata and return.
    if num_storeys == 1 and len(layouts_processed) <= 1:
        result = []
        for m in typical_members:
            m_copy = copy.deepcopy(m)
            m_copy["storey"] = "L01"
            m_copy["elevation_m"] = 0.0
            result.append(m_copy)
        return result

    # Multi-storey or multi-layout processing
    extrapolated_members: list[dict[str, Any]] = []

    # Filter out layout sheets that contain structural members
    active_layouts = []
    for layout in layouts_processed:
        layout_has_members = any(m.get("layout_name") == layout for m in typical_members)
        if layout_has_members:
            active_layouts.append(layout)

    # Fallback to all layouts if none specifically had members
    if not active_layouts:
        active_layouts = layouts_processed if layouts_processed else ["Model"]

    for i in range(1, num_storeys + 1):
        storey_code = f"L{i:02d}"
        elevation = (i - 1) * storey_height_m

        # Select layout to map to this storey
        if len(active_layouts) > 1:
            layout_idx = min(i - 1, len(active_layouts) - 1)
            target_layout = active_layouts[layout_idx]
            # Get members belonging to this layout tab
            floor_members = [m for m in typical_members if m.get("layout_name") == target_layout]
            # Fallback if specific layout has no members
            if not floor_members:
                floor_members = typical_members
        else:
            floor_members = typical_members

        for m in floor_members:
            m_copy = copy.deepcopy(m)
            m_copy["storey"] = storey_code
            m_copy["elevation_m"] = elevation
            
            # Prefix member ID with storey code to guarantee uniqueness
            orig_id = m_copy.get("member_id", "MEMBER")
            m_copy["member_id"] = f"{storey_code}-{orig_id}"
            
            extrapolated_members.append(m_copy)

    # Establish vertical linkages for column members
    link_column_stacks(extrapolated_members, tolerance_mm=300.0)

    return extrapolated_members


def link_column_stacks(
    members: list[dict[str, Any]], 
    tolerance_mm: float = 300.0
) -> None:
    """
    Finds columns on adjacent storeys and links them vertically (parent/child).
    Modifies the member dictionaries in-place.

    Parameters
    ----------
    members : list[dict]
        Extrapolated member array.
    tolerance_mm : float
        Max horizontal distance between centroids to consider them aligned.
    """
    columns = [m for m in members if m.get("member_type") == "column"]
    if not columns:
        return

    # Group columns by storey code
    columns_by_storey: dict[str, list[dict[str, Any]]] = {}
    for col in columns:
        storey = col.get("storey", "L01")
        columns_by_storey.setdefault(storey, []).append(col)

    # Sort storey codes (e.g. L01, L02, L03)
    sorted_storeys = sorted(columns_by_storey.keys())

    for idx in range(len(sorted_storeys) - 1):
        curr_storey = sorted_storeys[idx]
        next_storey = sorted_storeys[idx + 1]

        curr_cols = columns_by_storey[curr_storey]
        next_cols = columns_by_storey[next_storey]

        for col_curr in curr_cols:
            centroid_curr = col_curr.get("center_point")
            if not centroid_curr or "x" not in centroid_curr or "y" not in centroid_curr:
                continue

            x_curr = centroid_curr["x"]
            y_curr = centroid_curr["y"]

            best_match: dict[str, Any] | None = None
            best_dist = float("inf")

            for col_next in next_cols:
                centroid_next = col_next.get("center_point")
                if not centroid_next or "x" not in centroid_next or "y" not in centroid_next:
                    continue

                x_next = centroid_next["x"]
                y_next = centroid_next["y"]

                dist = math.sqrt((x_curr - x_next) ** 2 + (y_curr - y_next) ** 2)
                if dist <= tolerance_mm and dist < best_dist:
                    best_match = col_next
                    best_dist = dist

            if best_match:
                # Initialize meta dicts if not present
                col_curr.setdefault("meta", {})
                best_match.setdefault("meta", {})

                col_curr["meta"]["child_column_id"] = best_match["member_id"]
                best_match["meta"]["parent_column_id"] = col_curr["member_id"]

                logger.debug(
                    "Linked columns vertically: %s (below) <-> %s (above), dist=%.2f mm",
                    col_curr["member_id"], best_match["member_id"], best_dist
                )

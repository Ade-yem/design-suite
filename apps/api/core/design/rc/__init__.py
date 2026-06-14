"""
Module for reinforced concrete design
"""
from typing import Any, Dict, Optional

def design_member(
    analysis_result: Dict[str, Any],
    geometry_meta: Dict[str, Any],
    design_code: str = "BS8110",
) -> Dict[str, Any]:
    """
    Dispatcher function to route design calculation requests to appropriate material modules.

    Parameters
    ----------
    analysis_result : dict
        Analysis output containing forces/moments in stress_resultants.
    geometry_meta : dict
        Geometry parameters from parsed DXF/user edits.
    design_code : str
        "BS8110" or "EC2".

    Returns
    -------
    dict
        Design results.
    """
    member_type = (
        analysis_result.get("member_type")
        or geometry_meta.get("member_type")
        or "beam"
    )
    member_type = member_type.lower()
    
    # Extract stress resultants
    stress = analysis_result.get("stress_resultants", {})
    if hasattr(stress, "model_dump"):
        stress = stress.model_dump()
        
    M_sag = stress.get("M_max_sagging_kNm", 0.0)
    M_hog = stress.get("M_max_hogging_kNm", 0.0)
    V_max = stress.get("V_max_kN", 0.0)
    N_axial = stress.get("N_axial_kN", 0.0)

    # Convert kNm -> Nmm and kN -> N
    M = M_sag if M_sag >= M_hog else -M_hog
    M_Nmm = M * 1e6
    V_N = V_max * 1e3
    N_N = N_axial * 1e3

    # Common parameters with fallbacks
    b = float(geometry_meta.get("b_mm") or geometry_meta.get("b") or 225.0)
    h = float(geometry_meta.get("h_mm") or geometry_meta.get("h") or 450.0)
    cover = float(geometry_meta.get("cover_mm") or geometry_meta.get("cover") or 25.0)
    
    # concrete grade & steel yield
    fcu = float(geometry_meta.get("fcu_MPa") or geometry_meta.get("fcu") or 30.0)
    fck = float(geometry_meta.get("fck_MPa") or geometry_meta.get("fck") or fcu)
    fy = float(geometry_meta.get("fy_MPa") or geometry_meta.get("fy") or 460.0)
    fyk = float(geometry_meta.get("fyk_MPa") or geometry_meta.get("fyk") or fy)
    fyv = float(geometry_meta.get("fyv_MPa") or geometry_meta.get("fyv") or 250.0)
    fywk = float(geometry_meta.get("fywk_MPa") or geometry_meta.get("fywk") or fyv)
    
    link_dia = float(geometry_meta.get("link_dia_mm") or geometry_meta.get("link_dia") or 8.0)
    bar_dia = float(geometry_meta.get("bar_dia_mm") or geometry_meta.get("bar_dia") or 20.0)
    comp_bar_dia = float(geometry_meta.get("comp_bar_dia_mm") or geometry_meta.get("comp_bar_dia") or 16.0)

    span = float(
        geometry_meta.get("span_mm")
        or geometry_meta.get("span")
        or geometry_meta.get("lx_mm")
        or geometry_meta.get("lx")
        or 5000.0
    )
    support_condition = str(geometry_meta.get("support_condition") or "simple")
    
    code = design_code.upper() if design_code else "BS8110"

    if code == "BS8110":
        if member_type == "beam":
            from models.bs8110.beam import BeamSection
            from core.design.rc.bs8110.beam import calculate_beam_reinforcement
            
            section = BeamSection(
                b=b, h=h, cover=cover, fcu=fcu, fy=fy, fyv=fyv,
                link_dia=link_dia, bar_dia=bar_dia, comp_bar_dia=comp_bar_dia,
                section_type=geometry_meta.get("section_type", "rectangular"),
                support_condition=support_condition,
                bf=geometry_meta.get("bf"), hf=geometry_meta.get("hf"),
                beta_b=geometry_meta.get("beta_b", 1.0)
            )
            res = calculate_beam_reinforcement(section, M=M_Nmm, V=V_N, span=span)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "beam"
            res["design_code"] = "BS8110"
            return res
            
        elif member_type == "column":
            from models.bs8110.column import ColumnSection
            from core.design.rc.bs8110.column import calculate_column_reinforcement
            
            section = ColumnSection(
                b=b, h=h,
                l_ex=float(geometry_meta.get("l_ex_mm") or geometry_meta.get("l_ex") or span),
                l_ey=float(geometry_meta.get("l_ey_mm") or geometry_meta.get("l_ey") or span),
                cover=cover, fcu=fcu, fy=fy, link_dia=link_dia, bar_dia=bar_dia,
                braced=bool(geometry_meta.get("braced", True))
            )
            res = calculate_column_reinforcement(section, N=N_N, Mx=M_Nmm, My=0.0)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "column"
            res["design_code"] = "BS8110"
            return res
            
        elif member_type == "slab":
            from models.bs8110.slab import SlabSection
            from core.design.rc.bs8110.slab import calculate_slab_reinforcement
            
            lx = float(geometry_meta.get("lx_mm") or geometry_meta.get("lx") or span)
            ly = float(geometry_meta.get("ly_mm") or geometry_meta.get("ly") or lx)
            
            section = SlabSection(
                h=h, cover=cover, fcu=fcu, lx=lx, ly=ly, fy=fy,
                slab_type=geometry_meta.get("slab_type", "one-way"),
                panel_type=geometry_meta.get("panel_type"),
                support_condition=support_condition,
                beta_b=geometry_meta.get("beta_b", 1.0),
                layer=geometry_meta.get("layer", "outer"),
                bar_dia=bar_dia,
                bar_dia_outer=geometry_meta.get("bar_dia_outer", 0.0),
                bar_dia_sec=geometry_meta.get("bar_dia_sec", 10.0)
            )
            res = calculate_slab_reinforcement(section, n_or_M=M_Nmm, F_or_V=V_N, span_or_gk=span)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "slab"
            res["design_code"] = "BS8110"
            return res
            
        else:
            return {
                "member_id": analysis_result.get("member_id", "unknown"),
                "member_type": member_type,
                "design_code": "BS8110",
                "status": "skipped",
                "reason": f"Design not implemented for member type {member_type} under BS8110.",
                "reinforcement_description": "None",
                "notes": [f"Member type {member_type} design skipped."],
                "warnings": []
            }
            
    else:  # EC2
        if member_type == "beam":
            from models.ec2.beam import EC2BeamSection
            from core.design.rc.eurocode2.beam import calculate_beam_reinforcement as calculate_beam_ec2
            
            section = EC2BeamSection(
                b=b, h=h, cover=cover, fck=fck, fyk=fyk, fywk=fywk,
                link_dia=link_dia, bar_dia=bar_dia, comp_bar_dia=comp_bar_dia,
                section_type=geometry_meta.get("section_type", "rectangular"),
                support_condition=support_condition,
                bf=geometry_meta.get("bf"), hf=geometry_meta.get("hf"),
                delta=geometry_meta.get("delta", 1.0)
            )
            res = calculate_beam_ec2(
                section, M=M_Nmm, V=V_N, span=span, N_Ed=N_N,
                theta_deg=float(geometry_meta.get("theta_deg", 21.8))
            )
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "beam"
            res["design_code"] = "EC2"
            return res
            
        else:
            return {
                "member_id": analysis_result.get("member_id", "unknown"),
                "member_type": member_type,
                "design_code": "EC2",
                "status": "skipped",
                "reason": f"Design not implemented for member type {member_type} under EC2.",
                "reinforcement_description": "None",
                "notes": [f"Member type {member_type} design skipped."],
                "warnings": []
            }
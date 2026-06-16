"""
Module for reinforced concrete design
"""
from typing import Any, Dict, Optional


def _slab_design_udl(
    geometry_meta: Dict[str, Any],
    M_Nmm: float,
    lx: float,
    support_condition: str,
) -> float:
    """
    Factored design pressure n (N/mm²) for special-slab (ribbed/waffle/flat) design.

    Flat- and ribbed-slab routines need the factored UDL directly (they derive
    their own design moments), unlike solid slabs which can be designed from a
    governing moment. Prefer an explicit design load from ``geometry_meta``;
    otherwise back-calculate the per-metre pressure that reproduces the
    governing analysis moment for the span.
    """
    n_kpa = (
        geometry_meta.get("n_uls_kpa")
        or geometry_meta.get("design_load_kpa")
        or geometry_meta.get("w_uls_kpa")
    )
    if n_kpa is not None:
        return float(n_kpa) / 1000.0  # kN/m² → N/mm²
    coeff = 2.0 if support_condition == "cantilever" else (
        10.0 if support_condition == "continuous" else 8.0
    )
    # M_Nmm is the governing per-metre slab moment (N·mm/m); divide by the
    # 1000 mm strip width to recover a physical pressure in N/mm².
    return (coeff * abs(M_Nmm)) / (1000.0 * lx ** 2) if lx else 0.0


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
            lx = float(geometry_meta.get("lx_mm") or geometry_meta.get("lx") or span)
            ly = float(geometry_meta.get("ly_mm") or geometry_meta.get("ly") or lx)
            slab_system = str(geometry_meta.get("slab_system") or "solid").lower().strip()

            if slab_system in ("ribbed", "waffle", "flat"):
                from core.design.rc.bs8110.special_slab import (
                    calculate_special_slab_reinforcement,
                )
                try:
                    if slab_system in ("ribbed", "waffle"):
                        from models.bs8110.special_slab import RibbedWaffleSection

                        orientation = "two-way" if slab_system == "waffle" else "one-way"
                        section = RibbedWaffleSection(
                            h=h, cover=cover, fcu=fcu, lx=lx, ly=ly, fy=fy,
                            slab_type=geometry_meta.get(
                                "slab_type", "two-way" if slab_system == "waffle" else "one-way"
                            ),
                            panel_type=geometry_meta.get("panel_type") or "interior",
                            support_condition=support_condition,
                            beta_b=geometry_meta.get("beta_b", 1.0),
                            bar_dia=bar_dia,
                            rib_width=float(geometry_meta.get("rib_width") or geometry_meta.get("rib_width_mm") or 125.0),
                            rib_spacing=float(geometry_meta.get("rib_spacing") or geometry_meta.get("rib_spacing_mm") or 700.0),
                            topping_thickness=float(geometry_meta.get("topping_thickness") or geometry_meta.get("topping_thickness_mm") or 75.0),
                            slab_orientation=orientation,
                        )
                        # Per-rib actions: the rib carries load over its tributary
                        # (centre-to-centre) width. M_Nmm/V_N are per-metre slab actions.
                        trib = section.rib_spacing / 1000.0
                        res = calculate_special_slab_reinforcement(
                            section,
                            n_udl=_slab_design_udl(geometry_meta, M_Nmm, lx, support_condition),
                            M_rib=abs(M_Nmm) * trib,
                            V_rib=abs(V_N) * trib,
                            span=lx,
                        )
                    else:  # flat
                        from models.bs8110.special_slab import FlatSlabSection

                        section = FlatSlabSection(
                            h=h, cover=cover, fcu=fcu, lx=lx, ly=ly, fy=fy,
                            slab_type=geometry_meta.get("slab_type", "two-way"),
                            panel_type=geometry_meta.get("panel_type") or "interior",
                            support_condition=support_condition,
                            beta_b=geometry_meta.get("beta_b", 1.0),
                            bar_dia=bar_dia,
                            column_dia=float(geometry_meta.get("column_c") or geometry_meta.get("column_dia") or geometry_meta.get("column_c_mm") or 400.0),
                            is_circular_col=bool(geometry_meta.get("is_circular_col", False)),
                            is_drop_panel=bool(geometry_meta.get("is_drop_panel", False)),
                            drop_thickness=float(geometry_meta.get("drop_thickness") or geometry_meta.get("drop_extra_thickness") or 0.0),
                            drop_lx=float(geometry_meta.get("drop_lx") or 0.0),
                            drop_ly=float(geometry_meta.get("drop_ly") or 0.0),
                            edge_condition=str(geometry_meta.get("edge_condition") or "interior"),
                        )
                        res = calculate_special_slab_reinforcement(
                            section,
                            n_udl=_slab_design_udl(geometry_meta, M_Nmm, lx, support_condition),
                        )
                except (ValueError, TypeError) as exc:
                    res = {
                        "status": "Section Invalid",
                        "reason": str(exc),
                        "reinforcement_description": "None",
                        "notes": [f"{slab_system.capitalize()} slab geometry rejected: {exc}"],
                        "warnings": [str(exc)],
                    }
                res["member_id"] = analysis_result.get("member_id", "unknown")
                res["member_type"] = "slab"
                res["slab_system"] = slab_system
                res["design_code"] = "BS8110"
                return res

            from models.bs8110.slab import SlabSection
            from core.design.rc.bs8110.slab import calculate_slab_reinforcement

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
            res["slab_system"] = slab_system
            res["design_code"] = "BS8110"
            return res
            
        elif member_type == "footing":
            from models.bs8110.footing import PadFooting
            from core.design.rc.bs8110.footing import design_pad_footing

            critical = analysis_result.get("critical_sections", {})
            geom = critical.get("geometry", {}) if isinstance(critical, dict) else {}
            B_m = float(geom.get("B_m", 1.5))
            L_m = float(geom.get("L_m", 1.5))
            h_mm = float(geometry_meta.get("h_footing_mm", 500))
            c1 = float(geometry_meta.get("c1", 300))
            c2 = float(geometry_meta.get("c2", 300))
            section = PadFooting(
                lx=B_m * 1000, ly=L_m * 1000,
                h=h_mm,
                cover=float(geometry_meta.get("cover_mm") or geometry_meta.get("cover") or 50.0),
                fcu=float(geometry_meta.get("fcu_MPa") or geometry_meta.get("fcu") or 30.0),
                fy=float(geometry_meta.get("fy_MPa") or geometry_meta.get("fy") or 460.0),
                column_cx=c1, column_cy=c2,
                bar_dia=float(geometry_meta.get("bar_dia_mm") or geometry_meta.get("bar_dia") or 16.0),
            )
            N_uls_N = float(geometry_meta.get("N_uls", 0.0)) * 1_000
            M_uls_Nmm = float(geometry_meta.get("M_uls", 0.0)) * 1e6
            res = design_pad_footing(section, N=N_uls_N, Mx=M_uls_Nmm, My=0.0)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "footing"
            res["design_code"] = "BS8110"
            return res

        elif member_type == "wall":
            from models.bs8110.wall import WallSection
            from core.design.rc.bs8110.wall import design_reinforced_wall

            t = float(geometry_meta.get("h_wall_mm") or geometry_meta.get("thickness_mm") or b)
            l_w = float(geometry_meta.get("l_w_mm") or geometry_meta.get("l_w") or span)
            l_e = float(
                geometry_meta.get("l_e_mm") or geometry_meta.get("l_e")
                or geometry_meta.get("clear_height_mm") or span
            )
            section = WallSection(
                h=t, l_w=l_w, l_e=l_e, fcu=fcu, fy=fy, cover=cover,
                bar_dia=bar_dia, braced=bool(geometry_meta.get("braced", True)),
            )
            n_v = (N_N / l_w) if l_w else N_N
            M_per_m = M_Nmm / max(l_w / 1000.0, 1.0)
            V_h = (V_N / l_w) if (V_max and l_w) else None
            res = design_reinforced_wall(section, n_v=n_v, M=M_per_m, V_h=V_h)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "wall"
            res["design_code"] = "BS8110"
            return res

        elif member_type == "staircase":
            from models.bs8110.staircase import StaircaseSection
            from core.design.rc.bs8110.staircase import calculate_staircase_reinforcement

            stair_support = support_condition if support_condition in ("simple", "continuous") else "simple"
            section = StaircaseSection(
                waist=float(geometry_meta.get("waist_mm") or geometry_meta.get("waist") or h),
                tread=float(geometry_meta.get("tread_mm") or geometry_meta.get("tread") or 250.0),
                riser=float(geometry_meta.get("riser_mm") or geometry_meta.get("riser") or 175.0),
                num_steps=int(geometry_meta.get("num_steps") or 10),
                span=span,
                width=float(geometry_meta.get("width_mm") or geometry_meta.get("width") or 1000.0),
                cover=cover, fcu=fcu, fy=fy,
                support_condition=stair_support, bar_dia=bar_dia,
                bar_dia_dist=float(geometry_meta.get("bar_dia_dist_mm") or geometry_meta.get("bar_dia_dist") or 10.0),
                beta_b=float(geometry_meta.get("beta_b", 1.0)),
            )
            imposed = float(geometry_meta.get("imposed_load") or geometry_meta.get("qk") or 3.0)
            finishes = float(geometry_meta.get("finishes_load") or geometry_meta.get("gk_fin") or 1.5)
            res = calculate_staircase_reinforcement(section, imposed_load=imposed, finishes_load=finishes)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "staircase"
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
            
        elif member_type == "footing":
            from core.design.rc.eurocode2.footing import design_pad_footing as design_pad_footing_ec2
            from models.ec2.footing import PadFooting as EC2PadFooting

            critical = analysis_result.get("critical_sections", {})
            geom = critical.get("geometry", {}) if isinstance(critical, dict) else {}
            B_m = float(geom.get("B_m", 1.5))
            L_m = float(geom.get("L_m", 1.5))
            h_mm = float(geometry_meta.get("h_footing_mm", 500))
            c1 = float(geometry_meta.get("c1", 300))
            c2 = float(geometry_meta.get("c2", 300))
            section = EC2PadFooting(
                lx=B_m * 1000, ly=L_m * 1000,
                h=h_mm,
                cover=float(geometry_meta.get("cover_mm") or geometry_meta.get("cover") or 50.0),
                fck=float(geometry_meta.get("fck_MPa") or geometry_meta.get("fck") or 30.0),
                fyk=float(geometry_meta.get("fyk_MPa") or geometry_meta.get("fyk") or 500.0),
                column_cx=c1, column_cy=c2,
                bar_dia=float(geometry_meta.get("bar_dia_mm") or geometry_meta.get("bar_dia") or 16.0),
            )
            N_uls_N = float(geometry_meta.get("N_uls", 0.0)) * 1_000
            M_uls_Nmm = float(geometry_meta.get("M_uls", 0.0)) * 1e6
            res = design_pad_footing_ec2(section, N_Ed=N_uls_N, Mx_Ed=M_uls_Nmm, My_Ed=0.0)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "footing"
            res["design_code"] = "EC2"
            return res

        elif member_type == "column":
            from models.ec2.column import EC2ColumnSection
            from core.design.rc.eurocode2.column import calculate_column_reinforcement

            section = EC2ColumnSection(
                b=b, h=h,
                l_0x=float(geometry_meta.get("l_ex_mm") or geometry_meta.get("l_ex") or geometry_meta.get("l_0x") or span),
                l_0y=float(geometry_meta.get("l_ey_mm") or geometry_meta.get("l_ey") or geometry_meta.get("l_0y") or span),
                cover=cover, fck=fck, fyk=fyk, link_dia=link_dia, bar_dia=bar_dia,
                braced=bool(geometry_meta.get("braced", True)),
            )
            res = calculate_column_reinforcement(section, N_Ed=N_N, M_Edx=M_Nmm, M_Edy=0.0, V_Ed=V_N)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "column"
            res["design_code"] = "EC2"
            return res

        elif member_type == "slab":
            lx = float(geometry_meta.get("lx_mm") or geometry_meta.get("lx") or span)
            ly = float(geometry_meta.get("ly_mm") or geometry_meta.get("ly") or lx)
            if ly < lx:
                lx, ly = ly, lx
            slab_system = str(geometry_meta.get("slab_system") or "solid").lower().strip()

            if slab_system in ("ribbed", "waffle", "flat"):
                from core.design.rc.eurocode2.special_slab import (
                    calculate_special_slab_reinforcement,
                )
                try:
                    if slab_system in ("ribbed", "waffle"):
                        from models.ec2.slab import EC2RibbedSection

                        orientation = "two-way" if slab_system == "waffle" else "one-way"
                        section = EC2RibbedSection(
                            h=h, cover=cover, fck=fck, lx=lx, ly=ly, fyk=fyk,
                            slab_type=geometry_meta.get(
                                "slab_type", "two-way" if slab_system == "waffle" else "one-way"
                            ),
                            panel_type=geometry_meta.get("panel_type") or "CCCC",
                            support_condition=support_condition,
                            bar_dia_x=float(geometry_meta.get("bar_dia_x") or bar_dia),
                            bar_dia_y=float(geometry_meta.get("bar_dia_y") or bar_dia),
                            delta=float(geometry_meta.get("delta", geometry_meta.get("beta_b", 1.0))),
                            rib_width=float(geometry_meta.get("rib_width") or geometry_meta.get("rib_width_mm") or 120.0),
                            rib_spacing=float(geometry_meta.get("rib_spacing") or geometry_meta.get("rib_spacing_mm") or 700.0),
                            topping_thickness=float(geometry_meta.get("topping_thickness") or geometry_meta.get("topping_thickness_mm") or 80.0),
                            slab_orientation=orientation,
                        )
                        trib = section.rib_spacing / 1000.0
                        res = calculate_special_slab_reinforcement(
                            section,
                            n_udl=_slab_design_udl(geometry_meta, M_Nmm, lx, support_condition),
                            M_rib=abs(M_Nmm) * trib,
                            V_rib=abs(V_N) * trib,
                            span=lx,
                        )
                    else:  # flat
                        from models.ec2.slab import EC2FlatSlabSection

                        section = EC2FlatSlabSection(
                            h=h, cover=cover, fck=fck, lx=lx, ly=ly, fyk=fyk,
                            slab_type=geometry_meta.get("slab_type", "two-way"),
                            panel_type=geometry_meta.get("panel_type") or "CCCC",
                            support_condition=support_condition,
                            bar_dia_x=float(geometry_meta.get("bar_dia_x") or bar_dia),
                            bar_dia_y=float(geometry_meta.get("bar_dia_y") or bar_dia),
                            delta=float(geometry_meta.get("delta", geometry_meta.get("beta_b", 1.0))),
                            column_c=float(geometry_meta.get("column_c") or geometry_meta.get("column_dia") or geometry_meta.get("column_c_mm") or 400.0),
                            is_circular_col=bool(geometry_meta.get("is_circular_col", False)),
                            is_drop_panel=bool(geometry_meta.get("is_drop_panel", False)),
                            drop_thickness_extra=float(geometry_meta.get("drop_thickness_extra") or geometry_meta.get("drop_thickness") or 0.0),
                            drop_lx=float(geometry_meta.get("drop_lx") or 0.0),
                            drop_ly=float(geometry_meta.get("drop_ly") or 0.0),
                            edge_condition=str(geometry_meta.get("edge_condition") or "interior"),
                        )
                        res = calculate_special_slab_reinforcement(
                            section,
                            n_udl=_slab_design_udl(geometry_meta, M_Nmm, lx, support_condition),
                        )
                except (ValueError, TypeError) as exc:
                    res = {
                        "status": "Section Invalid",
                        "reason": str(exc),
                        "reinforcement_description": "None",
                        "notes": [f"{slab_system.capitalize()} slab geometry rejected: {exc}"],
                        "warnings": [str(exc)],
                    }
                res["member_id"] = analysis_result.get("member_id", "unknown")
                res["member_type"] = "slab"
                res["slab_system"] = slab_system
                res["design_code"] = "EC2"
                return res

            from models.ec2.slab import EC2SlabSection
            from core.design.rc.eurocode2.slab import calculate_slab_reinforcement

            section = EC2SlabSection(
                h=h, cover=cover, fck=fck, lx=lx, ly=ly, fyk=fyk,
                slab_type=geometry_meta.get("slab_type", "one-way"),
                panel_type=geometry_meta.get("panel_type"),
                support_condition=support_condition,
                bar_dia_x=float(geometry_meta.get("bar_dia_x") or bar_dia),
                bar_dia_y=float(geometry_meta.get("bar_dia_y") or bar_dia),
                delta=float(geometry_meta.get("delta", geometry_meta.get("beta_b", 1.0))),
            )
            # EC2 slab design needs a factored load intensity n (N/mm²).
            # Prefer an explicit design load from meta; otherwise back-calculate the
            # intensity that reproduces the governing analysis moment for the span.
            n_kpa = (
                geometry_meta.get("n_uls_kpa")
                or geometry_meta.get("design_load_kpa")
                or geometry_meta.get("w_uls_kpa")
            )
            if n_kpa is not None:
                n_load = float(n_kpa) / 1000.0  # kN/m² → N/mm²
            else:
                coeff = 2.0 if support_condition == "cantilever" else (
                    10.0 if support_condition == "continuous" else 8.0
                )
                n_load = (coeff * abs(M_Nmm)) / (lx ** 2) if lx else 0.0
            res = calculate_slab_reinforcement(section, n=n_load, V_Ed=V_N)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "slab"
            res["slab_system"] = slab_system
            res["design_code"] = "EC2"
            return res

        elif member_type == "wall":
            from models.ec2.wall import EC2WallSection
            from core.design.rc.eurocode2.wall import design_reinforced_wall

            t = float(geometry_meta.get("h_wall_mm") or geometry_meta.get("thickness_mm") or b)
            l_w = float(geometry_meta.get("l_w_mm") or geometry_meta.get("l_w") or span)
            l_0 = float(
                geometry_meta.get("l_0_mm") or geometry_meta.get("l_0")
                or geometry_meta.get("l_e_mm") or span
            )
            section = EC2WallSection(
                h=t, l_w=l_w, l_0=l_0, fck=fck, fyk=fyk, cover=cover,
                bar_dia=bar_dia, braced=bool(geometry_meta.get("braced", True)),
            )
            n_v = (N_N / l_w) if l_w else N_N
            M_per_m = M_Nmm / max(l_w / 1000.0, 1.0)
            V_h = (V_N / l_w) if (V_max and l_w) else None
            res = design_reinforced_wall(section, n_v=n_v, M=M_per_m, V_h=V_h)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "wall"
            res["design_code"] = "EC2"
            return res

        elif member_type == "staircase":
            from models.ec2.staircase import EC2StaircaseSection
            from core.design.rc.eurocode2.staircase import calculate_staircase_reinforcement

            stair_support = support_condition if support_condition in ("simple", "continuous", "cantilever") else "simple"
            section = EC2StaircaseSection(
                waist=float(geometry_meta.get("waist_mm") or geometry_meta.get("waist") or h),
                tread=float(geometry_meta.get("tread_mm") or geometry_meta.get("tread") or 250.0),
                riser=float(geometry_meta.get("riser_mm") or geometry_meta.get("riser") or 175.0),
                num_steps=int(geometry_meta.get("num_steps") or 10),
                span=span,
                width=float(geometry_meta.get("width_mm") or geometry_meta.get("width") or 1000.0),
                cover=cover, fck=fck, fyk=fyk, support_condition=stair_support, bar_dia=bar_dia,
                bar_dia_dist=float(geometry_meta.get("bar_dia_dist_mm") or geometry_meta.get("bar_dia_dist") or 10.0),
                delta=float(geometry_meta.get("delta", geometry_meta.get("beta_b", 1.0))),
            )
            imposed = float(geometry_meta.get("imposed_load") or geometry_meta.get("qk") or 3.0)
            finishes = float(geometry_meta.get("finishes_load") or geometry_meta.get("gk_fin") or 1.5)
            res = calculate_staircase_reinforcement(section, imposed_load=imposed, finishes_load=finishes)
            res["member_id"] = analysis_result.get("member_id", "unknown")
            res["member_type"] = "staircase"
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
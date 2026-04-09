from typing import Dict, Any, List, Optional
from models.loading.schema import DesignCode, LimitState, OccupancyCategory, SlabType, PunchingShearData
from services.loading.tables import OccupancyLoadTable, MaterialWeightTable
from services.loading.load_combinations import LoadCombinationEngine

class RibbedSlabAssembler:
    """Assembles loads for ribbed slabs (one-way)."""

    @staticmethod
    def calculate_self_weight(
        topping_thickness_mm: float,
        rib_width_mm: float,
        rib_depth_below_topping_mm: float,
        rib_spacing_mm: float,
        filler_weight_kn_m2: float = 0.0
    ) -> float:
        """
        Self-weight = [Topping thickness * 25] + [Rib volume per m width / Rib spacing]
        """
        gamma = MaterialWeightTable.get_rc_weight()
        
        # Topping weight (kN/m2)
        topping_weight = (topping_thickness_mm / 1000.0) * gamma
        
        # Rib weight per meter width (kN/m2)
        rib_area_m2 = (rib_width_mm / 1000.0) * (rib_depth_below_topping_mm / 1000.0)
        num_ribs_per_m = 1000.0 / rib_spacing_mm
        rib_weight = rib_area_m2 * num_ribs_per_m * gamma
        
        return topping_weight + rib_weight + filler_weight_kn_m2

    @staticmethod
    def assemble_ribbed_slab_load(
        topping_thickness_mm: float,
        rib_width_mm: float,
        rib_depth_below_topping_mm: float,
        rib_spacing_mm: float,
        filler_weight_kn_m2: float,
        screed_load: float,
        finishes_load: float,
        services_load: float,
        occupancy: OccupancyCategory,
        custom_qk: float,
        code: DesignCode
    ) -> Dict[str, float]:
        sw = RibbedSlabAssembler.calculate_self_weight(
            topping_thickness_mm, rib_width_mm, rib_depth_below_topping_mm, rib_spacing_mm, filler_weight_kn_m2
        )
        
        gk = sw + screed_load + finishes_load + services_load
        
        if occupancy == OccupancyCategory.CUSTOM:
            qk = custom_qk
        else:
            qk = OccupancyLoadTable.get_load(occupancy, code)
        
        uls_load = LoadCombinationEngine.factor_loads(gk, qk, 0, code, LimitState.ULS_DOMINANT)
        
        return {
            "gk": round(gk, 2),
            "qk": round(qk, 2),
            "uls_load": round(uls_load, 2),
            "self_weight": round(sw, 2),
            "classification": "one-way" # Enforced
        }

class WaffleSlabAssembler:
    """Assembles loads for waffle slabs (two-way ribbed)."""

    @staticmethod
    def calculate_field_self_weight(
        topping_thickness_mm: float,
        rib_width_mm: float,
        rib_depth_below_topping_mm: float,
        rib_spacing_x_mm: float,
        rib_spacing_y_mm: float
    ) -> float:
        """
        Self-weight per m² for the ribbed field area with junction correction.
        """
        gamma = MaterialWeightTable.get_rc_weight()
        topping_weight = (topping_thickness_mm / 1000.0) * gamma
        
        vol_x = (rib_width_mm / 1000.0) * (rib_depth_below_topping_mm / 1000.0) * (1000.0 / rib_spacing_y_mm)
        vol_y = (rib_width_mm / 1000.0) * (rib_depth_below_topping_mm / 1000.0) * (1000.0 / rib_spacing_x_mm)
        
        # Junction correction: subtract the overlap volume counted twice
        junction_area_m2 = (rib_width_mm / 1000.0) * (rib_width_mm / 1000.0)
        num_junctions_per_m2 = (1000.0 / rib_spacing_x_mm) * (1000.0 / rib_spacing_y_mm)
        vol_junction_correction = junction_area_m2 * (rib_depth_below_topping_mm / 1000.0) * num_junctions_per_m2
        
        total_vol_ribs_per_m2 = vol_x + vol_y - vol_junction_correction
        
        return topping_weight + (total_vol_ribs_per_m2 * gamma)

    @staticmethod
    def assemble_waffle_slab_load(
        topping_thickness_mm: float,
        rib_width_mm: float,
        rib_depth_below_topping_mm: float,
        rib_spacing_x_mm: float,
        rib_spacing_y_mm: float,
        solid_band_width_m: float,
        screed_load: float,
        finishes_load: float,
        services_load: float,
        occupancy: OccupancyCategory,
        custom_qk: float,
        code: DesignCode
    ) -> Dict[str, Any]:
        """
        Assembles loads for waffle slab, distinguishes between field and solid band zones.
        """
        sw_field = WaffleSlabAssembler.calculate_field_self_weight(
            topping_thickness_mm, rib_width_mm, rib_depth_below_topping_mm, rib_spacing_x_mm, rib_spacing_y_mm
        )
        
        # Solid band self-weight
        total_depth_mm = topping_thickness_mm + rib_depth_below_topping_mm
        sw_solid = (total_depth_mm / 1000.0) * MaterialWeightTable.get_rc_weight()
        
        if occupancy == OccupancyCategory.CUSTOM:
            qk = custom_qk
        else:
            qk = OccupancyLoadTable.get_load(occupancy, code)
            
        common_dead = screed_load + finishes_load + services_load
        
        gk_field = sw_field + common_dead
        gk_solid = sw_solid + common_dead
        
        uls_field = LoadCombinationEngine.factor_loads(gk_field, qk, 0, code, LimitState.ULS_DOMINANT)
        uls_solid = LoadCombinationEngine.factor_loads(gk_solid, qk, 0, code, LimitState.ULS_DOMINANT)
        
        return {
            "field_zone": {
                "gk": round(gk_field, 2),
                "qk": round(qk, 2),
                "uls_load": round(uls_field, 2),
                "sw": round(sw_field, 2)
            },
            "solid_band_zone": {
                "gk": round(gk_solid, 2),
                "qk": round(qk, 2),
                "uls_load": round(uls_solid, 2),
                "sw": round(sw_solid, 2),
                "width_m": solid_band_width_m
            },
            "classification": "two-way"
        }

class FlatSlabAssembler:
    """Assembles loads for flat slabs."""

    @staticmethod
    def assemble_flat_slab_load(
        thickness_mm: float,
        drop_panel_thickness_mm: Optional[float],
        drop_panel_width_m: Optional[float],
        column_head_dim_m: Optional[float],
        screed_load: float,
        finishes_load: float,
        services_load: float,
        occupancy: OccupancyCategory,
        custom_qk: float,
        lx_m: float,
        ly_m: float,
        code: DesignCode,
        patch_loads: List[Dict[str, float]] = [] # [{value: kn_m2, x_range: (start, end), y_range: (start, end)}]
    ) -> Dict[str, Any]:
        """
        Assembles loads for flat slab and prepares strip distributions.
        """
        sw_main = (thickness_mm / 1000.0) * MaterialWeightTable.get_rc_weight()
        
        common_dead = screed_load + finishes_load + services_load
        gk_main = sw_main + common_dead
        
        if occupancy == OccupancyCategory.CUSTOM:
            qk = custom_qk
        else:
            qk = OccupancyLoadTable.get_load(occupancy, code)
            
        # Drop panel handling
        sw_drop = 0.0
        if drop_panel_thickness_mm:
            sw_drop = (drop_panel_thickness_mm / 1000.0) * MaterialWeightTable.get_rc_weight()
            
        uls_main = LoadCombinationEngine.factor_loads(gk_main, qk, 0, code, LimitState.ULS_DOMINANT)
        
        # Strip distribution (Simple implementation of Column/Middle Strip split)
        # BS 8110 / EC2 principles
        col_strip_percent = 0.75 if code == DesignCode.BS8110 else 0.60
        mid_strip_percent = 1.0 - col_strip_percent
        
        # Punching Shear Flagging: u0 perimeter
        u0 = 0.0
        if column_head_dim_m:
            u0 = 4 * column_head_dim_m
        else:
            # Assume nominal column size for u0 if not provided, or flag for input
            u0 = -1.0 

        return {
            "main_zone": {
                "gk": round(gk_main, 2),
                "qk": round(qk, 2),
                "uls_load": round(uls_main, 2)
            },
            "drop_panel": {
                "extra_gk": round(sw_drop, 2),
                "width_m": drop_panel_width_m
            },
            "strip_distribution": {
                "column_strip_factor": col_strip_percent,
                "middle_strip_factor": mid_strip_percent
            },
            "punching_shear_u0": u0,
            "patch_loads": patch_loads
        }

class SlabLoadRouter:
    """Routes slab loading assembly to the specialized sub-module."""

    @staticmethod
    def assemble(slab_type: SlabType, **kwargs) -> Dict[str, Any]:
        if slab_type == SlabType.SOLID:
            from services.loading.assemblers import SlabLoadAssembler
            return SlabLoadAssembler.assemble_slab_load(**kwargs)
        elif slab_type == SlabType.RIBBED:
            return RibbedSlabAssembler.assemble_ribbed_slab_load(**kwargs)
        elif slab_type == SlabType.WAFFLE:
            return WaffleSlabAssembler.assemble_waffle_slab_load(**kwargs)
        elif slab_type == SlabType.FLAT:
            return FlatSlabAssembler.assemble_flat_slab_load(**kwargs)
        else:
            raise ValueError(f"Unsupported slab type: {slab_type}")

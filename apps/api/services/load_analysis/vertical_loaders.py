from typing import Dict, List, Any, Optional
from models.loading.schema import DesignCode, LimitState
from services.loading.tables import MaterialWeightTable
from services.loading.load_combinations import LoadCombinationEngine

class ColumnLoadAssembler:
    """Assembles and accumulates loads for columns."""

    @staticmethod
    def calculate_self_weight(
        width_mm: float,
        depth_mm: float,
        height_m: float
    ) -> float:
        """Returns the self-weight (Gk) of the column per storey."""
        area_m2 = (width_mm / 1000.0) * (depth_mm / 1000.0)
        return area_m2 * height_m * MaterialWeightTable.get_rc_weight()

    @staticmethod
    def get_load_reduction_factor(num_floors: int) -> float:
        """
        BS 6399 / EC1 reduction factor for imposed loads on columns.
        (Simplified implementation - could be expanded based on specific code clauses)
        """
        if num_floors <= 1:
            return 1.0
        elif num_floors == 2:
            return 0.9
        elif num_floors == 3:
            return 0.8
        elif num_floors == 4:
            return 0.7
        elif num_floors == 5:
            return 0.6
        else:
            return 0.5 # Max reduction typically capped at 50%

    @staticmethod
    def accumulate_column_loads(
        incoming_gk: float, # Sum of beam reactions Gk + flat slab Gk
        incoming_qk: float, # Sum of beam reactions Qk + flat slab Qk
        num_floors_supported: int,
        self_weight_gk: float,
        code: DesignCode,
        is_flat_slab: bool = False
    ) -> Dict[str, float]:
        """
        Accumulates total column design loads.
        If is_flat_slab is True, incoming_gk/qk are assumed to be direct slab reactions.
        """
        reduction = ColumnLoadAssembler.get_load_reduction_factor(num_floors_supported)
        
        total_gk = incoming_gk + self_weight_gk
        reduced_qk = incoming_qk * reduction
        
        uls_load = LoadCombinationEngine.factor_loads(
            total_gk, reduced_qk, 0, code, LimitState.ULS_DOMINANT
        )

        return {
            "total_gk": round(total_gk, 2),
            "reduced_qk": round(reduced_qk, 2),
            "uls_axial_load": round(uls_load, 2),
            "reduction_factor": reduction,
            "load_path": "direct_from_slab" if is_flat_slab else "via_beams"
        }


class WallLoadAssembler:
    """Assembles loads for loadbearing walls."""

    @staticmethod
    def calculate_self_weight(
        thickness_mm: float,
        height_m: float,
        length_m: float = 1.0 # Calculated per meter run
    ) -> float:
        """Returns the self-weight (Gk) of the wall per meter run per storey."""
        vol_m3 = (thickness_mm / 1000.0) * height_m * length_m
        return vol_m3 * MaterialWeightTable.get_rc_weight()

    @staticmethod
    def assemble_wall_load(
        incoming_gk_m: float,
        incoming_qk_m: float,
        thickness_mm: float,
        height_m: float,
        code: DesignCode,
        eccentricity_mm: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Assemble the total design line load (kN/m) for a loadbearing wall.
        """
        self_weight = WallLoadAssembler.calculate_self_weight(thickness_mm, height_m)
        
        total_gk_m = incoming_gk_m + self_weight
        total_qk_m = incoming_qk_m
        
        uls_load_m = LoadCombinationEngine.factor_loads(
            total_gk_m, total_qk_m, 0, code, LimitState.ULS_DOMINANT
        )
        
        # Nominal moment due to eccentric loading
        nominal_moment_uls = 0.0
        if eccentricity_mm:
            e_m = eccentricity_mm / 1000.0
            nominal_moment_uls = uls_load_m * e_m

        return {
            "total_gk_m": round(total_gk_m, 2),
            "total_qk_m": round(total_qk_m, 2),
            "uls_axial_load_m": round(uls_load_m, 2),
            "eccentric_moment_uls": round(nominal_moment_uls, 2)
        }


class FootingLoadAssembler:
    """Assembles terminal loads for footing design."""

    @staticmethod
    def calculate_self_weight(
        length_m: float,
        width_m: float,
        thickness_m: float
    ) -> float:
        return length_m * width_m * thickness_m * MaterialWeightTable.get_rc_weight()

    @staticmethod
    def assemble_footing_load(
        column_axial_gk: float,
        column_axial_qk: float,
        column_mx_gk: float,
        column_mx_qk: float,
        column_my_gk: float,
        column_my_qk: float,
        footing_length_m: float,
        footing_width_m: float,
        footing_thickness_m: float,
        soil_surcharge_gk: float, # Backfill soil load on footing
        code: DesignCode
    ) -> Dict[str, float]:
        """
        Terminal accumulator for footing design.
        """
        self_weight_gk = FootingLoadAssembler.calculate_self_weight(
            footing_length_m, footing_width_m, footing_thickness_m
        )

        total_gk = column_axial_gk + self_weight_gk + soil_surcharge_gk
        total_qk = column_axial_qk
        
        uls_axial = LoadCombinationEngine.factor_loads(total_gk, total_qk, 0, code, LimitState.ULS_DOMINANT)
        sls_axial = LoadCombinationEngine.factor_loads(total_gk, total_qk, 0, code, LimitState.SLS_CHARACTERISTIC)

        # Factored Moments
        uls_mx = LoadCombinationEngine.factor_loads(column_mx_gk, column_mx_qk, 0, code, LimitState.ULS_DOMINANT)
        uls_my = LoadCombinationEngine.factor_loads(column_my_gk, column_my_qk, 0, code, LimitState.ULS_DOMINANT)
        
        sls_mx = LoadCombinationEngine.factor_loads(column_mx_gk, column_mx_qk, 0, code, LimitState.SLS_CHARACTERISTIC)
        sls_my = LoadCombinationEngine.factor_loads(column_my_gk, column_my_qk, 0, code, LimitState.SLS_CHARACTERISTIC)

        return {
            "total_gk": round(total_gk, 2),
            "total_qk": round(total_qk, 2),
            "uls_axial": round(uls_axial, 2),
            "sls_axial": round(sls_axial, 2), # Used for bearing pressure check
            "uls_mx": round(uls_mx, 2),
            "uls_my": round(uls_my, 2),
            "sls_mx": round(sls_mx, 2),
            "sls_my": round(sls_my, 2)
        }

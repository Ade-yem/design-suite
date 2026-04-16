from typing import Dict
from models.loading.schema import DesignCode, LimitState, OccupancyCategory
from services.loading.tables import MaterialWeightTable, OccupancyLoadTable
from services.loading.load_combinations import LoadCombinationEngine

class StaircaseLoadAssembler:
    """Assembles loads for staircases."""

    @staticmethod
    def calculate_self_weight(
        going_mm: float,
        riser_mm: float,
        waist_thickness_mm: float
    ) -> float:
        """
        Calculates equivalent horizontal self-weight (Gk) per m² of staircase flight.
        Uses the geometric properties to find equivalent thickness.
        """
        # Inclination factor: slope length / horizontal length
        import math
        slope_factor = math.sqrt(going_mm**2 + riser_mm**2) / going_mm
        
        # Equivalent thickness = waist / cos(theta) + riser / 2
        waist_eq_m = (waist_thickness_mm / 1000.0) * slope_factor
        steps_eq_m = (riser_mm / 1000.0) / 2.0
        
        total_eq_thickness = waist_eq_m + steps_eq_m
        
        return total_eq_thickness * MaterialWeightTable.get_rc_weight()

    @staticmethod
    def assemble_staircase_load(
        going_mm: float,
        riser_mm: float,
        waist_thickness_mm: float,
        finishes_gk: float,
        code: DesignCode
    ) -> Dict[str, float]:
        """
        Assembles area loads for a staircase flight.
        Imposed load is defaulted to OccupancyCategory.STAIRS (3.0 kN/m²).
        """
        self_weight_gk = StaircaseLoadAssembler.calculate_self_weight(
            going_mm, riser_mm, waist_thickness_mm
        )
        
        gk = self_weight_gk + finishes_gk
        qk = OccupancyLoadTable.get_load(OccupancyCategory.STAIRS, code)

        uls_load = LoadCombinationEngine.factor_loads(
            gk, qk, 0, code, LimitState.ULS_DOMINANT
        )

        return {
            "gk": round(gk, 2),
            "qk": round(qk, 2),
            "uls_load": round(uls_load, 2)
        }

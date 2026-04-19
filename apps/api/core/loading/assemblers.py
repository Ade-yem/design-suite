from typing import Dict, Any, List
from models.loading.schema import DesignCode, LimitState, OccupancyCategory
from core.loading.tables import OccupancyLoadTable, MaterialWeightTable
from core.loading.load_combinations import LoadCombinationEngine

class SlabLoadAssembler:
    """Assembles area loads for a slab panel."""

    @staticmethod
    def classify_slab(ly: float, lx: float) -> str:
        """
        Classify as 'one-way' or 'two-way' based on span ratio.
        lx = short span, ly = long span
        """
        if lx <= 0:
            raise ValueError("Short span lx must be > 0")
        ratio = ly / lx
        return "one-way" if ratio >= 2.0 else "two-way"

    @staticmethod
    def assemble_slab_load(
        thickness_mm: float,
        screed_load: float,
        finishes_load: float,
        services_load: float,
        occupancy: OccupancyCategory,
        custom_qk: float,
        code: DesignCode
    ) -> Dict[str, float]:
        """
        Assemble the characteristic and ultimate design area loads (kN/m²) for a slab.
        """
        # Self-weight
        thickness_m = thickness_mm / 1000.0
        self_weight = thickness_m * MaterialWeightTable.get_rc_weight()

        # Total Dead Load (Gk)
        gk = self_weight + screed_load + finishes_load + services_load

        # Total Imposed Load (Qk)
        if occupancy == OccupancyCategory.CUSTOM:
            qk = custom_qk
        else:
            qk = OccupancyLoadTable.get_load(occupancy, code)

        # Factored Design Load (ULS)
        uls_load = LoadCombinationEngine.factor_loads(gk, qk, 0, code, LimitState.ULS_DOMINANT)

        return {
            "gk": round(gk, 2),
            "qk": round(qk, 2),
            "uls_load": round(uls_load, 2)
        }

class BeamLoadAssembler:
    """Assembles loads on a beam spanning from slabs, walls, etc."""

    @staticmethod
    def equivalent_udl_from_slab(
        slab_gk_area: float,
        slab_qk_area: float,
        lx: float,
        ly: float,
        is_short_span_beam: bool
    ) -> Dict[str, float]:
        """
        Convert two-way or one-way slab loads into equivalent UDLs for beam design.
        Using standard yield line principles to get equivalent UDL.
        """
        classification = SlabLoadAssembler.classify_slab(ly, lx)

        if classification == "one-way":
            # Load goes purely to long beams (spanning over lx)
            # Short span lx/2 area
            if is_short_span_beam:
                # Typically carries minimal or no load
                eq_qk = 0.0
                eq_gk = 0.0
            else:
                eq_gk = slab_gk_area * (lx / 2)
                eq_qk = slab_qk_area * (lx / 2)
        else:
            # Two-way distribution
            if is_short_span_beam:
                # Triangular load equivalent UDL = Area load * lx / 3
                eq_gk = slab_gk_area * (lx / 3)
                eq_qk = slab_qk_area * (lx / 3)
            else:
                # Trapezoidal load equivalent UDL 
                # Factor = (1 - 1 / (3 * (ly/lx)^2)) * (lx/2)
                beta = ly / lx
                factor = (1 - 1 / (3 * (beta ** 2))) * (lx / 2) if beta > 0 else 0
                eq_gk = slab_gk_area * factor
                eq_qk = slab_qk_area * factor

        return {
            "equivalent_gk_m": round(eq_gk, 2),
            "equivalent_qk_m": round(eq_qk, 2)
        }

    @staticmethod
    def assemble_beam_load(
        width_mm: float,
        depth_mm: float, # overall depth
        slab_eq_gk: float,
        slab_eq_qk: float,
        wall_line_load_gk: float,
        point_loads: List[Dict[str, float]], # List of dicts with 'gk', 'qk', 'pos'
        code: DesignCode
    ) -> Dict[str, Any]:
        """
        Assemble the final beam loads per span length.
        """
        # Beam Self weight
        area_m2 = (width_mm / 1000.0) * (depth_mm / 1000.0)
        self_weight_gk = area_m2 * MaterialWeightTable.get_rc_weight()

        total_gk_m = self_weight_gk + slab_eq_gk + wall_line_load_gk
        total_qk_m = slab_eq_qk
        
        uls_udl = LoadCombinationEngine.factor_loads(total_gk_m, total_qk_m, 0, code, LimitState.ULS_DOMINANT)

        # Process point loads
        factored_point_loads = []
        for pl in point_loads:
            uls_pl = LoadCombinationEngine.factor_loads(pl.get('gk', 0), pl.get('qk', 0), 0, code, LimitState.ULS_DOMINANT)
            factored_point_loads.append({
                "gk": pl.get('gk', 0),
                "qk": pl.get('qk', 0),
                "uls_load": round(uls_pl, 2),
                "position": pl.get('pos', 0)
            })

        return {
            "total_gk_m": round(total_gk_m, 2),
            "total_qk_m": round(total_qk_m, 2),
            "uls_udl": round(uls_udl, 2),
            "point_loads": factored_point_loads
        }

from typing import Tuple, Dict, Any
from models.loading.schema import DesignCode, LimitState

class LoadCombinationEngine:
    """Engine for generating factored loads based on limit states and design codes."""

    @staticmethod
    def get_factors(code: DesignCode, limit_state: LimitState) -> Tuple[float, float, float]:
        """
        Returns load factors (gamma_G, gamma_Q, gamma_W) for Gk, Qk, Wk respectively.
        """
        if code == DesignCode.BS8110:
            return LoadCombinationEngine._bs8110_factors(limit_state)
        elif code == DesignCode.EC2:
            return LoadCombinationEngine._ec2_factors(limit_state)
        
        raise ValueError(f"Unsupported design code: {code}")

    @staticmethod
    def _bs8110_factors(limit_state: LimitState) -> Tuple[float, float, float]:
        """Load factors for BS 8110."""
        if limit_state == LimitState.ULS_DOMINANT:
            return (1.4, 1.6, 0.0)
        elif limit_state == LimitState.ULS_WIND:
            return (1.2, 1.2, 1.2)
        elif limit_state == LimitState.SLS_CHARACTERISTIC:
            return (1.0, 1.0, 0.0)
        
        # Default fallback for unhandled / non-applicable SLS states for BS 8110
        return (1.0, 1.0, 0.0)

    @staticmethod
    def _ec2_factors(limit_state: LimitState) -> Tuple[float, float, float]:
        """Load factors for EC2 (EN 1990)."""
        if limit_state == LimitState.ULS_DOMINANT:
            return (1.35, 1.5, 0.0)
        elif limit_state == LimitState.ULS_WIND:
            return (1.35, 1.5, 0.9)  # 1.5 * 0.6 wind combination factor
        elif limit_state == LimitState.SLS_CHARACTERISTIC:
            return (1.0, 1.0, 0.0)
        elif limit_state == LimitState.SLS_QUASI_PERMANENT:
            return (1.0, 0.3, 0.0)
        elif limit_state == LimitState.SLS_FREQUENT:
            return (1.0, 0.5, 0.0)
        
        return (1.0, 1.0, 0.0)

    @staticmethod
    def factor_loads(gk: float, qk: float, wk: float, code: DesignCode, limit_state: LimitState) -> float:
        """Apply gamma factors to characteristic loads to get ultimate/serviceability loads."""
        gamma_G, gamma_Q, gamma_W = LoadCombinationEngine.get_factors(code, limit_state)
        return gamma_G * gk + gamma_Q * qk + gamma_W * wk

    @staticmethod
    def generate_pattern_loads(gk: float, qk: float, code: DesignCode) -> Dict[str, Any]:
        """
        Generate pattern loading scenarios for continuous members.
        Returns the ULS factored loads for different arrangements.
        For spans fully loaded: gamma_G*gk + gamma_Q*qk
        For spans min loaded (adjacent unloaded): 1.0*gk (BS8110/EC2 min dead load factor)
        """
        ulS_limit = LimitState.ULS_DOMINANT
        gamma_G_max, gamma_Q_max, _ = LoadCombinationEngine.get_factors(code, ulS_limit)
        
        # Minimum dead load factor for unloaded alternate spans
        gamma_G_min = 1.0 
        
        max_load = gamma_G_max * gk + gamma_Q_max * qk
        min_load = gamma_G_min * gk
        
        return {
            "max_load": max_load,
            "min_load": min_load,
            "arrangements": [
                {"name": "All spans fully loaded", "description": "Max midspan sagging"},
                {"name": "Alternate spans loaded", "description": "Max support hogging"},
                {"name": "Adjacent spans loaded", "description": "Max shear at supports"}
            ],
            "factors_used": {
                "gamma_G_max": gamma_G_max,
                "gamma_Q_max": gamma_Q_max,
                "gamma_G_min": gamma_G_min
            }
        }

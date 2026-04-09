from models.loading.schema import OccupancyCategory, DesignCode

class OccupancyLoadTable:
    """Table for characteristic imposed loads (Qk) based on occupancy."""
    
    # Values mapped to (BS 6399, EC1) in kN/m²
    _table = {
        OccupancyCategory.RESIDENTIAL: {"BS8110": 1.5, "EC2": 2.0},
        OccupancyCategory.OFFICE: {"BS8110": 2.5, "EC2": 3.0},
        OccupancyCategory.RETAIL: {"BS8110": 4.0, "EC2": 4.0},
        OccupancyCategory.ROOF_ACCESSIBLE: {"BS8110": 1.5, "EC2": 1.0},
        OccupancyCategory.ROOF_NON_ACCESSIBLE: {"BS8110": 0.6, "EC2": 0.4},
        OccupancyCategory.STAIRS: {"BS8110": 3.0, "EC2": 3.0},
    }

    @classmethod
    def get_load(cls, occupancy: OccupancyCategory, code: DesignCode) -> float:
        """
        Get the characteristic imposed load (Qk) for a given occupancy and design code.
        """
        if occupancy == OccupancyCategory.CUSTOM:
            raise ValueError("Custom occupancy requires a manually provided load value")
        
        return cls._table[occupancy][code.value]

class MaterialWeightTable:
    """Standard material unit weights."""
    
    REINFORCED_CONCRETE = 25.0 # kN/m³
    PLAIN_CONCRETE = 24.0      # kN/m³
    SOIL = 18.0                # kN/m³ (approximate)
    STEEL = 78.5               # kN/m³

    @classmethod
    def get_rc_weight(cls) -> float:
        return cls.REINFORCED_CONCRETE

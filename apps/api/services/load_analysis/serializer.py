from typing import Dict, Any, List
from models.loading.schema import MemberLoadOutput, DesignCode, SpanLoads

class LoadSerializer:
    """Serializes the load assembly output into a schema valid format."""

    @staticmethod
    def serialize_member(
        member_id: str,
        member_type: str,
        design_code: DesignCode,
        spans_data: List[Dict[str, Any]],
        combination_used: str,
        source_slabs: List[str] = [],
        punching_shear_checks: List[Dict[str, Any]] = [],
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Serializes member loads into the standard JSON schema.
        `spans_data` should be a list of dictionaries, each containing:
        - span_id
        - length_m
        - loads: Dict (e.g. {'udl_dead_gk': 18.5, 'point_loads': []})
        - pattern_loading_flag (optional, default False)
        """
        spans = []
        for span_raw in spans_data:
            span = SpanLoads(
                span_id=span_raw['span_id'],
                length_m=span_raw['length_m'],
                loads=span_raw['loads'],
                pattern_loading_flag=span_raw.get('pattern_loading_flag', False)
            )
            spans.append(span)

        output = MemberLoadOutput(
            member_id=member_id,
            member_type=member_type,
            design_code=design_code,
            spans=spans,
            combination_used=combination_used,
            source_slabs=source_slabs,
            punching_shear_checks=punching_shear_checks,
            notes=notes
        )

        # Return standardized dictionary representations, suitable for JSON
        return output.model_dump()

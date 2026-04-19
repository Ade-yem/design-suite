import pytest

class TestFullPipelineBS8110:
    """
    Reference case: 3-span continuous RC beam to BS 8110
    Spans: 6.0m, 5.5m, 6.0m
    Loading: Gk = 25 kN/m, Qk = 15 kN/m
    Section: 300 × 550mm, fcu = 30 MPa, fy = 460 MPa
    Hand-calculated results used as benchmark.
    """

    HAND_CALC_BENCHMARK = {
        "B-01": {
            "M_midspan_end_span_kNm": 148.2,
            "M_support_first_kNm": -164.7,
            "V_max_kN": 193.5,
            "As_midspan_mm2": 956,
            "As_support_mm2": 1087
        }
    }

    @pytest.mark.skip(reason="Requires full E2E setup with mocks or live integration")
    async def test_complete_pipeline_produces_correct_design(
        self, async_client
    ):
        # Step 1 — Create project
        pass

    @pytest.mark.skip(reason="Needs report generation backend running")
    async def test_report_generated_and_downloadable(self, async_client):
        """
        After full pipeline, a PDF report must be generated and
        downloadable with status 200 and correct content-type.
        """
        pass

    @pytest.mark.skip(reason="Needs full E2E setup")
    async def test_pipeline_rejects_out_of_order_stage(self, async_client):
        """
        Attempting to generate a report before drawings are confirmed
        must fail with 403 at any point in the pipeline.
        """
        pass


class TestFullPipelineEC2:
    """
    Same structural case as BS8110 test but designed to EC2.
    Results will differ due to different partial factors and
    design equations — both must pass independently.
    """

    EC2_BENCHMARK = {
        "B-01": {
            "M_midspan_end_span_kNm": 145.1,  # Slightly different due to 1.35Gk
            "As_midspan_mm2": 932
        }
    }

    @pytest.mark.skip(reason="Needs EC2 specific module integration")
    async def test_ec2_combination_factors_applied_correctly(
        self, async_client
    ):
        pass

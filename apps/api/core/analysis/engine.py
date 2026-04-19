from typing import List, Dict, Any, Literal
import uuid
from models.loading.schema import MemberLoadOutput, DesignCode
from models.analysis.schema import AnalysisOutputSchema, MemberAnalysisResult, StressResultants
from .beam_solver import SimplySupportedBeamSolver, MomentCoefficientSolver
from .column_solver import ColumnSolver
from .slab_solver import TwoWaySlabSolver, FlatSlabSolver, RibbedSlabSolver, WaffleSlabSolver
from .footing_solver import PadFootingSolver, CombinedFootingSolver, StripFootingSolver
from .staircase_solver import StaircaseSolver
from .wall_solver import WallSolver

class AnalysisEngine:
    """
    Structural Analysis Engine Orchestrator.
    Routes loaded member geometry to the correct solver module and packages results.
    """
    def __init__(self, design_code: Literal["BS8110", "EC2"] = "EC2"):
        self.design_code = design_code
        self.results: List[MemberAnalysisResult] = []

    def analyze_member(self, load_data: MemberLoadOutput, geometry_meta: Dict[str, Any]) -> MemberAnalysisResult:
        """
        Routes a member to its specific solver based on type and geometry.
        """
        m_type = load_data.member_type
        m_id = load_data.member_id
        
        if m_type == "beam":
            return self._route_beam(load_data, geometry_meta)
        elif m_type == "slab":
            return self._route_slab(load_data, geometry_meta)
        elif m_type == "column":
            return self._route_column(load_data, geometry_meta)
        elif m_type == "wall":
            return self._route_wall(load_data, geometry_meta)
        elif m_type == "footing":
            return self._route_footing(load_data, geometry_meta)
        elif m_type == "staircase":
            return self._route_staircase(load_data, geometry_meta)
        else:
            raise ValueError(f"Unknown member type: {m_type}")

    def _route_beam(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        num_spans = len(load_data.spans)
        
        if num_spans == 1:
            span = load_data.spans[0]
            # meta should contain E, I
            solver = SimplySupportedBeamSolver(
                member_id=load_data.member_id,
                span_L=span.length_m,
                E=meta.get("E", 30e6), # Default 30GPa
                I=meta.get("I", 0.001), # Default
                design_code=self.design_code
            )
            # Apply loads from span.loads
            # Simplified: assuming 'n_uls' is provided in loads for now
            n_uls = span.loads.get("n_uls", 0.0)
            if isinstance(n_uls, (int, float)):
                solver.add_udl(n_uls)
            
            return solver.solve()
        else:
            # Check if regular for coefficient method
            # For now, fallback to Coefficient Solver for multi-span
            spans_list = [s.length_m for s in load_data.spans]
            solver = MomentCoefficientSolver(
                member_id=load_data.member_id,
                spans=spans_list,
                design_code=self.design_code
            )
            # Use max n_uls across spans for simple coefficient method
            n_max = max([s.loads.get("n_uls", 0.0) for s in load_data.spans])
            return solver.solve(n_max)

    def _route_slab(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        s_type = meta.get("slab_type", "solid")
        
        if s_type == "flat":
            # For flat slab, normally we'd do Equivalent Frame or Punching check
            # For now, do poking check as per requested focus
            solver = FlatSlabSolver(
                column_id=load_data.member_id, # Simplified mapping
                col_width=meta.get("c1", 300),
                col_depth=meta.get("c2", 300),
                slab_depth=meta.get("h", 250),
                cover=meta.get("cover", 25)
            )
            # The solve method in my slab_solver for FlatSlab was named check_punching_shear
            # and returns a Dict, not MemberAnalysisResult in the previous implementation?
            # Actually, I should probably standardize it to return MemberAnalysisResult.
            # For now, let's wrap it.
            # Wait, looking at slab_solver implementation:
            # check_punching_shear returns a Dict containing 'punching_shear' info.
            
            # Re-routing logic for flat slab as a member result
            V_Ed = meta.get("V_Ed", 0.0)
            analysis_dict = solver.check_punching_shear(V_Ed, self.design_code)
            
            return MemberAnalysisResult(
                member_id=load_data.member_id,
                member_type="slab",
                analysis_method="closed_form",
                stress_resultants=StressResultants(V_max_kN=V_Ed),
                calculation_trace=solver.trace,
                flags=[analysis_dict["punching_shear"]["flag"]]
            )
        
        elif s_type == "ribbed":
            # Ribbed solver
            solver = RibbedSlabSolver(
                panel_id=load_data.member_id,
                L=meta.get("L", 5.0),
                rib_spacing=meta.get("s", 600),
                rib_width=meta.get("bw", 150),
                topping_h=meta.get("hf", 50),
                total_h=meta.get("h", 300)
            )
            n_uls = meta.get("n_uls", 10.0)
            return solver.solve(n_uls)
            
        else: # Default TwoWay or Waffle for Ly/Lx check
            Lx = meta.get("Lx", 4.0)
            Ly = meta.get("Ly", 5.0)
            if Ly / Lx >= 2.0: # One-Way slab
                # Treated as unit-width beam
                meta["I"] = (1.0 * (meta.get("h", 0.2)**3)) / 12.0
                return self._route_beam(load_data, meta)
            else:
                solver = TwoWaySlabSolver(
                    panel_id=load_data.member_id,
                    Lx=Lx,
                    Ly=Ly,
                    edge_conditions=meta.get("edge_conditions", ["C","C","C","C"])
                )
                n_uls = meta.get("n_uls", 10.0)
                return solver.solve(n_uls)

    def _route_column(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        solver = ColumnSolver(
            member_id=load_data.member_id,
            h=meta.get("h", 300),
            b=meta.get("b", 300),
            L_clear=meta.get("L_clear", 3.0),
            end_condition=meta.get("end_condition", "fixed_fixed")
        )
        N = meta.get("N_uls", 1000.0)
        M = meta.get("M_uls", 0.0)
        return solver.solve(N, M)

    def _route_wall(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        solver = WallSolver(
            member_id=load_data.member_id,
            storey=meta.get("storey", 1),
            h_clear=meta.get("h_clear", 3.0),
            thickness=meta.get("thickness", 200),
            design_code=self.design_code
        )
        N = meta.get("N_axial_kN", 200.0)
        M = meta.get("beam_moment_kNm_per_m", 10.0)
        return solver.solve(N_axial_kN=N, beam_moment_kNm_per_m=M)

    def _route_footing(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        f_type = meta.get("footing_type", "pad")
        if f_type == "pad":
            solver = PadFootingSolver(
                member_id=load_data.member_id,
                col_c1=meta.get("c1", 300),
                col_c2=meta.get("c2", 300),
                qa_allowable_kpa=meta.get("qa", 200)
            )
            return solver.solve(meta.get("N_sls", 500), meta.get("N_uls", 750), meta.get("M_uls", 50))
        return None # Simplified

    def _route_staircase(self, load_data: MemberLoadOutput, meta: Dict[str, Any]) -> MemberAnalysisResult:
        solver = StaircaseSolver(
            member_id=load_data.member_id,
            L_plan=meta.get("L_plan", 4.0),
            R=meta.get("R", 150.0),
            G=meta.get("G", 300.0),
            waistband_thickness=meta.get("h_w", 150.0),
            finishes_kpa=meta.get("finishes", 1.0),
            live_load_kpa=meta.get("live_load", 3.0),
            design_code=self.design_code
        )
        return solver.solve()

    def generate_full_report(self, members_to_analyze: List[Dict[str, Any]]) -> AnalysisOutputSchema:
        """
        Takes a list of member data (load_output + meta) and returns the full analysis schema.
        """
        all_results = []
        for item in members_to_analyze:
            result = self.analyze_member(item["load_data"], item["meta"])
            all_results.append(result)
            
        return AnalysisOutputSchema(
            analysis_id=str(uuid.uuid4()),
            design_code=self.design_code,
            members=all_results
        )

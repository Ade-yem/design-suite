import sys
import os
import numpy as np

# Add apps/api to path to allow importing core modules
sys.path.append(os.path.join(os.getcwd()))

from core.analysis.global_solver import GlobalMatrixSolver
from core.reporting.calc_sheet import BMDGenerator, SFDGenerator

def analyze_beam():
    print("Initializing Global Matrix Solver...")
    solver = GlobalMatrixSolver()

    # Beam Properties (Typical Concrete Section 230x450mm)
    E = 30e9        # 30 GPa
    b = 0.23
    h = 0.45
    A = b * h
    I = (b * h**3) / 12
    
    print(f"Properties: E={E/1e6:.0f} MPa, A={A:.4f} m2, I={I:.6f} m4")

    # Node Definitions (x, y)
    # N1 at 0m, N2 at 4m, PL at 6m, N3 at 10m, N4 at 13m
    nodes = {
        "N1": solver.add_node("N1", 0.0, 0.0, [True, True, False]),
        "N2": solver.add_node("N2", 4.0, 0.0, [False, True, False]),
        "PL": solver.add_node("PL", 6.0, 0.0, [False, False, False]),
        "N3": solver.add_node("N3", 10.0, 0.0, [False, True, False]),
        "N4": solver.add_node("N4", 13.0, 0.0, [False, True, False])
    }

    # Element Definitions
    elements = {
        "E1": solver.add_element("E1", "N1", "N2", E, A, I),
        "E2": solver.add_element("E2", "N2", "PL", E, A, I),
        "E3": solver.add_element("E3", "PL", "N3", E, A, I),
        "E4": solver.add_element("E4", "N3", "N4", E, A, I)
    }

    # Load Definitions
    udl = -3000.0  # 3 kN/m downwards
    p_load = -18000.0 # 18 kN downwards
    
    # Apply UDL to all elements
    for eid in elements:
        solver.add_member_udl(eid, udl)
        
    # Apply Point Load at node PL
    solver.apply_nodal_load("PL", Fy=p_load)

    # Solve
    print("Solving system...")
    results = solver.solve()
    
    reactions = results["reactions"]
    internal_forces = results["internal_forces"]

    print("\n" + "="*40)
    print("REACTIONS (kN, kNm)")
    print("="*40)
    for node_id, r in sorted(reactions.items()):
        print(f"{node_id:<10} Fy: {r['Fy']/1000:>10.2f} kN")

    # --- Diagram Generation ---
    print("\nGenerating Diagram Data...")
    bmd_points = []
    sfd_points = []
    
    # Discretize each element
    num_steps = 20
    total_span = 13.0
    
    for eid, elem in elements.items():
        L = elem.length
        forces = internal_forces[eid]
        # End forces (Forces on member)
        # Sign convention in global_solver f_local: 
        # [Axial_i, Shear_i, Moment_i, Axial_j, Shear_j, Moment_j]
        # V(x) = V1 + w*x
        # M(x) = M1 + V1*x + w*x^2 / 2
        V1 = forces["node_i"]["V"]
        M1 = forces["node_i"]["M"]
        x_start = elem.node_i.x
        
        for i in range(num_steps + 1):
            x_local = (i / num_steps) * L
            x_global = x_start + x_local
            
            # w is applied in add_member_udl (downward is negative)
            # Internal Shear V(x) = V1 + w*x
            # Internal Moment M(x) = -M1 + V1*x + w*x^2/2 (Civil convention: Sagging +)
            V_x = V1 + udl * x_local
            M_x = -M1 + V1 * x_local + (udl * x_local**2) / 2.0
            
            bmd_points.append({"position_m": x_global, "moment_kNm": M_x / 1000.0})
            sfd_points.append({"position_m": x_global, "shear_kN": V_x / 1000.0})

    # Prepare input for generators
    analysis_output = {
        "bmd_points": bmd_points,
        "sfd_points": sfd_points
    }
    
    print("Producing SVGs...")
    bmd_gen = BMDGenerator()
    sfd_gen = SFDGenerator()
    
    bmd_svg = bmd_gen.generate(analysis_output, total_span)
    sfd_svg = sfd_gen.generate(analysis_output, total_span)
    
    # Write to files
    with open("bmd.svg", "w") as f:
        f.write(bmd_svg)
    with open("sfd.svg", "w") as f:
        f.write(sfd_svg)
        
    print(f"\nSuccess! Diagrams generated:")
    print(f"- BMD: {os.path.abspath('bmd.svg')}")
    print(f"- SFD: {os.path.abspath('sfd.svg')}")

if __name__ == "__main__":
    analyze_beam()

import numpy as np
from typing import List, Dict, Tuple, Any

class Node:
    """
    Structural node with coordinates, degrees of freedom, and forces.
    """
    def __init__(self, node_id: str, x: float, y: float):
        self.id = node_id
        self.x = x
        self.y = y
        # Global DOF indices [u, v, theta] will be set during assembly
        self.dof_indices: List[int] = [-1, -1, -1]
        
        # Boundary conditions: True means the DOF is fixed (restrained)
        # Sequence: [u (x-disp), v (y-disp), theta (rotation)]
        self.restraints: List[bool] = [False, False, False]
        
        # Applied nodal forces: [Fx, Fy, M]
        self.nodal_loads: np.ndarray = np.zeros(3)

class Element:
    """
    2D Frame element (Euler-Bernoulli) with axial stiffness.
    """
    def __init__(self, elem_id: str, node_i: Node, node_j: Node, E: float, A: float, I: float):
        self.id = elem_id
        self.node_i = node_i
        self.node_j = node_j
        self.E = E
        self.A = A
        self.I = I
        
        # Equivalent nodal forces from member loads: [Fx1, Fy1, M1, Fx2, Fy2, M2]
        self.fixed_end_forces_local: np.ndarray = np.zeros(6)

    @property
    def length(self) -> float:
        dx = self.node_j.x - self.node_i.x
        dy = self.node_j.y - self.node_i.y
        return np.sqrt(dx**2 + dy**2)

    @property
    def angle(self) -> float:
        """Angle of the element relative to the global X-axis (in radians)."""
        dx = self.node_j.x - self.node_i.x
        dy = self.node_j.y - self.node_i.y
        return np.arctan2(dy, dx)

    def local_stiffness_matrix(self) -> np.ndarray:
        """
        returns the 6x6 local stiffness matrix for a 2D frame element.
        Order of DOFs: [u1, v1, theta1, u2, v2, theta2]
        """
        L = self.length
        E = self.E
        A = self.A
        I = self.I
        
        k = np.zeros((6, 6))
        
        # Axial terms
        axial = E * A / L
        k[0, 0] = axial
        k[0, 3] = -axial
        k[3, 0] = -axial
        k[3, 3] = axial
        
        # Bending terms
        L2 = L * L
        L3 = L2 * L
        
        k[1, 1] = 12 * E * I / L3
        k[1, 2] = 6 * E * I / L2
        k[1, 4] = -12 * E * I / L3
        k[1, 5] = 6 * E * I / L2
        
        k[2, 1] = k[1, 2]
        k[2, 2] = 4 * E * I / L
        k[2, 4] = -6 * E * I / L2
        k[2, 5] = 2 * E * I / L
        
        k[4, 1] = k[1, 4]
        k[4, 2] = k[2, 4]
        k[4, 4] = 12 * E * I / L3
        k[4, 5] = -6 * E * I / L2
        
        k[5, 1] = k[1, 5]
        k[5, 2] = k[2, 5]
        k[5, 4] = k[4, 5]
        k[5, 5] = 4 * E * I / L
        
        return k

    def transformation_matrix(self) -> np.ndarray:
        """
        Returns the 6x6 transformation matrix T to convert from local to global coordinates.
        (Global = T^T * Local * T) Wait, actually typically k_global = T^T * k_local * T.
        If d_local = T * d_global.
        """
        c = np.cos(self.angle)
        s = np.sin(self.angle)
        
        T = np.zeros((6, 6))
        
        T[0, 0] = c
        T[0, 1] = s
        T[1, 0] = -s
        T[1, 1] = c
        T[2, 2] = 1.0
        
        T[3, 3] = c
        T[3, 4] = s
        T[4, 3] = -s
        T[4, 4] = c
        T[5, 5] = 1.0
        
        return T

    def global_stiffness_matrix(self) -> np.ndarray:
        k_local = self.local_stiffness_matrix()
        T = self.transformation_matrix()
        # k_global = T^T * k_local * T
        return T.T @ k_local @ T


class GlobalMatrixSolver:
    """
    Phase 1: General Matrix Stiffness Solver for 2D Frames and Continuous Beams.
    """
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.elements: Dict[str, Element] = {}
        
        self.total_dof = 0
        self.K_global = np.array([])
        self.F_global = np.array([])
        self.D_global = np.array([]) # Displacements
        
        # For managing boundary conditions
        self.free_dofs: List[int] = []
        self.fixed_dofs: List[int] = []

    def add_node(self, node_id: str, x: float, y: float, restraints: List[bool] = None) -> Node:
        node = Node(node_id, x, y)
        if restraints and len(restraints) == 3:
            node.restraints = restraints
        self.nodes[node_id] = node
        return node

    def add_element(self, elem_id: str, node_i_id: str, node_j_id: str, E: float, A: float, I: float) -> Element:
        node_i = self.nodes[node_i_id]
        node_j = self.nodes[node_j_id]
        elem = Element(elem_id, node_i, node_j, E, A, I)
        self.elements[elem_id] = elem
        return elem

    def apply_nodal_load(self, node_id: str, Fx: float=0.0, Fy: float=0.0, M: float=0.0):
        """Applies a point load directly at a node."""
        self.nodes[node_id].nodal_loads += np.array([Fx, Fy, M])

    def add_member_udl(self, elem_id: str, w: float):
        """
        Adds a uniform distributed load w (force/length, downwards is negative) along the local y-axis.
        Converts to fixed end forces in local coordinates.
        """
        elem = self.elements[elem_id]
        L = elem.length
        # Local Fixed End Forces (w is local y-direction)
        # F_yi = -wL/2, F_yj = -wL/2, Mi = -wL^2/12, Mj = wL^2/12
        # (Assuming w is typically negative for downwards, M_left is negative, M_right is positive)
        # In strictly standard FEA sign convention, vertical load w (positive downwards):
        # Reaction at left: V1 = wL/2, M1 = wL^2/12 (counter-clockwise required to hold)
        # We need "equivalent nodal forces" which are the opposite of fixed end reactions.
        # But commonly, fixed end reactions are what the element feels, applying force to the node.
        
        # Assuming w is defined such that negative w pulls the beam down in local-y:
        # FEM formulation uses Equivalent Nodal Forces = - (Fixed End Reactions)
        # Fyi = wL/2, Mi = wL^2/12
        
        # Let w be positive pointing UP in local y. Downward load: w is negative.
        # Fixed end reactions (forces exerted BY supports ON beam):
        # Ry_1 = -wL/2, M_1 = -w * L^2 / 12 (CCW is positive. Support moment is wL^2/12 CCW left, CW right)
        # Actually standard:
        # V1 = wL/2
        # M1 = wL^2 / 12  (counter-clockwise)
        # V2 = wL/2
        # M2 = -wL^2 / 12 (clockwise)
        # NOTE: if w is downwards (negative y), V1 = wL/2 (w negative -> negative V, i.e., downwards)
        
        w_up = w # If user passes negative for down, w_up is negative
        # Fixed end reactions vector:
        FER = np.array([
            0.0,                    # Fx1
            -w_up * L / 2,          # Fy1
            -w_up * (L**2) / 12,    # M1
            0.0,                    # Fx2
            -w_up * L / 2,          # Fy2
             w_up * (L**2) / 12     # M2
        ])
        # Equivalent Nodal Forces = - FER
        eq_nodal_forces = -FER
        elem.fixed_end_forces_local += eq_nodal_forces

    def _assign_dofs(self):
        """Assigns global DOF indices to all nodes and separates free/fixed DOFs."""
        dof_counter = 0
        self.free_dofs = []
        self.fixed_dofs = []
        
        for node in self.nodes.values():
            node.dof_indices = [dof_counter, dof_counter+1, dof_counter+2]
            
            for i in range(3):
                if node.restraints[i]:
                    self.fixed_dofs.append(dof_counter + i)
                else:
                    self.free_dofs.append(dof_counter + i)
            
            dof_counter += 3
            
        self.total_dof = dof_counter

    def _assemble_global_system(self):
        """Assembles the K global matrix and global force vector F."""
        n_dof = self.total_dof
        self.K_global = np.zeros((n_dof, n_dof))
        self.F_global = np.zeros(n_dof)
        
        # Apply direct nodal loads
        for node in self.nodes.values():
            for i in range(3):
                dof = node.dof_indices[i]
                self.F_global[dof] += node.nodal_loads[i]
                
        # Assemble element matrices and equivalent nodal forces
        for elem in self.elements.values():
            k_glob = elem.global_stiffness_matrix()
            
            # Map valid global indices
            elem_dofs = elem.node_i.dof_indices + elem.node_j.dof_indices
            
            # Add to K_global
            for local_r, global_r in enumerate(elem_dofs):
                for local_c, global_c in enumerate(elem_dofs):
                    self.K_global[global_r, global_c] += k_glob[local_r, local_c]
            
            # Add equivalent nodal forces from member loads
            T = elem.transformation_matrix()
            # global_forces = T^T @ local_forces
            # Wait, d_local = T d_global, so F_global = T^T F_local
            eq_nodal_forces_global = T.T @ elem.fixed_end_forces_local
            
            for local_r, global_r in enumerate(elem_dofs):
                self.F_global[global_r] += eq_nodal_forces_global[local_r]

    def solve(self) -> Dict[str, Any]:
        """
        Solves the Ku = F system for unknown displacements, and computes reactions and internal forces.
        """
        self._assign_dofs()
        self._assemble_global_system()
        
        self.D_global = np.zeros(self.total_dof)
        
        if len(self.free_dofs) > 0:
            # Partitioning matrices
            K_ff = self.K_global[np.ix_(self.free_dofs, self.free_dofs)]
            F_f = self.F_global[self.free_dofs]
            
            # Solve for free displacements: K_ff * D_f = F_f
            try:
                D_f = np.linalg.solve(K_ff, F_f)
            except np.linalg.LinAlgError:
                raise ValueError("Matrix is singular. Check boundary conditions (structure may be unstable).")
                
            # Place back into D_global
            for i, dof in enumerate(self.free_dofs):
                self.D_global[dof] = D_f[i]
                
        # Compute global force vector including reactions F = K * D
        F_total = self.K_global @ self.D_global
        
        # Reactions are F_total at fixed DOFs minus any applied loads at those DOFs
        # Note: self.F_global contained applied nodal loads and equivalent nodal loads
        # Total force at support = K * D = Reaction + Applied Nodal Forces (which we already mapped into F_global)
        # So Reaction = K * D - F_applied
        
        reactions = {}
        for node_id, node in self.nodes.items():
            r = []
            for i in range(3):
                dof_idx = node.dof_indices[i]
                if dof_idx in self.fixed_dofs:
                    reaction_val = F_total[dof_idx] - self.F_global[dof_idx]
                    r.append(reaction_val)
                else:
                    r.append(0.0)
            if any(node.restraints):
                reactions[node_id] = {"Fx": r[0], "Fy": r[1], "M": r[2]}
                
        # Internal Member Forces
        internal_forces = {}
        for elem_id, elem in self.elements.items():
            elem_dofs = elem.node_i.dof_indices + elem.node_j.dof_indices
            global_disps = self.D_global[elem_dofs]
            
            # Transform to local displacements
            T = elem.transformation_matrix()
            local_disps = T @ global_disps
            
            # F_local = k_local * d_local - Equivalent_Nodal_Forces_Local
            # The actual internal end forces (forces EXERTED BY nodes ON element)
            k_local = elem.local_stiffness_matrix()
            f_local = (k_local @ local_disps) - elem.fixed_end_forces_local
            
            # Sign convention standard:
            # f_local = [Axial_1, Shear_1, Moment_1, Axial_2, Shear_2, Moment_2]
            internal_forces[elem_id] = {
                "node_i": {"N": f_local[0], "V": f_local[1], "M": f_local[2]},
                "node_j": {"N": f_local[3], "V": f_local[4], "M": f_local[5]}
            }

        return {
            "displacements": self.D_global,
            "reactions": reactions,
            "internal_forces": internal_forces
        }

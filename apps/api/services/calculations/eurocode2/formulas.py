import math

def calculate_k_ec2(M: float, fck: float, b: float, d: float) -> float:
    """
    Calculate K factor for Eurocode 2.
    K = M / (b * d^2 * fck)
    """
    return M / (b * d**2 * fck)

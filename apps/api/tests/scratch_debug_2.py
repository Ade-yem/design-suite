from services.design.rc.common.select_reinforcement import select_beam_reinforcement
import math

res = select_beam_reinforcement(895, b_available=300, cover=30, link_dia=8)
print(res)

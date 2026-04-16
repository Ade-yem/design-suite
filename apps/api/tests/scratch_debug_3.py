from models.bs8110.beam import BeamSection
from services.design.rc.bs8110.beam import calculate_beam_reinforcement

section = BeamSection(b=225, h=450, cover=25, fcu=30, fy=460, fyv=250)
results = calculate_beam_reinforcement(section=section, M=100e6, V=50e3, span=5000)
print(f"As_req: {results['As_req']}")
for note in results['notes']:
    print(note)

print("\n--- SHEAR FAIL TEST ---")
section_small = BeamSection(b=150, h=150, cover=25, fcu=30, fy=460, fyv=250)
results_fail = calculate_beam_reinforcement(section=section_small, M=10e6, V=350e3, span=2000)
print(f"Status: {results_fail['status']}")
for note in results_fail['notes']:
    print(note)

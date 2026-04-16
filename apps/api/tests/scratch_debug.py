from models.ec2.beam import EC2BeamSection
from services.design.rc.eurocode2.beam import calculate_beam_reinforcement
import json

section = EC2BeamSection(b=300, h=600, cover=30, fck=30, fyk=500)
results = calculate_beam_reinforcement(section=section, M=200e6, V=100e3, span=6000)
print(f"As_req: {results['As_req']}")
for note in results['notes']:
    print(note)

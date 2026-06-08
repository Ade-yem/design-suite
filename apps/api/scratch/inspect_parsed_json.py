import json
import math

with open("/home/adehnaija/Documents/projects/design-suite/parsed.json", "r") as f:
    data = json.load(f)

entities = data.get("entities", [])

for label in ("1B8", "1B9", "1B10"):
    t_ent = None
    for ent in entities:
        if ent.get("dxf_type") in ("TEXT", "MTEXT"):
            content = ent.get("attributes", {}).get("text_content", "")
            if label in content:
                t_ent = ent
                break
    if not t_ent:
        print(f"Could not find {label} text entity!")
        continue

    tc = t_ent.get("bounding_box", {}).get("centroid", t_ent.get("geometry", {}).get("insertion_point", [0, 0]))
    
    # Find closest geometry entities
    geom_dists = []
    for ent in entities:
        if ent.get("dxf_type") not in ("TEXT", "MTEXT", "DIMENSION", "LEADER"):
            bbox = ent.get("bounding_box", {})
            centroid = bbox.get("centroid", [0.0, 0.0])
            dist = math.hypot(tc[0] - centroid[0], tc[1] - centroid[1])
            geom_dists.append((dist, ent))

    geom_dists.sort(key=lambda x: x[0])
    
    print(f"\n--- Closest geometry entities to {label} text ({t_ent.get('attributes', {}).get('text_content')}) ---")
    for dist, ent in geom_dists[:3]:
        print(f"Dist: {dist:.1f} mm | Type: {ent.get('dxf_type')} | Layer: {ent.get('layer')} | Hint: {ent.get('layer_hint')} | Flags: {ent.get('flags')}")
        print(f"  Geometry: {ent.get('geometry')}")

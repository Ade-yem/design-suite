import ast

with open("/home/adehnaija/Documents/projects/design-suite/res.txt", "r") as f:
    content = f.read()

# Load as python literal
members = ast.literal_eval(content)

print(f"Total members parsed: {len(members)}")
types = {}
voids = 0
for m in members:
    m_type = m.get("member_type")
    types[m_type] = types.get(m_type, 0) + 1
    if m.get("is_void"):
        voids += 1

print("\nMember type counts:")
for t, count in types.items():
    print(f"- {t}: {count}")

print(f"\nTotal voids/openings: {voids}")

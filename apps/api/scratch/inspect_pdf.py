import fitz
import re

pdf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.pdf"
doc = fitz.open(pdf_path)
print(f"Total Pages: {len(doc)}")
for i, page in enumerate(doc):
    print(f"\n--- PAGE {i+1} ---")
    text = page.get_text()
    print(text[:3000]) # print first 3000 chars of page text

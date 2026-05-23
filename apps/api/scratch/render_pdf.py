import fitz

pdf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.pdf"
doc = fitz.open(pdf_path)
page = doc[0]
pix = page.get_pixmap(dpi=150)
output_path = "/home/adehnaija/.gemini/antigravity/brain/5c647017-c270-40a0-b9cf-539702c7796c/Floor-beam.png"
pix.save(output_path)
print(f"PDF page successfully rendered to {output_path}")

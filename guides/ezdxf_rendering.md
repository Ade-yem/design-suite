# ezdxf Drawing Addon Documentation

This guide provides instructions and reference code for using the `ezdxf.addons.drawing` addon. The drawing addon decomposes complex DXF entities into simple geometric primitives and renders them to various output backends (SVG, PDF, PNG, DXF, etc.).

---

## Core Concepts

The rendering process consists of these primary steps:
1. **RenderContext**: Resolves and caches document-wide properties (layers, styles, line types, colors).
2. **Backend**: Receives drawing primitives (lines, polylines, paths, fills) and outputs them to a target format.
3. **Frontend**: Coordinates the rendering. It traverses the DXF layouts and feeds resolved drawing primitives to the Backend.
4. **Layout/Page**: Specifies page sizes, margins, scale factors, and orientation.

---

## 1. SVG Export (Native)

SVG export uses the native `SVGBackend` which is fast and does not require external C dependencies. Note that the SVG backend flips coordinates along the Y-axis and uses a compact integer coordinate system.

```python
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, svg, layout

def export_svg(dxf_path: str, output_svg_path: str) -> None:
    """Parses a DXF file and exports it to SVG format."""
    # Load DXF document
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    # 1. Create the render context
    context = RenderContext(doc)
    
    # 2. Create the backend
    backend = svg.SVGBackend()
    
    # 3. Create the frontend
    frontend = Frontend(context, backend)
    
    # 4. Draw the modelspace
    frontend.draw_layout(msp)
    
    # 5. Define an A4 page layout with 20mm margins
    page = layout.Page(
        width=210,
        height=297,
        unit=layout.Units.mm,
        margins=layout.Margins.all(20)
    )
    
    # 6. Retrieve SVG content as string and save
    svg_string = backend.get_string(page)
    with open(output_svg_path, "w", encoding="utf-8") as fp:
        fp.write(svg_string)
```

---

## 2. Frontend Configuration

You can customize the rendering properties (such as background color or line coloring policy) using `Configuration`.

```python
from ezdxf.addons.drawing import config

# Create a configuration for a white background and monochrome/black lines
cfg = config.Configuration(
    background_policy=config.BackgroundPolicy.WHITE,
    color_policy=config.ColorPolicy.BLACK,
    hatch_policy=config.HatchPolicy.NORMAL,  # NORMAL, IGNORE, OUTLINES, SOLID_FILL
)

# Instantiate the frontend with the configuration
frontend = Frontend(context, backend, config=cfg)
```

### Configuration Options:
- **LineweightPolicy**: Control lineweights (absolute, relative, or fixed).
- **LinePolicy**: Control whether linetypes are rendered accurately or as simple solid lines.
- **HatchPolicy**: Ignore, render only outlines, or solid fill hatches.
- **ColorPolicy**: Native color, black, white, monochrome, etc.
- **BackgroundPolicy**: Default, black, white, transparent (off), or custom.
- **TextPolicy**: Render text as filled shapes, outlines, or ignore completely.

---

## 3. Page Layout and Scaling

The `layout.Page` class controls page sizing, scaling, and orientation.

### Auto-Detect Page Size
Setting `width=0` and `height=0` automatically calculates the page size to tightly fit the drawing content.

```python
# Auto-detect page size with 2mm margins on all sides
page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(2))

# Scale content by 1:1 without forcing fit-to-page
svg_string = backend.get_string(
    page, 
    settings=layout.Settings(scale=1.0, fit_page=False)
)
```

### Scaling Content (e.g. 10:1 Scale)
```python
page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(2))

# scale=10 means 10 page units represent 1 drawing unit (10:1 uniform scale)
svg_string = backend.get_string(
    page,
    settings=layout.Settings(scale=10.0, fit_page=False)
)
```

---

## 4. PDF and PNG Export

PDF and PNG rendering use the `PyMuPdfBackend`.
> **Note**: Requires the `pymupdf` library.

### PDF Export
```python
from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config

def export_pdf(dxf_path: str, output_pdf_path: str) -> None:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    context = RenderContext(doc)
    backend = pymupdf.PyMuPdfBackend()
    
    # Configure white background
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE)
    frontend = Frontend(context, backend, config=cfg)
    
    frontend.draw_layout(msp)
    
    page = layout.Page(210, 297, layout.Units.mm, margins=layout.Margins.all(20))
    pdf_bytes = backend.get_pdf_bytes(page)
    
    with open(output_pdf_path, "wb") as fp:
        fp.write(pdf_bytes)
```

### PNG Export
```python
def export_png(dxf_path: str, output_png_path: str) -> None:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    context = RenderContext(doc)
    backend = pymupdf.PyMuPdfBackend()
    
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE)
    frontend = Frontend(context, backend, config=cfg)
    frontend.draw_layout(msp)
    
    page = layout.Page(210, 297, layout.Units.mm, margins=layout.Margins.all(20))
    
    # Specify DPI to control quality/resolution
    png_bytes = backend.get_pixmap_bytes(page, fmt="png", dpi=150)
    
    with open(output_png_path, "wb") as fp:
        fp.write(png_bytes)
```

---

## 5. DXF Primitive Export

The `DXFBackend` allows flattening, exploding, and converting complex elements (like text and arcs) back into raw DXF primitives (POINT, LINE, LWPOLYLINE, SPLINE, HATCH).

```python
from ezdxf.addons.drawing import Frontend, RenderContext, dxf

def flatten_dxf(input_dxf: str, output_dxf: str) -> None:
    doc = ezdxf.readfile(input_dxf)
    msp = doc.modelspace()
    
    export_doc = ezdxf.new()
    context = RenderContext(doc)
    backend = dxf.DXFBackend(export_doc.modelspace())
    
    frontend = Frontend(context, backend)
    frontend.draw_layout(msp)
    
    export_doc.saveas(output_dxf)
```

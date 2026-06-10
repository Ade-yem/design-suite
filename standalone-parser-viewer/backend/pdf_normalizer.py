"""
pdf_vision.py
=============
Option C — visual grounding for the Vision Agent.

Replaces the previous approach of base64-encoding a 24 MB AutoCAD PDF and
shipping it inline to Gemini (which silently downsampled it to an illegible
raster) with a deterministic, high-DPI rasterisation step that we control.

What it does
------------
1. Rasterises each PDF page with PyMuPDF (`fitz`) at a chosen DPI.
2. Crops away the surrounding sheet whitespace so the drawing fills the frame
   (small AutoCAD plans typically occupy <40% of a letter sheet).
3. Optionally emits overlapping tiles so dense beam/column labels stay legible
   even after the model's internal downscaling.
4. Returns LangChain-ready ``image_url`` content blocks.

A single page rasterised at 300 DPI is ~0.3 MB of PNG versus ~33 MB of base64
PDF, and every label is readable — which is what makes slab and *void*
detection work at all.

Drop-in usage
-------------
    from pdf_vision import build_vision_content

    content = build_vision_content(prompt_text, pdf_path)      # text + images
    response = await llm.ainvoke([HumanMessage(content=content)])

The result of rasterisation is cached per (path, mtime, dpi, ...) so calling it
once for the column stage and again for the slab/void stage does the work only
once.
"""

from __future__ import annotations

import base64
import functools
import io
import logging
import os
from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Tuple, TypedDict, Union

logger = logging.getLogger(__name__)


class TextContentBlock(TypedDict):
    """A LangChain content block containing text."""
    type: Literal["text"]
    text: str


class ImageUrlDetail(TypedDict):
    """Details for a visual content block's URL."""
    url: str


class ImageUrlContentBlock(TypedDict):
    """A LangChain content block containing an image URL."""
    type: Literal["image_url"]
    image_url: Union[str, ImageUrlDetail]


ContentBlock = Union[TextContentBlock, ImageUrlContentBlock]


@dataclass
class RasterImage:
    """A single rasterised image plus a short human label for the prompt."""
    png: bytes
    label: str
    width: int
    height: int

    @property
    def b64(self) -> str:
        return base64.b64encode(self.png).decode("utf-8")

    @property
    def data_url(self) -> str:
        return f"data:image/png;base64,{self.b64}"


# ── Rasterisation ─────────────────────────────────────────────────────────────


def _content_clip(page) -> Optional["Any"]:
    """
    Compute the bounding box of actual ink (vectors + text) on the page so we can
    crop away the surrounding sheet margin. Returns a fitz.Rect or None.
    """
    import fitz

    bbox = None
    try:
        for d in page.get_drawings():
            r = d.get("rect")
            if r is None:
                continue
            bbox = r if bbox is None else (bbox | r)
        for w in page.get_text("words"):
            r = fitz.Rect(w[:4])
            bbox = r if bbox is None else (bbox | r)
    except Exception as err:  # pragma: no cover - defensive
        logger.warning("Content-bbox detection failed, using full page: %s", err)
        return None

    if bbox is None or bbox.is_empty:
        return None

    # Pad a little so border linework isn't clipped.
    pad = 12.0
    bbox = fitz.Rect(bbox.x0 - pad, bbox.y0 - pad, bbox.x1 + pad, bbox.y1 + pad)
    # Stay inside the page.
    return bbox & page.rect


def _downscale_png(png: bytes, max_long_side: int) -> Tuple[bytes, int, int]:
    """Downscale a PNG so its longest side <= max_long_side. No-op if already small."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as im:
        w, h = im.size
        longest = max(w, h)
        if longest <= max_long_side:
            return png, w, h
        scale = max_long_side / float(longest)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        im = im.convert("RGB").resize(new_size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue(), new_size[0], new_size[1]


def _tile_png(
    png: bytes,
    grid: Tuple[int, int],
    overlap: float,
    max_long_side: int,
) -> List[Tuple[bytes, int, int, str]]:
    """
    Split a PNG into grid[0] x grid[1] overlapping tiles. Each tile is then
    downscaled to max_long_side. Returns (png, w, h, label) per tile.
    """
    from PIL import Image

    cols, rows = grid
    tiles: List[Tuple[bytes, int, int, str]] = []
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGB")
        W, H = im.size
        tw, th = W / cols, H / rows
        ox, oy = tw * overlap, th * overlap
        for r in range(rows):
            for c in range(cols):
                left = max(0, int(c * tw - ox))
                upper = max(0, int(r * th - oy))
                right = min(W, int((c + 1) * tw + ox))
                lower = min(H, int((r + 1) * th + oy))
                crop = im.crop((left, upper, right, lower))
                buf = io.BytesIO()
                crop.save(buf, format="PNG", optimize=True)
                tpng, twd, thd = _downscale_png(buf.getvalue(), max_long_side)
                label = f"detail tile (row {r + 1}/{rows}, col {c + 1}/{cols})"
                tiles.append((tpng, twd, thd, label))
    return tiles


def _rasterize_uncached(
    pdf_path: str,
    dpi: int,
    max_long_side: int,
    crop_to_content: bool,
    tile: bool,
    tile_grid: Tuple[int, int],
    tile_overlap: float,
    max_pages: int,
) -> List[RasterImage]:
    import fitz

    images: List[RasterImage] = []
    doc = fitz.open(pdf_path)
    try:
        n = min(doc.page_count, max_pages)
        for pno in range(n):
            page = doc[pno]
            clip = _content_clip(page) if crop_to_content else None

            pix = page.get_pixmap(dpi=dpi, clip=clip)
            full_png = pix.tobytes("png")

            # Overview: whole (cropped) page, downscaled to fit.
            ov_png, ov_w, ov_h = _downscale_png(full_png, max_long_side)
            page_tag = f" (page {pno + 1}/{n})" if n > 1 else ""
            images.append(
                RasterImage(ov_png, f"full drawing overview{page_tag}", ov_w, ov_h)
            )

            # Detail tiles, only worthwhile if the raster is genuinely large.
            if tile and max(pix.width, pix.height) > max_long_side:
                for tpng, tw, th, tlabel in _tile_png(
                    full_png, tile_grid, tile_overlap, max_long_side
                ):
                    images.append(RasterImage(tpng, tlabel + page_tag, tw, th))
    finally:
        doc.close()

    logger.info(
        "Rasterised %s -> %d image(s) at dpi=%d (tile=%s)",
        os.path.basename(pdf_path), len(images), dpi, tile,
    )
    return images


@functools.lru_cache(maxsize=8)
def _rasterize_cached(
    pdf_path: str,
    mtime: float,           # part of the cache key; invalidates on file change
    dpi: int,
    max_long_side: int,
    crop_to_content: bool,
    tile: bool,
    tile_grid: Tuple[int, int],
    tile_overlap: float,
    max_pages: int,
) -> Tuple[RasterImage, ...]:
    return tuple(
        _rasterize_uncached(
            pdf_path, dpi, max_long_side, crop_to_content,
            tile, tile_grid, tile_overlap, max_pages,
        )
    )


def rasterize_pdf(
    pdf_path: str,
    *,
    dpi: int = 300,
    max_long_side: int = 3072,
    crop_to_content: bool = True,
    tile: bool = True,
    tile_grid: Tuple[int, int] = (2, 2),
    tile_overlap: float = 0.06,
    max_pages: int = 4,
) -> List[RasterImage]:
    """
    Rasterise a PDF into legible PNG images for an LLM vision call.

    Parameters
    ----------
    dpi : int
        Render resolution. 300 keeps small text legible; bump to 400 for very
        dense sheets at the cost of larger tiles.
    max_long_side : int
        Each emitted image's longest side is capped here. Gemini tiles large
        images internally; ~3072 is a good balance of detail vs token cost.
    crop_to_content : bool
        Trim surrounding sheet whitespace so the drawing fills the frame.
    tile : bool
        Also emit overlapping detail tiles when the raster exceeds max_long_side.
        Strongly recommended for structural plans with small beam labels.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return []
    try:
        mtime = os.path.getmtime(pdf_path)
        return list(
            _rasterize_cached(
                pdf_path, mtime, dpi, max_long_side, crop_to_content,
                tile, tile_grid, tile_overlap, max_pages,
            )
        )
    except Exception as err:
        logger.warning("PDF rasterisation failed for '%s': %s", pdf_path, err)
        return []


# ── LangChain content assembly ────────────────────────────────────────────────


def images_to_content_blocks(images: List[RasterImage]) -> List[ImageUrlContentBlock]:
    """
    Convert RasterImage list to LangChain multimodal content blocks.

    Uses the string ``image_url`` form, which ``ChatGoogleGenerativeAI`` accepts.
    If you ever swap providers and hit a format error, switch to the dict form:
        {"type": "image_url", "image_url": {"url": img.data_url}}
    """
    return [
        {"type": "image_url", "image_url": img.data_url}
        for img in images
    ]


def build_vision_content(
    prompt_text: str,
    pdf_path: Optional[str],
    **raster_kwargs: Any,
) -> List[ContentBlock]:
    """
    Build the ``content`` list for a HumanMessage: the text prompt followed by
    rasterised, captioned drawing images. Falls back to text-only if there is no
    usable PDF (so the caller never has to special-case a missing file).
    """
    images = rasterize_pdf(pdf_path, **raster_kwargs) if pdf_path else []

    text_block: TextContentBlock = {"type": "text", "text": prompt_text}
    if not images:
        if pdf_path:
            logger.info("No images produced from PDF; sending text-only prompt.")
        return [text_block]

    # A short caption block keeps the model oriented across multiple images.
    caption = (
        "\n\nAttached drawing images follow, in this order:\n"
        + "\n".join(f"{i + 1}. {img.label} ({img.width}x{img.height}px)"
                    for i, img in enumerate(images))
    )
    text_block["text"] += caption
    content: List[ContentBlock] = [text_block]
    content.extend(images_to_content_blocks(images))
    return content


__all__ = [
    "RasterImage",
    "rasterize_pdf",
    "images_to_content_blocks",
    "build_vision_content",
]
"""Cắt figure thẳng từ trang PDF (Spec 2 ẢNH) — thay ảnh Docling cắt sẵn ~144 dpi.

Thuần + tất định: PyMuPDF render vùng bbox ở DPI mục tiêu, Pillow trim viền trắng, PNG không
nhúng thời gian. KHÔNG phụ thuộc docling. Cả đường Docling và hybrid gọi ``render_picture``
(docling_adapter) → ``crop_figure``.
"""

from __future__ import annotations

import io

import pymupdf as fitz
from PIL import Image, ImageChops

from .model import BBox

_WHITE = (255, 255, 255)


def _trim_white(img: Image.Image) -> Image.Image:
    """Bỏ viền trắng đồng nhất quanh ảnh. Ảnh toàn trắng → giữ nguyên (không cắt về rỗng)."""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, _WHITE)
    box = ImageChops.difference(rgb, bg).getbbox()
    if box is None:
        return img
    return img.crop(box)


def crop_figure(
    page: fitz.Page,
    bbox: BBox,
    *,
    dpi: int = 200,
    padding_pt: float = 4.0,
    trim_white: bool = True,
) -> tuple[bytes, tuple[int, int]]:
    """Cắt vùng ``bbox`` (point, gốc trên-trái) từ ``page``.

    Nới ``padding_pt`` mỗi phía (cứu "cụt hình"), clip vào mép trang, render ở ``dpi``, trim viền
    trắng (bỏ "dư viền"). Trả ``(png_bytes, (width_px, height_px))``.
    """
    x0, y0, x1, y1 = bbox
    rect = fitz.Rect(x0 - padding_pt, y0 - padding_pt, x1 + padding_pt, y1 + padding_pt)
    rect.normalize()
    rect.intersect(page.rect)  # clip vào mép trang
    pix = page.get_pixmap(clip=rect, dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img.load()
    if trim_white:
        img = _trim_white(img)
    out = io.BytesIO()
    img.save(out, format="PNG")  # tất định (không timestamp)
    return out.getvalue(), img.size

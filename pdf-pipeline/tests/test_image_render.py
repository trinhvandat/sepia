"""Cropper thuần (Spec 2): cắt vùng bbox từ trang PDF, nới padding + clip mép, render DPI, trim.

KHÔNG cần docling. Dựng PDF một trang bằng PyMuPDF trong bộ nhớ (tất định).
"""

from __future__ import annotations

import io

import pymupdf as fitz
from PIL import Image

from sepia_pipeline.image_render import _trim_white, crop_figure

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _one_page_doc(width: float = 200, height: float = 300) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    # Hình chữ nhật đen 100x100 pt ở giữa làm "ảnh".
    page.draw_rect(fitz.Rect(50, 50, 150, 150), color=(0, 0, 0), fill=(0, 0, 0))
    return doc


def test_dims_follow_dpi() -> None:
    page = _one_page_doc()[0]
    png, (w, h) = crop_figure(page, (50, 50, 150, 150), dpi=72, padding_pt=0, trim_white=False)
    assert png[:8] == _PNG_MAGIC
    # 72 dpi → 1 px/pt; vùng 100x100 pt → ~100x100 px.
    assert abs(w - 100) <= 2 and abs(h - 100) <= 2
    img = Image.open(io.BytesIO(png))
    img.load()
    assert img.size == (w, h)


def test_padding_clamped_to_page() -> None:
    page = _one_page_doc(200, 300)[0]
    # bbox phủ cả trang + padding lớn: không được vượt mép trang.
    _png, (w, h) = crop_figure(page, (0, 0, 200, 300), dpi=72, padding_pt=50, trim_white=False)
    assert w <= 201 and h <= 301


def test_trim_white_shrinks() -> None:
    page = _one_page_doc()[0]
    # Cắt rộng hơn hình đen (có viền trắng): trim phải nhỏ hơn bản không trim.
    _a, (wt, ht) = crop_figure(page, (20, 20, 180, 180), dpi=72, padding_pt=0, trim_white=True)
    _b, (wr, hr) = crop_figure(page, (20, 20, 180, 180), dpi=72, padding_pt=0, trim_white=False)
    assert wt < wr and ht < hr


def test_all_white_kept() -> None:
    white = Image.new("RGB", (10, 10), (255, 255, 255))
    assert _trim_white(white).size == (10, 10)


def test_deterministic() -> None:
    page = _one_page_doc()[0]
    a, _ = crop_figure(page, (40, 40, 160, 160), dpi=120)
    page2 = _one_page_doc()[0]
    b, _ = crop_figure(page2, (40, 40, 160, 160), dpi=120)
    assert a == b  # cùng input → cùng bytes

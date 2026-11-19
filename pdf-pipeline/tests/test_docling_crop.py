"""Đường Docling dùng cropper từ PDF (Spec 2). KHÔNG cần docling: item giả + trang PyMuPDF thật."""

from __future__ import annotations

from types import SimpleNamespace

import pymupdf as fitz
from PIL import Image

from sepia_pipeline.docling_adapter import _picture_rect, render_picture

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _FakeBBox:
    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self.l, self.t, self.r, self.b = left, top, right, bottom

    def to_top_left_origin(self, page_height: float):  # Docling API; đã top-left sẵn trong test
        return self


def _fake_pic_item(bbox: _FakeBBox, page_no: int = 1):
    return SimpleNamespace(prov=[SimpleNamespace(page_no=page_no, bbox=bbox)])


def _one_page_doc() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.draw_rect(fitz.Rect(50, 50, 150, 150), color=(0, 0, 0), fill=(0, 0, 0))
    return doc


def test_picture_rect_from_prov() -> None:
    doc = _one_page_doc()
    item = _fake_pic_item(_FakeBBox(50, 50, 150, 150))
    page, rect = _picture_rect(item, doc)
    assert rect == (50, 50, 150, 150)


def test_picture_rect_none_without_fdoc() -> None:
    item = _fake_pic_item(_FakeBBox(50, 50, 150, 150))
    assert _picture_rect(item, None) is None


def test_render_picture_crops_from_pdf() -> None:
    doc = _one_page_doc()
    item = _fake_pic_item(_FakeBBox(50, 50, 150, 150))
    got = render_picture(item, None, doc, image_dpi=72, figure_padding_pt=0)
    assert got is not None
    png, bbox, sdpi = got
    assert png[:8] == _PNG_MAGIC
    assert bbox == (50, 50, 150, 150)
    assert sdpi == 72


def test_render_picture_fallback_uses_docling_image() -> None:
    # Không prov / không fdoc → fallback ảnh Docling (get_image), không mang hình học.
    item = SimpleNamespace(prov=None, get_image=lambda doc: Image.new("RGB", (4, 4), (10, 10, 10)))
    got = render_picture(item, object(), None, image_dpi=72, figure_padding_pt=0)
    assert got is not None
    png, bbox, sdpi = got
    assert png[:8] == _PNG_MAGIC
    assert bbox is None and sdpi is None

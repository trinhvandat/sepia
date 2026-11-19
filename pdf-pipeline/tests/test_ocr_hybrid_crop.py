"""Đường hybrid cắt lại figure từ PDF (Spec 2).

Thuần, không docling: order_items giả + fitz thật.
"""

from __future__ import annotations

from types import SimpleNamespace

import pymupdf as fitz

from sepia_pipeline.model import ImageBlock
from sepia_pipeline.ocr_hybrid import _assemble_blocks


class _FakeBBox:
    def __init__(self, left: float, top: float, right: float, bottom: float) -> None:
        self.l, self.t, self.r, self.b = left, top, right, bottom

    def to_top_left_origin(self, page_height: float):
        return self


def _pic_entry(page: int = 1):
    item = SimpleNamespace(prov=[SimpleNamespace(page_no=page, bbox=_FakeBBox(50, 50, 150, 150))])
    return {"item": item, "label": "picture", "page": page, "bbox": None, "target": None}


def _one_page_doc() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.draw_rect(fitz.Rect(50, 50, 150, 150), color=(0, 0, 0), fill=(0, 0, 0))
    return doc


def test_hybrid_picture_cropped_from_pdf() -> None:
    fdoc = _one_page_doc()
    blocks, _dropped = _assemble_blocks(
        [_pic_entry(1)],
        doc=None,
        cached_pages={0},  # trang 1 có cache → caption từ Vision (rỗng ở đây)
        fdoc=fdoc,
        image_dpi=72,
        figure_padding_pt=0,
    )
    assert len(blocks) == 1
    img = blocks[0]
    assert isinstance(img, ImageBlock)
    assert img.bbox == (50, 50, 150, 150)
    assert img.source_dpi == 72
    assert img.png[:8] == b"\x89PNG\r\n\x1a\n"

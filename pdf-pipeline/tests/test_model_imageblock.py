"""ImageBlock mang hình học (Spec 2): backward-compat + dataclasses.replace giữ field mới."""

from __future__ import annotations

import dataclasses

from sepia_pipeline.model import ImageBlock


def test_imageblock_defaults_backward_compat() -> None:
    b = ImageBlock(png=b"x", page=3)  # caller cũ: chỉ png + page
    assert b.caption == ""
    assert b.bbox is None
    assert b.source_dpi is None


def test_imageblock_carries_geometry() -> None:
    b = ImageBlock(png=b"x", page=1, caption="hình 1", bbox=(1.0, 2.0, 3.0, 4.0), source_dpi=200)
    assert b.bbox == (1.0, 2.0, 3.0, 4.0)
    assert b.source_dpi == 200


def test_replace_caption_keeps_geometry() -> None:
    # Gắn caption sau (docling/hybrid) KHÔNG được mất bbox/source_dpi.
    b = ImageBlock(png=b"x", page=1, bbox=(1.0, 2.0, 3.0, 4.0), source_dpi=200)
    b2 = dataclasses.replace(b, caption="chú thích")
    assert b2.caption == "chú thích"
    assert b2.bbox == (1.0, 2.0, 3.0, 4.0)
    assert b2.source_dpi == 200

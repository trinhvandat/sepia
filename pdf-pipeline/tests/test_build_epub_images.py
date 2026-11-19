"""Spec 2: build_epub siết cỡ ảnh (CSS + <img> attr) và nét (trần cỡ downscale-only)."""

from __future__ import annotations

import io

from PIL import Image

from sepia_pipeline.build_epub import _IMG_MAX_EDGE, _block_html, _css, _process_image
from sepia_pipeline.model import ImageBlock


def _png(w: int, h: int, color=(123, 50, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_css_limits_height() -> None:
    css = _css("serif")
    assert "max-height" in css
    assert "object-fit" in css


def test_process_image_downscales_to_max_edge() -> None:
    out = _process_image(_png(_IMG_MAX_EDGE * 2, _IMG_MAX_EDGE))
    assert out is not None
    _data, _ext, _mt, wh = out
    assert wh is not None
    assert max(wh) == _IMG_MAX_EDGE  # downscale tới trần


def test_process_image_no_upscale() -> None:
    out = _process_image(_png(100, 80))
    assert out is not None
    _data, _ext, _mt, wh = out
    assert wh == (100, 80)  # KHÔNG phóng to ảnh nhỏ


def test_block_html_img_has_dims() -> None:
    html = _block_html(ImageBlock(png=_png(300, 200), page=5), [])
    assert 'width="300"' in html
    assert 'height="200"' in html
    assert "<figure>" in html


def test_tiny_image_dropped() -> None:
    # Ảnh < 64px vẫn bị bỏ (chỉ còn caption nếu có).
    html = _block_html(ImageBlock(png=_png(10, 10), page=1, caption="chú"), [])
    assert "<img" not in html
    assert "chú" in html

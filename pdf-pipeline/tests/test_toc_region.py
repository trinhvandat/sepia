"""Cơ chế 4 drop_printed_toc: bỏ vùng mục lục in sẵn neo mốc 'MỤC LỤC'. Thuần, dựng Block tay."""

from __future__ import annotations

from sepia_pipeline.model import Heading, Paragraph
from sepia_pipeline.reflow import (
    ReflowConfig,
    _ascii_fold,
    _is_real_body,
    _is_toc_marker,
)


def test_ascii_fold_strips_all_diacritics() -> None:
    assert _ascii_fold("MỤC LỤC") == "MUC LUC"
    assert _ascii_fold("MỰC LỰC") == "MUC LUC"  # OCR sai dấu ụ→ự
    assert _ascii_fold("muc luc") == "MUC LUC"
    assert _ascii_fold("Đông Y") == "DONG Y"  # đ→d, mũ/thanh bỏ


def test_is_toc_marker() -> None:
    assert _is_toc_marker(Heading(text="MỤC LỤC", level=1, page=1))
    assert _is_toc_marker(Heading(text="MỰC LỰC", level=1, page=1))  # OCR méo
    assert _is_toc_marker(Paragraph(text="Mục Lục", page=1))
    # Câu dài có cụm "mục lục" → KHÔNG phải mốc
    assert not _is_toc_marker(Paragraph(text="Mục lục của chương này rất dài", page=1))
    assert not _is_toc_marker(Heading(text="LỜI NÓI ĐẦU", level=1, page=1))


def test_is_real_body() -> None:
    cfg = ReflowConfig()
    # Văn xuôi thật: dài ≥60 ký tự, có chữ thường, không phải mục lục/số trang
    real = Paragraph(
        text=(
            "Mùa xuân là khoảng thời gian từ tiết Lập xuân tới tiết Lập hạ "
            "rất là quan trọng đối với nông dân"
        ),
        page=1,
    )
    assert _is_real_body(real, cfg)
    # Ngắn → không phải biên
    assert not _is_real_body(Paragraph(text="Chương 1", page=1), cfg)
    # Số trang đứng riêng → không
    assert not _is_real_body(Paragraph(text="46", page=1), cfg)
    # Tiêu đề in hoa (không có chữ thường) → không
    assert not _is_real_body(
        Paragraph(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y RẤT HAY VÀ BỔ ÍCH LẮM", page=1), cfg
    )
    # Heading không bao giờ là biên
    assert not _is_real_body(Heading(text="x" * 80 + " đoạn", level=1, page=1), cfg)

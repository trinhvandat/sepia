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
            "rất là quan trọng đối với nông dân."
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
    # Dài, chữ thường, nhưng kết bằng ':' (dạng tiêu đề chương) → không phải biên (kết câu THẬT)
    assert not _is_real_body(
        Paragraph(text="Những điều cần biết trước khi bước vào thế giới đông y cổ truyền:", page=1),
        cfg,
    )
    # Dài, chữ thường, nhưng kết bằng số trang (không có dấu kết câu) → không phải biên
    assert not _is_real_body(
        Paragraph(
            text="Những điều cần biết trước khi bước vào thế giới đông y cổ truyền trang 76",
            page=1,
        ),
        cfg,
    )


def _real_book_blocks() -> list:
    # Mô phỏng chap_0001: mở đầu thật → MỰC LỰC → mục vỡ + tên chương lặp → thân bài thật.
    return [
        Heading(text="LỜI NÓI ĐẦU", level=1, page=1),
        Paragraph(
            text="Đông y là kết tinh của kinh nghiệm phòng và chữa bệnh suốt mấy nghìn năm qua",
            page=1,
        ),
        Heading(text="MỰC LỰC", level=1, page=2),  # mốc (OCR méo)
        Paragraph(text="16-17 Dưỡng sinh mùa thu -. . Dưỡng sinh mùa đông .. 18-19", page=2),
        Heading(text="Chương 1", level=1, page=2),
        Heading(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", level=1, page=2),
        Paragraph(text="10. Bệnh tật là cuộc chiến giữa chính khí và tà khí", page=2),
        Paragraph(text="46", page=2),
        Paragraph(
            text="7. Cách phân biệt thuốc Đông y thật giả 74 • •• • 8. Những kiêng kỵ y . 76",
            page=2,
        ),
        Paragraph(
            text=(
                "Mùa xuân là khoảng thời gian từ tiết Lập xuân tới tiết Lập hạ, "
                "tức là các tháng giêng hai ba."
            ),
            page=3,
        ),
    ]


def test_mechanism4_drops_toc_region_keeps_real() -> None:
    from sepia_pipeline.reflow import drop_printed_toc

    kept, removed = drop_printed_toc(_real_book_blocks())
    texts = [getattr(b, "text", "") for b in kept]
    # Giữ mở đầu thật + thân bài thật
    assert "LỜI NÓI ĐẦU" in texts
    assert any(t.startswith("Đông y là kết tinh") for t in texts)
    assert any(t.startswith("Mùa xuân là khoảng") for t in texts)
    # Bỏ mốc + mục + tên chương lặp
    assert not any(_ascii_fold(t).strip() == "MUC LUC" for t in texts)
    assert "Chương 1" not in texts
    assert "BƯỚC VÀO THẾ GIỚI ĐÔNG Y" not in texts
    assert "46" not in texts
    assert not any(t.startswith("10. Bệnh tật") for t in texts)
    # GIỚI HẠN ĐÃ BIẾT (spec §7 rủi ro #1, hướng AN TOÀN): dòng mục lục run-on dạng văn xuôi, dù dài
    # và có chữ thường, KHÔNG kết thúc bằng dấu kết câu THẬT (. ! ? …) — nó kết bằng số trang/dấu
    # chấm rời rạc ("• •• • ... 76") — nên không thoả _ends_strong_sentence và không trở thành
    # biên; bị bỏ cùng vùng mục lục. Assert rõ để giới hạn này không bị che: nếu sau đó nới điều
    # kiện, dòng sẽ lọt → cần kiểm tra kỹ hơn trước khi thay đổi.
    assert not any(t.startswith("7. Cách phân biệt") for t in texts)


def test_mechanism4_colon_paragraph_does_not_end_region_but_period_does() -> None:
    """Đoạn kết bằng ':' (dạng tiêu đề) KHÔNG kết thúc vùng mục lục (bị bỏ cùng vùng); đoạn kết
    bằng '.' ngay sau đó mới là biên văn xuôi thật → dừng bỏ, được giữ."""
    from sepia_pipeline.reflow import drop_printed_toc

    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="16-17 Dưỡng sinh mùa thu -. . Dưỡng sinh mùa đông .. 18-19", page=1),
        Paragraph(text="Những điều cần biết trước khi bước vào thế giới đông y cổ truyền:", page=1),
        Paragraph(
            text=("Đông y là kết tinh của kinh nghiệm phòng và chữa bệnh suốt mấy nghìn năm qua."),
            page=2,
        ),
    ]
    kept, removed = drop_printed_toc(blocks)
    texts = [getattr(b, "text", "") for b in kept]
    # Đoạn kết ':' bị bỏ cùng vùng mục lục (không phải biên)
    assert not any(t.startswith("Những điều cần biết") for t in texts)
    # Đoạn kết '.' ngay sau đó là biên thật → được giữ
    assert any(t.startswith("Đông y là kết tinh") for t in texts)


def test_mechanism4_no_marker_unchanged() -> None:
    from sepia_pipeline.reflow import drop_printed_toc

    blocks = [
        Paragraph(
            text="Một đoạn văn xuôi bình thường không có mục lục gì ở đây cả nhé bạn ơi", page=1
        ),
        Heading(text="Chương 1", level=1, page=1),
        Paragraph(
            text="Nội dung chương một kể về nhiều thứ rất hay và bổ ích cho người đọc", page=1
        ),
    ]
    kept, removed = drop_printed_toc(blocks)
    assert len(kept) == 3  # không mốc → nguyên vẹn


def test_mechanism4_cap_prevents_runaway() -> None:
    from sepia_pipeline.reflow import ReflowConfig, drop_printed_toc

    # Mốc nhưng KHÔNG có biên văn xuôi thật trong cap nhỏ → KHÔNG bỏ gì (an toàn).
    blocks = [Heading(text="MỤC LỤC", level=1, page=1)]
    blocks += [Paragraph(text="x", page=1) for _ in range(5)]  # toàn khối ngắn, không biên
    kept, removed = drop_printed_toc(blocks, ReflowConfig(toc_region_max_blocks=3))
    assert len(kept) == len(blocks)  # cap chặn: không gặp biên → giữ hết


def test_pipeline_version_bumped_to_14() -> None:
    from sepia_pipeline import PIPELINE_VERSION

    assert PIPELINE_VERSION == 14

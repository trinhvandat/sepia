"""Test định tuyến engine (Mốc 1b) — logic chọn không cần cài Docling; tích hợp Docling thì skip."""

from pathlib import Path

import pymupdf as fitz
import pytest

import sepia_pipeline.docling_adapter as da
from sepia_pipeline.convert import _choose_engine, convert_pdf, should_prefer_image_ocr
from sepia_pipeline.model import Document, Line, Page, TextSpan


def test_choose_heuristic_forced(monkeypatch) -> None:
    monkeypatch.setattr(da, "docling_available", lambda: True)
    assert _choose_engine("heuristic", is_scan_ocr=True)[0] == "heuristic"


def test_choose_auto_text_unicode_uses_heuristic(monkeypatch) -> None:
    monkeypatch.setattr(da, "docling_available", lambda: True)
    assert _choose_engine("auto", is_scan_ocr=False)[0] == "heuristic"


def test_choose_auto_scan_ocr_uses_docling_when_available(monkeypatch) -> None:
    monkeypatch.setattr(da, "docling_available", lambda: True)
    assert _choose_engine("auto", is_scan_ocr=True)[0] == "docling"


def test_choose_auto_scan_ocr_falls_back_without_docling(monkeypatch) -> None:
    monkeypatch.setattr(da, "docling_available", lambda: False)
    engine, warnings = _choose_engine("auto", is_scan_ocr=True)
    assert engine == "heuristic"
    assert any("Docling" in w for w in warnings)


def test_choose_docling_explicit_errors_without_extra(monkeypatch) -> None:
    monkeypatch.setattr(da, "docling_available", lambda: False)
    with pytest.raises(RuntimeError):
        _choose_engine("docling", is_scan_ocr=False)


def test_convert_invalid_engine(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()
    with pytest.raises(ValueError):
        convert_pdf(pdf, tmp_path / "o.epub", engine="khong-biet")


# --- Lớp 0: trigger Vision khi lớp text PDF không đáng tin -------------------


def _doc(text: str) -> Document:
    span = TextSpan(text=text, font="X", size=10.0)
    line = Line(page=1, bbox=(0, 0, 100, 10), spans=(span,))
    page = Page(number=1, width=100, height=100, lines=(line,))
    return Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="s")


def test_prefer_image_ocr_when_vietnamese_but_low_score():
    # tiếng Việt thật — cố ý ≥8 ký tự Việt "thật" (ư/đ/ớ/ệ/ề/ỏ) để qua cổng looks_vietnamese
    # mặc định (min_real_chars=8) — NHƯNG lớp text hỏng dấu hệ thống nên điểm âm tiết vẫn thấp
    # (0.4 < 0.75).
    assert (
        should_prefer_image_ocr(_doc("phưdng thuóc nhiéu trưđc ngưài vớư bệnh nhưn đều khỏi"))
        is True
    )


def test_no_prefer_when_clean_vietnamese():
    assert should_prefer_image_ocr(_doc("phương thuốc nhiều trước người đông y")) is False


def test_no_prefer_when_not_vietnamese():
    assert should_prefer_image_ocr(_doc("the quick brown fox jumps over")) is False


def test_no_prefer_when_mostly_english_with_incidental_vn_names():
    # Chủ yếu tiếng Anh, chỉ có vài ký tự Việt "thật" lạc lõng (tên riêng Đức, Hung) → KHÔNG đủ
    # ≥8 ký tự để qua cổng looks_vietnamese (bảo vệ chống dương tính giả mà ngưỡng mặc định 8
    # tạo ra).
    text = (
        "The doctor from Da Nang and Hung Yen, Mr. Đức, presented new clinical "
        "findings about herbal treatment efficacy and dosage over several trials"
    )
    assert should_prefer_image_ocr(_doc(text)) is False


# --- Tích hợp Docling (skip nếu chưa cài extra) -------------------------------

docling = pytest.importorskip("docling", reason="cần `uv sync --extra docling`")


@pytest.fixture
def tiny_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    tw = fitz.TextWriter(page.rect)
    cjk = fitz.Font("cjk")
    tw.append((40, 80), "GIỚI THIỆU ĐÔNG Y", font=cjk, fontsize=20)
    tw.append((40, 120), "Đoạn văn tiếng Việt có dấu để Docling trích.", font=cjk, fontsize=11)
    tw.write_text(page)
    path = tmp_path / "tiny.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_docling_adapter_returns_blocks(tiny_pdf: Path) -> None:
    from sepia_pipeline.docling_adapter import extract_blocks_docling

    blocks = extract_blocks_docling(tiny_pdf)
    assert blocks, "Docling phải trả ít nhất một khối"


def test_convert_engine_docling_valid_and_deterministic(tiny_pdf: Path, tmp_path: Path) -> None:
    a = tmp_path / "a.epub"
    b = tmp_path / "b.epub"
    r = convert_pdf(tiny_pdf, a, engine="docling", run_check=False)
    convert_pdf(tiny_pdf, b, engine="docling", run_check=False)
    assert r.engine == "docling"
    assert a.exists()
    assert a.read_bytes() == b.read_bytes()  # Docling → EPUB tất định từng byte

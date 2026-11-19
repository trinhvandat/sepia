# Bỏ vùng Mục lục in sẵn (neo mốc "MỤC LỤC") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ cả vùng mục lục in sẵn (kể cả khi OCR làm mục vỡ) bằng cách neo theo mốc "MỤC LỤC" chịu lỗi dấu, dừng ở văn xuôi thật, có cap chống ăn lan.

**Architecture:** Thêm **cơ chế 4** vào `drop_printed_toc` (reflow.py), bổ sung 3 cơ chế hiện có. Hai helper thuần: `_ascii_fold` (bỏ mọi dấu + đ→d) nhận mốc; `_is_real_body` nhận biên kết thúc. Chỉ chạy khi có mốc ⇒ sách không mục lục in sẵn: 0 thay đổi.

**Tech Stack:** Python 3, `unicodedata`, pytest, ruff, uv. Thuần `list[Block]`, offline, tất định.

## Global Constraints

- **Offline + tất định**: cùng PDF + cùng `PIPELINE_VERSION` ⇒ EPUB byte-identical. Mọi hàm thuần.
- **Giữ 2-tuple** `drop_printed_toc(blocks, config) -> (kept, removed)` — KHÔNG đổi arity (10 test unpack 2 giá trị).
- **Chỉ kích hoạt sau mốc "MỤC LỤC"**; không mốc → danh sách blocks nguyên vẹn.
- **KHÔNG đụng** phần trước mốc (mở đầu thật) hay văn xuôi thật sau vùng.
- **Commit bỏ dòng `Co-Authored-By`** (repo tắt attribution).
- **Verify mỗi task** từ `pdf-pipeline/`: `uv run ruff format --check . && uv run ruff check . && uv run pytest -q` — tất cả xanh.
- Mọi lệnh chạy từ `pdf-pipeline/`.

## Lệch spec (có chủ đích)

- **Bỏ cảnh báo cap-hit** (spec §2.4 "phát cảnh báo"): threading warning qua `drop_printed_toc` sẽ phải đổi return thành 3-tuple → phá 10 test. Thay vào đó cap-hit = **im lặng không bỏ** (an toàn). `collect_warnings` không đổi.
- **Bỏ `toc_marker_max_letters`** (spec §3): so khớp đúng `_ascii_fold(text) == "MUC LUC"` đã tự loại câu dài ("MỤC LỤC của chương" → "MUC LUC CUA CHUONG" ≠ "MUC LUC"). Thừa.

---

### Task 1: Helper nhận mốc + nhận biên + cấu hình

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/reflow.py` (thêm `_ascii_fold`, `_is_toc_marker`, `_is_real_body`; thêm 2 trường `ReflowConfig`)
- Test: `pdf-pipeline/tests/test_toc_region.py` (create)

**Interfaces:**
- Consumes: `collapse_ws`, `is_page_number_line`, `_is_toc_entry_text`, `_non_space_len` (đã có trong reflow.py); `unicodedata` (đã import ở reflow.py:18).
- Produces:
  - `_ascii_fold(text: str) -> str` — bỏ mọi dấu (thanh+móc+mũ) + `đ/Đ→d/D`, hoa hoá.
  - `_is_toc_marker(block: Block) -> bool` — `_ascii_fold(collapse_ws(text)).strip() == "MUC LUC"`.
  - `_is_real_body(block: Block, config: ReflowConfig) -> bool` — Paragraph văn xuôi thật.
  - `ReflowConfig.toc_body_min_chars: int = 60`, `ReflowConfig.toc_region_max_blocks: int = 60`.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_toc_region.py`:
```python
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
    real = Paragraph(text="Mùa xuân là khoảng thời gian từ tiết Lập xuân tới tiết Lập hạ nhé", page=1)
    assert _is_real_body(real, cfg)
    # Ngắn → không phải biên
    assert not _is_real_body(Paragraph(text="Chương 1", page=1), cfg)
    # Số trang đứng riêng → không
    assert not _is_real_body(Paragraph(text="46", page=1), cfg)
    # Tiêu đề in hoa (không có chữ thường) → không
    assert not _is_real_body(Paragraph(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y RẤT HAY VÀ BỔ ÍCH LẮM", page=1), cfg)
    # Heading không bao giờ là biên
    assert not _is_real_body(Heading(text="x" * 80 + " đoạn", level=1, page=1), cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py -v`
Expected: FAIL (`ImportError: cannot import name '_ascii_fold'`).

- [ ] **Step 3: Write minimal implementation**

In `pdf-pipeline/sepia_pipeline/reflow.py`:

(a) Add the two `ReflowConfig` fields next to the existing `toc_run_min`/`toc_page_fraction` (around line 52). After the `toc_page_fraction: float = 0.5` line, add:
```python
    # Cơ chế 4 (neo mốc "MỤC LỤC"): từ mốc, bỏ vùng mục lục tới khi gặp văn xuôi thật (Paragraph
    # ≥ toc_body_min_chars ký tự, có chữ thường, không phải mục lục/số trang). Cap toc_region_max_blocks
    # chặn ăn lan: quét hết cap mà chưa gặp biên → KHÔNG bỏ gì (an toàn).
    toc_body_min_chars: int = 60
    toc_region_max_blocks: int = 60
```

(b) Add the three helpers right before `drop_printed_toc` (before line 368, after `_is_strong_toc`):
```python
# Cơ chế 4: mục lục in sẵn OCR-vỡ (số trang đứng riêng, mục không dấu-dẫn, tên chương lặp) không khớp
# 3 cơ chế trên. Neo theo mốc "MỤC LỤC" (chịu lỗi dấu: "MỰC LỰC"), bỏ cả vùng tới khi gặp văn xuôi thật.
def _ascii_fold(text: str) -> str:
    """Bỏ MỌI dấu (thanh + móc/mũ/breve) + ``đ/Đ→d/D``, hoa hoá. 'MỤC LỤC'/'MỰC LỰC' → 'MUC LUC'."""
    s = text.replace("đ", "d").replace("Đ", "D")  # đ không phân rã NFD → map trước
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # bỏ mọi combining mark
    return unicodedata.normalize("NFC", s).upper()


def _is_toc_marker(block: Block) -> bool:
    """Khối là mốc 'MỤC LỤC' (chịu lỗi dấu). So khớp đúng → tự loại câu dài chứa cụm này."""
    if not isinstance(block, Heading | Paragraph):
        return False
    return _ascii_fold(collapse_ws(block.text)).strip() == "MUC LUC"


def _is_real_body(block: Block, config: ReflowConfig) -> bool:
    """Biên kết thúc vùng mục lục: Paragraph văn xuôi thật (dài, có chữ thường, không mục lục/số trang)."""
    if not isinstance(block, Paragraph):
        return False
    text = block.text
    if _is_toc_entry_text(text) or is_page_number_line(text):
        return False
    if _non_space_len(text) < config.toc_body_min_chars:
        return False
    return any(ch.islower() for ch in text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/reflow.py tests/test_toc_region.py
git commit -m "feat(pipeline): helper nhận mốc MỤC LỤC + biên văn xuôi (cơ chế 4 TOC)"
```

---

### Task 2: Cơ chế 4 trong `drop_printed_toc`

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/reflow.py` (`drop_printed_toc` — thêm bước 4 trước khi tính `removed`/`kept`)
- Test: `pdf-pipeline/tests/test_toc_region.py` (thêm case)

**Interfaces:**
- Consumes: `_is_toc_marker`, `_is_real_body` (Task 1); `drop` list + `blocks` + `config` trong `drop_printed_toc`.
- Produces: `drop_printed_toc` vẫn trả `(kept, removed)` — không đổi chữ ký.

- [ ] **Step 1: Write the failing test**

Append to `pdf-pipeline/tests/test_toc_region.py`:
```python
def _real_book_blocks() -> list:
    # Mô phỏng chap_0001: mở đầu thật → MỰC LỰC → mục vỡ + tên chương lặp → thân bài thật.
    return [
        Heading(text="LỜI NÓI ĐẦU", level=1, page=1),
        Paragraph(text="Đông y là kết tinh của kinh nghiệm phòng và chữa bệnh suốt mấy nghìn năm qua", page=1),
        Heading(text="MỰC LỰC", level=1, page=2),  # mốc (OCR méo)
        Paragraph(text="16-17 Dưỡng sinh mùa thu -. . Dưỡng sinh mùa đông .. 18-19", page=2),
        Heading(text="Chương 1", level=1, page=2),
        Heading(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", level=1, page=2),
        Paragraph(text="10. Bệnh tật là cuộc chiến giữa chính khí và tà khí", page=2),
        Paragraph(text="46", page=2),
        Paragraph(text="7. Cách phân biệt thuốc Đông y thật giả 74 • •• • 8. Những kiêng kỵ y . 76", page=2),
        Paragraph(text="Mùa xuân là khoảng thời gian từ tiết Lập xuân tới tiết Lập hạ, tức là các tháng giêng hai ba", page=3),
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


def test_mechanism4_no_marker_unchanged() -> None:
    from sepia_pipeline.reflow import drop_printed_toc

    blocks = [
        Paragraph(text="Một đoạn văn xuôi bình thường không có mục lục gì ở đây cả nhé bạn ơi", page=1),
        Heading(text="Chương 1", level=1, page=1),
        Paragraph(text="Nội dung chương một kể về nhiều thứ rất hay và bổ ích cho người đọc", page=1),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py -k mechanism4 -v`
Expected: FAIL (`test_mechanism4_drops_toc_region_keeps_real`: "Chương 1" still kept — mechanism 4 not implemented yet).

- [ ] **Step 3: Write minimal implementation**

In `drop_printed_toc` (reflow.py), insert mechanism 4 **after** the page-density block (after line 420, right before `removed = sum(...)` at line 422):
```python
    # 4) Vùng neo mốc "MỤC LỤC": từ mỗi mốc, bỏ tới khi gặp văn xuôi thật (_is_real_body). Cap
    #    toc_region_max_blocks chặn ăn lan: quét hết cap chưa gặp biên → KHÔNG bỏ (an toàn).
    n = len(blocks)
    i = 0
    while i < n:
        if _is_toc_marker(blocks[i]):
            end = None
            limit = min(n, i + 1 + config.toc_region_max_blocks)
            for j in range(i + 1, limit):
                if _is_real_body(blocks[j], config):
                    end = j
                    break
            if end is not None:
                for k in range(i, end):
                    drop[k] = True
                i = end
                continue
        i += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py -v`
Expected: PASS (all cases).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/reflow.py tests/test_toc_region.py
git commit -m "feat(pipeline): cơ chế 4 drop_printed_toc — bỏ vùng mục lục neo mốc"
```

---

### Task 3: Bump `PIPELINE_VERSION` + docs

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/__init__.py` (`PIPELINE_VERSION` 13→14 + changelog)
- Modify: `docs/03-pdf-pipeline.md` (ghi chú cơ chế 4) và `docs/05-tech-decisions.md` (nối ADR-011)
- Test: `pdf-pipeline/tests/test_toc_region.py` (assert version)

**Interfaces:** (none mới)

- [ ] **Step 1: Write the failing test**

Append to `pdf-pipeline/tests/test_toc_region.py`:
```python
def test_pipeline_version_bumped_to_14() -> None:
    from sepia_pipeline import PIPELINE_VERSION

    assert PIPELINE_VERSION == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py::test_pipeline_version_bumped_to_14 -v`
Expected: FAIL (`13 != 14`).

- [ ] **Step 3: Write minimal implementation**

(a) `pdf-pipeline/sepia_pipeline/__init__.py` — bump version (line 52) + changelog comment above it:
```python
# v14: BỎ VÙNG MỤC LỤC IN SẴN (cơ chế 4 drop_printed_toc). Mục lục OCR-vỡ (số trang đứng riêng, mục
#      không dấu-dẫn, tên chương lặp) không khớp 3 cơ chế cũ → neo theo mốc "MỤC LỤC" (chịu lỗi dấu,
#      "MỰC LỰC"), bỏ cả vùng tới khi gặp văn xuôi thật; cap chặn ăn lan. → nội dung đổi cho sách có
#      mục lục in sẵn kiểu vỡ.
PIPELINE_VERSION = 14
```

(b) `docs/03-pdf-pipeline.md` — tìm mục mô tả `drop_printed_toc` (hoặc xử lý mục lục in sẵn) và thêm một gạch đầu dòng: cơ chế 4 — neo mốc "MỤC LỤC" (chuẩn hoá bỏ dấu), bỏ cả vùng mục lục tới khi gặp văn xuôi thật (≥60 ký tự, chữ thường), cap 60 khối chống ăn lan, chỉ chạy khi có mốc.

(c) `docs/05-tech-decisions.md` — dưới ghi chú ADR-011 (clean-display), thêm một câu: cơ chế 4 mở rộng `drop_printed_toc` để bắt mục lục OCR-vỡ không có dấu-dẫn, neo theo mốc "MỤC LỤC".

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_toc_region.py::test_pipeline_version_bumped_to_14 -v`
Expected: PASS.

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/__init__.py docs/03-pdf-pipeline.md docs/05-tech-decisions.md tests/test_toc_region.py
git commit -m "chore(pipeline): PIPELINE_VERSION 14 (bỏ vùng mục lục) + docs"
```

---

## Sau khi xong tất cả task

- [ ] Full verify: `cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q` — tất cả xanh (gồm các test `drop_printed_toc` cũ không hồi quy).
- [ ] (Tùy chọn) convert lại sách thật (`out/qa-v13-pack` hoặc sample) → mở `chap_0001` kiểm trang mục lục đã biến mất, mở đầu + thân bài thật còn nguyên.
- [ ] PR `fix/printed-toc-drop` → master, chờ 2 check CI. PR body để dòng Claude Code (commit thì KHÔNG).

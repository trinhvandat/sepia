# Spec 2 (ẢNH) — Image rendering cho EPUB: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa 4 lỗi ảnh EPUB (cỡ/cắt/vị trí/nét) bằng cách cho `ImageBlock` mang hình học và cắt lại figure thẳng từ PDF ở DPI cao + padding, rồi siết cỡ/nén khi dựng EPUB.

**Architecture:** Thêm cropper thuần `image_render.crop_figure` (PyMuPDF + Pillow) dùng chung cho đường Docling và hybrid, thay cho ảnh Docling cắt sẵn ~144 dpi. `ImageBlock` thêm `bbox`/`source_dpi`. `build_epub` thêm CSS `max-height`/`object-fit`, nâng trần cỡ ảnh (downscale-only) và phát `<img width/height>`. Toàn bộ offline + tất định.

**Tech Stack:** Python 3, PyMuPDF (`pymupdf`), Pillow (PIL), ebooklib, pytest, ruff, uv. Docling là extra nặng (không chạy trong CI) — mọi test ở plan này **không** cần docling.

## Global Constraints

- **Offline + tất định**: không gọi mạng; cùng PDF + cùng `PIPELINE_VERSION` ⇒ EPUB giống hệt từng byte. Cropper/trim phải tất định (PIL PNG không nhúng thời gian).
- **Đổi output ảnh ⇒ tăng `PIPELINE_VERSION`** (12 → 13) + ghi changelog trong `sepia_pipeline/__init__.py`.
- **KHÔNG đụng pipeline chữ** (Spec 1) và **KHÔNG** sắp lại thứ tự đọc nhiều cột (để issue #18).
- **Lõi trung tính lĩnh vực**: không thêm khái niệm lĩnh vực vào code pipeline.
- **Commit bỏ dòng `Co-Authored-By`** (repo tắt attribution). Chỉ PR body để dòng Claude Code.
- **Verify bắt buộc** mỗi task: `cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest` — tất cả xanh (CI ép cả `format --check`).
- Mọi lệnh chạy từ thư mục `pdf-pipeline/` (nơi có `pyproject.toml`).

## Lệch spec (có chủ đích, YAGNI)

Spec §5 liệt kê 4 knob trong "ConvertConfig/CLI". Plan này:
- Đưa vào `ConvertConfig` **chỉ** `image_dpi` + `figure_padding_pt` (có tác động thật ở bước trích/cắt).
- Giữ `image_max_edge` (1800) + `jpeg_quality` (82) là **hằng số module** trong `build_epub.py` (chỉnh trong code), **không** thành config.
- **Không** thêm cờ CLI mới trong `__main__.py` (mặc định config đã đổi hành vi; một người bảo trì — thêm cờ sau nếu cần). Vì vậy `__main__.py` **không** nằm trong tệp sửa (khác với spec §10).

---

### Task 1: Thêm hình học vào `ImageBlock`

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/model.py:146-152`
- Test: `pdf-pipeline/tests/test_model_imageblock.py` (create)

**Interfaces:**
- Produces: `ImageBlock(png: bytes, page: int, caption: str = "", bbox: BBox | None = None, source_dpi: int | None = None)`. `BBox = tuple[float,float,float,float]` (point PDF, gốc trên-trái) đã có tại `model.py:12`.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_model_imageblock.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_model_imageblock.py -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'bbox'`).

- [ ] **Step 3: Write minimal implementation**

In `pdf-pipeline/sepia_pipeline/model.py`, replace the `ImageBlock` dataclass (lines 146-152):
```python
@dataclass(frozen=True)
class ImageBlock:
    """Ảnh (trang ảnh US-A6 hoặc hình do Docling cắt) → ``<figure><img>`` + ``<figcaption>``.

    ``bbox`` = vùng gốc trên trang PDF (point, gốc trên-trái); ``None`` = ảnh nguyên trang.
    ``source_dpi`` = DPI đã render ra ``png`` (provenance; ``None`` nếu không biết). Cả hai do đường
    Docling/hybrid ghi khi cắt lại figure từ PDF (Spec 2); build_epub KHÔNG phụ thuộc chúng để dựng.
    """

    png: bytes
    page: int
    caption: str = ""
    bbox: BBox | None = None
    source_dpi: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_model_imageblock.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/model.py tests/test_model_imageblock.py
git commit -m "feat(pipeline): ImageBlock mang bbox + source_dpi (Spec 2 ẢNH)"
```

---

### Task 2: Cropper dùng chung `image_render.crop_figure`

**Files:**
- Create: `pdf-pipeline/sepia_pipeline/image_render.py`
- Test: `pdf-pipeline/tests/test_image_render.py` (create)

**Interfaces:**
- Consumes: `BBox` from `model`.
- Produces:
  - `crop_figure(page: fitz.Page, bbox: BBox, *, dpi: int = 200, padding_pt: float = 4.0, trim_white: bool = True) -> tuple[bytes, tuple[int, int]]` — PNG bytes + `(width_px, height_px)`.
  - `_trim_white(img: Image.Image) -> Image.Image`.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_image_render.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_image_render.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sepia_pipeline.image_render'`).

- [ ] **Step 3: Write minimal implementation**

Create `pdf-pipeline/sepia_pipeline/image_render.py`:
```python
"""Cắt figure thẳng từ trang PDF (Spec 2 ẢNH) — thay ảnh Docling cắt sẵn ~144 dpi.

Thuần + tất định: PyMuPDF render vùng bbox ở DPI mục tiêu, Pillow trim viền trắng, PNG không nhúng
thời gian. KHÔNG phụ thuộc docling. Cả đường Docling và hybrid gọi ``render_picture`` (docling_adapter)
→ ``crop_figure``.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_image_render.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/image_render.py tests/test_image_render.py
git commit -m "feat(pipeline): cropper image_render.crop_figure (padding + DPI + trim)"
```

---

### Task 3: Dùng cropper trong đường Docling

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/docling_adapter.py` (thêm `_picture_rect`/`render_picture`; sửa `_picture_blocks`, caption re-attach dòng 219, `extract_blocks_docling`)
- Test: `pdf-pipeline/tests/test_docling_crop.py` (create)

**Interfaces:**
- Consumes: `crop_figure` (Task 2), `ImageBlock` with `bbox`/`source_dpi` (Task 1).
- Produces:
  - `_picture_rect(item, fdoc) -> tuple[fitz.Page, BBox] | None`
  - `render_picture(item, doc, fdoc, *, image_dpi: int, figure_padding_pt: float) -> tuple[bytes, BBox | None, int | None] | None` — `(png, bbox, source_dpi)`; cắt từ PDF nếu có toạ độ, nếu không fallback ảnh Docling (`bbox=None, source_dpi=None`).
  - `extract_blocks_docling(..., image_dpi: int = 200, figure_padding_pt: float = 4.0)`.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_docling_crop.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_docling_crop.py -v`
Expected: FAIL (`ImportError: cannot import name '_picture_rect'`).

- [ ] **Step 3: Write minimal implementation**

In `pdf-pipeline/sepia_pipeline/docling_adapter.py`:

(a) Add imports near the top (after line 15 `import pymupdf as fitz`):
```python
import dataclasses

from .image_render import crop_figure
from .model import BBox
```
(Keep the existing `from .model import Block, Heading, ImageBlock, Paragraph, Table` line; add `BBox` to it or import separately as above.)

(b) Add two helpers right after `_png_of` (after line 59):
```python
def _picture_rect(item, fdoc) -> tuple[fitz.Page, BBox] | None:
    """Trang PyMuPDF + bbox (point, gốc trên-trái) của một picture Docling; ``None`` nếu thiếu toạ độ."""
    prov = getattr(item, "prov", None)
    if not prov or fdoc is None:
        return None
    page_no = int(getattr(prov[0], "page_no", 0) or 0)
    if page_no < 1 or page_no > fdoc.page_count:
        return None
    page = fdoc[page_no - 1]
    h = page.rect.height
    bb = prov[0].bbox
    try:
        tl = bb.to_top_left_origin(page_height=h)
        rect: BBox = (tl.l, tl.t, tl.r, tl.b)
    except Exception:
        rect = (bb.l, h - bb.t, bb.r, h - bb.b)
    return page, rect


def render_picture(
    item, doc, fdoc, *, image_dpi: int, figure_padding_pt: float
) -> tuple[bytes, BBox | None, int | None] | None:
    """Ảnh figure: cắt lại từ PDF (nét + nới viền) nếu có toạ độ; không thì fallback ảnh Docling."""
    rect_info = _picture_rect(item, fdoc)
    if rect_info is not None:
        page_obj, bbox = rect_info
        png, _wh = crop_figure(page_obj, bbox, dpi=image_dpi, padding_pt=figure_padding_pt)
        return png, bbox, image_dpi
    png = _png_of(item, doc)
    if png is None:
        return None
    return png, None, None
```

(c) Replace `_picture_blocks` (lines 135-153) with:
```python
def _picture_blocks(
    item,
    doc,
    fdoc,
    page: int,
    min_chars: int,
    *,
    image_dpi: int,
    figure_padding_pt: float,
) -> list[Block]:
    """Xử lý một picture: khung chữ → đoạn văn; hình có nhãn ngắn → ảnh (cắt lại từ PDF) + caption."""
    clip_text = _picture_clip_text(item, fdoc)
    if _non_space_len(clip_text) >= min_chars:
        blocks: list[Block] = []
        for part in re.split(r"\n\s*\n", clip_text):
            text = normalize_text(part)
            if text and re.search(r"\w", text):
                blocks.append(Paragraph(text=text, page=page))
        if blocks:
            return blocks
    got = render_picture(item, doc, fdoc, image_dpi=image_dpi, figure_padding_pt=figure_padding_pt)
    if got is None:
        return []
    png, bbox, sdpi = got
    caption = _caption_text(item, doc) or normalize_text(clip_text)
    return [ImageBlock(png=png, page=page, caption=caption, bbox=bbox, source_dpi=sdpi)]
```

(d) Fix caption re-attach (line 219) to preserve geometry. Replace:
```python
                    prev = blocks[-1]
                    blocks[-1] = ImageBlock(png=prev.png, page=prev.page, caption=text)
```
with:
```python
                    blocks[-1] = dataclasses.replace(blocks[-1], caption=text)
```

(e) Thread knobs through `extract_blocks_docling`. Change its signature (lines 170-175):
```python
def extract_blocks_docling(
    pdf_path: str | Path,
    *,
    image_scale: float = 2.0,
    text_in_picture_min_chars: int = TEXT_IN_PICTURE_MIN_CHARS,
    image_dpi: int = 200,
    figure_padding_pt: float = 4.0,
) -> list[Block]:
```
and its `picture` branch call (line 204):
```python
            elif label == "picture":
                blocks.extend(
                    _picture_blocks(
                        item,
                        doc,
                        fdoc,
                        page,
                        text_in_picture_min_chars,
                        image_dpi=image_dpi,
                        figure_padding_pt=figure_padding_pt,
                    )
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_docling_crop.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/docling_adapter.py tests/test_docling_crop.py
git commit -m "feat(pipeline): đường Docling cắt lại figure từ PDF qua cropper"
```

---

### Task 4: Dùng cropper trong đường hybrid (OCR)

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/ocr_hybrid.py` (`_assemble_blocks` nhận `fdoc`/knobs + picture branch + caption re-attach dòng 472-474; `extract_blocks_hybrid` mở fitz + thread)
- Test: `pdf-pipeline/tests/test_ocr_hybrid_crop.py` (create)

**Interfaces:**
- Consumes: `render_picture` (Task 3), `ImageBlock` geometry (Task 1).
- Produces: `_assemble_blocks(order_items, doc, cached_pages, *, text_in_picture_min_chars=..., fdoc=None, image_dpi: int = 200, figure_padding_pt: float = 4.0)`. `fdoc=None` ⇒ fallback ảnh Docling (giữ hành vi test cũ).

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_ocr_hybrid_crop.py`:
```python
"""Đường hybrid cắt lại figure từ PDF (Spec 2). Thuần, không docling: order_items giả + fitz thật."""

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_ocr_hybrid_crop.py -v`
Expected: FAIL (`TypeError: _assemble_blocks() got an unexpected keyword argument 'fdoc'`).

- [ ] **Step 3: Write minimal implementation**

In `pdf-pipeline/sepia_pipeline/ocr_hybrid.py`:

(a) Add imports. The file currently has **neither** `import dataclasses` **nor** `import pymupdf as fitz`, and only `from dataclasses import dataclass, field` (line 18). Add both module imports in the stdlib/third-party block (after line 16 `import unicodedata`):
```python
import dataclasses

import pymupdf as fitz
```
Then extend the existing **multi-line** docling_adapter import (lines 21-27) to also pull `render_picture` — it already imports `_caption_text` and `_png_of`; add `render_picture` to that import list (keep alphabetical/style of the block).

(b) Change `_assemble_blocks` signature (lines 398-404):
```python
def _assemble_blocks(
    order_items: list[dict],
    doc,
    cached_pages: set[int],
    *,
    text_in_picture_min_chars: int = TEXT_IN_PICTURE_MIN_CHARS,
    fdoc=None,
    image_dpi: int = 200,
    figure_padding_pt: float = 4.0,
) -> tuple[list[Block], int]:
```

(c) Replace the picture branch `else` body (lines 443-449) with:
```python
            else:
                got = render_picture(
                    item, doc, fdoc, image_dpi=image_dpi, figure_padding_pt=figure_padding_pt
                )
                if got is None:
                    continue
                png, bbox, sdpi = got
                # Trang có cache: caption chỉ từ chữ Vision (có thể rỗng); KHÔNG lấy caption ABBYY.
                caption = text if has_cache else (text or _caption_text(item, doc))
                blocks.append(
                    ImageBlock(png=png, page=page, caption=caption, bbox=bbox, source_dpi=sdpi)
                )
```

(d) Fix caption re-attach (lines 472-474) to preserve geometry. Replace:
```python
            if blocks and isinstance(blocks[-1], ImageBlock) and not blocks[-1].caption:
                prev = blocks[-1]
                blocks[-1] = ImageBlock(png=prev.png, page=prev.page, caption=text)
```
with:
```python
            if blocks and isinstance(blocks[-1], ImageBlock) and not blocks[-1].caption:
                blocks[-1] = dataclasses.replace(blocks[-1], caption=text)
```

(e) In `extract_blocks_hybrid` (lines 558-601): add knobs + open fitz + thread. Change signature:
```python
def extract_blocks_hybrid(
    pdf_path: str | Path,
    cache: OcrCache,
    *,
    image_scale: float = 2.0,
    text_in_picture_min_chars: int = TEXT_IN_PICTURE_MIN_CHARS,
    image_dpi: int = 200,
    figure_padding_pt: float = 4.0,
) -> tuple[list[Block], HybridReport]:
```
Open the PDF once (after `doc = conv.convert(...).document`, around line 575):
```python
    fdoc = fitz.open(str(pdf_path))
```
Pass it + knobs into the `_assemble_blocks` call (lines 599-601) and close in a `finally`:
```python
    try:
        blocks, dropped = _assemble_blocks(
            order_items,
            doc,
            cached_pages,
            text_in_picture_min_chars=text_in_picture_min_chars,
            fdoc=fdoc,
            image_dpi=image_dpi,
            figure_padding_pt=figure_padding_pt,
        )
    finally:
        fdoc.close()
```
(If the lines after `_assemble_blocks` build the `HybridReport`, keep them after the `try/finally`; only the `_assemble_blocks` call needs `fdoc` open.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_ocr_hybrid_crop.py tests/test_ocr_hybrid_assembly.py -v`
Expected: PASS (new test + all existing assembly tests still green via `fdoc=None` fallback).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/ocr_hybrid.py tests/test_ocr_hybrid_crop.py
git commit -m "feat(pipeline): đường hybrid cắt lại figure từ PDF qua cropper"
```

---

### Task 5: `build_epub` — cỡ (CSS/attr) + nét (trần cỡ, nén)

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/build_epub.py` (hằng số dòng 78-79; `_css` dòng 52-64; `_process_image` dòng 126-152; `_block_html` dòng 193-203)
- Test: `pdf-pipeline/tests/test_build_epub_images.py` (create)

**Interfaces:**
- Consumes: `ImageBlock` (Task 1).
- Produces: `_process_image(png: bytes) -> tuple[bytes, str, str, tuple[int, int] | None] | None` (thêm `(w,h)` của ảnh đầu ra; `None` nếu bytes hỏng không đọc được cỡ). `_css` chứa `max-height`/`object-fit`. `<img>` có `width`/`height` khi biết cỡ.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_build_epub_images.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_build_epub_images.py -v`
Expected: FAIL (`test_css_limits_height` + `_process_image` unpack to 4 values fails — hiện trả 3-tuple).

- [ ] **Step 3: Write minimal implementation**

In `pdf-pipeline/sepia_pipeline/build_epub.py`:

(a) Raise image constants (lines 78-79):
```python
_IMG_MAX_EDGE = 1800
_IMG_JPEG_QUALITY = 82
```

(b) Add height/`object-fit` to the `img` rule in `_css` (line 57). Replace:
```python
        "img { max-width: 100%; height: auto; }\n"
```
with:
```python
        "img { max-width: 100%; max-height: 95vh; width: auto; height: auto;"
        " object-fit: contain; }\n"
```

(c) Replace `_process_image` (lines 126-152) to return output dims:
```python
def _process_image(png: bytes) -> tuple[bytes, str, str, tuple[int, int] | None] | None:
    """Nén/đổi cỡ ảnh → ``(bytes, ext, media_type, (w,h)|None)`` hoặc ``None`` nếu bỏ (ảnh tí hon).

    Ảnh ít màu → PNG (optimize); ảnh nhiều màu (chụp/scan) → JPEG. Cạnh dài ≤ ``_IMG_MAX_EDGE``
    (chỉ **downscale**, không phóng to). Bytes hỏng → giữ PNG nguyên (không biết cỡ → ``(w,h)=None``).
    """
    try:
        img = Image.open(io.BytesIO(png))
        img.load()
    except Exception:
        return png, "png", "image/png", None

    w, h = img.size
    if max(w, h) < _IMG_MIN_EDGE:
        return None  # ảnh tí hon → bỏ

    if max(w, h) > _IMG_MAX_EDGE:
        scale = _IMG_MAX_EDGE / max(w, h)
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

    few_colors = img.convert("RGB").getcolors(maxcolors=_IMG_PALETTE_MAX) is not None
    out = io.BytesIO()
    if few_colors:
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), "png", "image/png", img.size
    img.convert("RGB").save(out, format="JPEG", quality=_IMG_JPEG_QUALITY, optimize=True)
    return out.getvalue(), "jpg", "image/jpeg", img.size
```

(d) Update `_block_html` ImageBlock branch (lines 193-203) to unpack 4-tuple + emit dims:
```python
    # ImageBlock — nén/đổi cỡ; ảnh tí hon bị bỏ (chỉ còn caption nếu có để vẫn tìm được).
    processed = _process_image(b.png)
    if processed is None:
        # ảnh tí hon → bỏ ảnh; giữ chú thích dạng <p> (figcaption trần ngoài <figure> là HTML lỗi).
        return f"<p>{_esc(b.caption)}</p>" if b.caption else ""
    caption = f"<figcaption>{_esc(b.caption)}</figcaption>" if b.caption else ""
    data, ext, media_type, wh = processed
    name = f"images/img_{len(images):04d}.{ext}"  # tên theo thứ tự duyệt → duy nhất + tất định
    images.append((name, data, media_type))
    alt = _attr(b.caption) if b.caption else f"Trang {b.page}"
    dims = f' width="{wh[0]}" height="{wh[1]}"' if wh else ""
    return f'<figure><img src="{name}" alt="{alt}"{dims}/>{caption}</figure>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_build_epub_images.py tests/test_build_epub.py -v`
Expected: PASS (new tests + existing build_epub tests still green).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/build_epub.py tests/test_build_epub_images.py
git commit -m "feat(pipeline): EPUB siết cỡ ảnh (max-height/object-fit, <img> dims) + trần 1800px"
```

---

### Task 6: Wiring `convert` + bump `PIPELINE_VERSION`

**Files:**
- Modify: `pdf-pipeline/sepia_pipeline/convert.py` (`ConvertConfig` dòng 39-43; call sites dòng 227 + 233)
- Modify: `pdf-pipeline/sepia_pipeline/__init__.py` (dòng 52 + changelog comment)
- Test: `pdf-pipeline/tests/test_convert_image_config.py` (create)

**Interfaces:**
- Consumes: `extract_blocks_docling`/`extract_blocks_hybrid` knobs (Task 3/4).
- Produces: `ConvertConfig(detect, reflow, image_dpi: int = 200, figure_padding_pt: float = 4.0)`; `PIPELINE_VERSION == 13`.

- [ ] **Step 1: Write the failing test**

Create `pdf-pipeline/tests/test_convert_image_config.py`:
```python
"""Spec 2: default DPI ảnh = 200, có figure_padding_pt; PIPELINE_VERSION = 13."""

from __future__ import annotations

from sepia_pipeline import PIPELINE_VERSION
from sepia_pipeline.convert import ConvertConfig


def test_image_dpi_default_200() -> None:
    assert ConvertConfig().image_dpi == 200


def test_figure_padding_default() -> None:
    assert ConvertConfig().figure_padding_pt == 4.0


def test_pipeline_version_bumped() -> None:
    assert PIPELINE_VERSION == 13
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pdf-pipeline && uv run pytest tests/test_convert_image_config.py -v`
Expected: FAIL (`image_dpi == 150`, no `figure_padding_pt`, version 12).

- [ ] **Step 3: Write minimal implementation**

(a) `pdf-pipeline/sepia_pipeline/convert.py` — update `ConvertConfig` (lines 39-43):
```python
@dataclass(frozen=True)
class ConvertConfig:
    detect: DetectConfig = dataclasses.field(default_factory=DetectConfig)
    reflow: ReflowConfig = dataclasses.field(default_factory=ReflowConfig)
    image_dpi: int = 200  # Spec 2: nâng từ 150 → 200 (nét hơn cho trang ảnh + figure)
    figure_padding_pt: float = 4.0  # Spec 2: nới viền khi cắt figure từ PDF
```

(b) Thread knobs into the docling call site (line 233):
```python
        blocks = extract_blocks_docling(
            pdf_path, image_dpi=config.image_dpi, figure_padding_pt=config.figure_padding_pt
        )
```

(c) Thread into the hybrid call site (line 227):
```python
        blocks, hybrid_report = extract_blocks_hybrid(
            pdf_path,
            ocr_cache_obj,
            image_dpi=config.image_dpi,
            figure_padding_pt=config.figure_padding_pt,
        )
```

(d) `pdf-pipeline/sepia_pipeline/__init__.py` — bump version (line 52) and add a changelog comment above it:
```python
# v13: ẢNH (Spec 2). ImageBlock mang bbox + source_dpi; figure cắt lại THẲNG từ PDF ở DPI 200 +
#      padding (image_render.crop_figure) thay ảnh Docling ~144 dpi; trim viền trắng. build_epub:
#      CSS max-height/object-fit + <img width/height>, trần cỡ 1200→1800 (downscale-only), JPEG q82.
#      → bytes ảnh trong EPUB đổi (cả trang ảnh heuristic do DPI 150→200).
PIPELINE_VERSION = 13
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pdf-pipeline && uv run pytest tests/test_convert_image_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify + commit**

```bash
cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
git add sepia_pipeline/convert.py sepia_pipeline/__init__.py tests/test_convert_image_config.py
git commit -m "feat(pipeline): wiring DPI/padding ảnh + PIPELINE_VERSION 13 (Spec 2)"
```

---

### Task 7: Tài liệu — ADR + mô tả pipeline

**Files:**
- Modify: `docs/05-tech-decisions.md` (thêm ADR mới)
- Modify: `docs/03-pdf-pipeline.md` (mô tả bước ảnh mới)

**Interfaces:** (none — tài liệu)

- [ ] **Step 1: Thêm ADR vào `docs/05-tech-decisions.md`**

Append a new ADR (dùng đúng định dạng/đánh số ADR kế tiếp của file — mở file, tìm ADR cuối, +1). Nội dung:
```markdown
## ADR-0XX — Geometry-aware image rendering: cắt lại figure từ PDF (padding + DPI)

**Bối cảnh:** `ImageBlock` cũ chỉ giữ `png` bytes; ảnh đường Docling/hybrid do Docling cắt sẵn
ở `images_scale=2.0` (~144 dpi) → không nới viền (cụt hình/dư viền) hay re-render nét hơn được.
Trang ảnh heuristic render 150 dpi. build_epub chỉ `max-width:100%` → ảnh dọc tràn cao; trần cỡ
cứng 1200px làm mờ trang scan lớn.

**Quyết định:** `ImageBlock` mang thêm `bbox` + `source_dpi`. Thêm cropper thuần
`sepia_pipeline/image_render.crop_figure` cắt figure **thẳng từ trang PDF bằng PyMuPDF** (bbox Docling
+ padding → clip mép → render DPI 200 → trim viền trắng), dùng chung cho cả đường Docling và hybrid
(`render_picture`). build_epub thêm CSS `max-height:95vh`/`object-fit:contain` + `<img width/height>`,
nâng trần cỡ 1200→1800 (chỉ downscale), JPEG q82 / PNG line-art (core media type EPUB — không WebP).

**Hệ quả:** Tất định (PyMuPDF + PIL PNG không timestamp), offline, không docling trong test.
Output ảnh đổi ⇒ `PIPELINE_VERSION` 12→13. Content pack có thể nặng hơn (DPI cao) — giảm bằng trần cỡ
+ JPEG. Thứ tự đọc nhiều cột KHÔNG xử lý ở đây (issue #18). Phạm vi: [Spec 2 design](./superpowers/specs/2026-11-18-spec2-images-epub-design.md).
```

- [ ] **Step 2: Cập nhật `docs/03-pdf-pipeline.md`**

Tìm mục mô tả xử lý ảnh (figure/trang ảnh) và thêm một đoạn ngắn: figure nay được **cắt lại từ PDF**
ở DPI 200 + padding + trim viền (không dùng ảnh Docling cắt sẵn); EPUB giới hạn chiều cao ảnh và phát
kích thước `<img>`; trần cỡ 1800px downscale-only; JPEG/PNG theo nội dung. Trỏ tới ADR mới.

- [ ] **Step 3: Verify (docs không ảnh hưởng test, vẫn chạy để chắc)**

Run: `cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q`
Expected: PASS (toàn bộ test xanh).

- [ ] **Step 4: Commit**

```bash
git add docs/05-tech-decisions.md docs/03-pdf-pipeline.md
git commit -m "docs: ADR geometry-aware image rendering + mô tả bước ảnh (Spec 2)"
```

---

## Sau khi xong tất cả task

- [ ] Chạy full verify lần cuối: `cd pdf-pipeline && uv run ruff format --check . && uv run ruff check . && uv run pytest -q` — tất cả xanh.
- [ ] (Tùy chọn, cần máy có sách + Docling) convert một PDF có hình thật → mở EPUB soát bằng mắt: ảnh không tràn, đủ viền, nét hơn, caption đúng hình. Tham chiếu quy ước QA emulator trong bộ nhớ dự án.
- [ ] Mở PR `feat/epub-images` → `master`, mô tả 4 lỗi + cách sửa, chờ 2 check CI (pipeline, app) + review. PR body để dòng Claude Code (commit thì KHÔNG).

# Thiết kế — Spec 2 (ẢNH): cắt / cỡ / nét / vị trí hình cho EPUB

> Trạng thái: ĐÃ DUYỆT hướng (2026-11-18). Kế tiếp: viết kế hoạch thực thi.
> Liên quan: [Spec 1 (CHỮ)](./2026-11-18-text-reocr-rewrite-design.md) (tách riêng, đã xong — PR #34),
> [03-pdf-pipeline.md](../../03-pdf-pipeline.md), [05-tech-decisions.md](../../05-tech-decisions.md),
> [ADR-009](../../05-tech-decisions.md) (OCR Vision + cache), issue #18 (reading-order nhiều cột — **ngoài** Spec 2).

## 1. Vấn đề & mục tiêu

Ảnh (figure/hình) trong EPUB dựng từ pipeline hiện bị **4 lỗi** (tác giả chốt 2026-11-18):
1. **Cỡ sai** — ảnh to/nhỏ bất thường, ảnh dọc tràn chiều cao viewport.
2. **Cắt sai** — dư/thiếu viền, cụt hình hoặc dính chữ.
3. **Vị trí/thứ tự sai** — nhất là trang bố cục nhiều cột (gắn issue #18).
4. **Nét/chất lượng kém** — mờ hoặc file nặng.

**Mục tiêu:** sửa 4 lỗi **trong pipeline** (`pdf-pipeline/`, tách khỏi app KMP), giữ triết lý dự án:
offline tuyệt đối + **tất định (chạy CI)**, ít phụ thuộc, một người bảo trì (NFR-4).

**Gốc kỹ thuật của lỗi 2 & 4:** `ImageBlock` hiện **chỉ giữ `png` bytes**, mất sạch bbox/trang/DPI
(`model.py:146`). Ảnh đường Docling/hybrid lại do **Docling tự cắt sẵn ở ~144 dpi** (`images_scale=2.0`)
→ không thể nới viền (padding) hay re-render nét hơn vì đã mất pixel gốc quanh vùng cắt.

**Ràng buộc đã chốt:**
- Pipeline **offline + tất định** (không có bước online nào trong Spec 2).
- Thay đổi output ảnh ⇒ **tăng `PIPELINE_VERSION`**.
- **Không** đụng pipeline chữ (Spec 1) và **không** ôm bài toán reading-order nhiều cột (để #18).

## 2. Kiến trúc — pipeline ảnh "biết hình học"

Hiện có **hai nguồn** ảnh, hợp nhất ở `ImageBlock` rồi cùng đi qua `build_epub._process_image`:
- **Heuristic (PyMuPDF)**: render **nguyên trang** thành PNG khi là "trang ảnh" (`convert._render_image_pages`
  tại `convert.py:131`, `extract.render_page_png(dpi=150)`).
- **Docling / OCR hybrid**: cắt từng "picture" do Docling phát hiện (`_png_of(item, doc)` → `item.get_image(doc)`,
  `docling_adapter.py:50`, dùng lại ở `ocr_hybrid.py`).

Thay đổi cốt lõi: thêm một **cropper dùng chung** — module mới `sepia_pipeline/image_render.py`, hàm **thuần**
và **tất định**, cắt figure **thẳng từ trang PDF bằng PyMuPDF**:

```
bbox (Docling, point) ─► nới padding đối xứng ─► clip vào mép trang
   ─► page.get_pixmap(clip=rect, dpi=target) ─► trim viền trắng đều
   ─► (png_bytes, (width_px, height_px))
```

Khả thi đã kiểm chứng: cả `docling_adapter` (`fitz.open(pdf_path)` tại `docling_adapter.py:183`) và
`ocr_hybrid` đều **đã cầm `fitz.Document` + bbox** và dùng `fitz.Rect`/transform toạ độ — cropper chỉ tái dùng
những gì có sẵn, **không** cần hạ tầng mới. `build_epub` vẫn là nơi resize/nén cuối cho EPUB (consumer).

Chữ ký dự kiến (tinh chỉnh khi lập plan):
```python
def crop_figure(
    page: fitz.Page, bbox: BBox, *, dpi: int, padding_pt: float, trim_white: bool = True
) -> tuple[bytes, tuple[int, int]]:
    """Cắt vùng bbox (point, gốc trên-trái) từ trang PDF, nới padding, clip mép, render DPI, trim viền."""
```

## 3. Data model (`model.py`)

`ImageBlock` thêm field, **mặc định `None`** để backward-compat với test/caller cũ:
```python
@dataclass(frozen=True)
class ImageBlock:
    png: bytes
    page: int
    caption: str = ""
    bbox: BBox | None = None       # vùng gốc trên trang PDF (point, gốc trên-trái); None = ảnh nguyên trang
    source_dpi: int | None = None  # DPI đã render ra png này
```
- `png` = crop đã render ở DPI mục tiêu (không còn phụ thuộc `get_image` của Docling).
- `bbox`/`source_dpi` để `build_epub` quyết nén và **không upscale** quá nguồn.
- `BBox` = `(x0,y0,x1,y1)` point PDF, đã có ở `model.py:12`.

## 4. Bốn lỗi → cách sửa

### 4.1 Lỗi (1) — Cỡ / tràn viewport
`build_epub._css` (`build_epub.py:52`) hiện chỉ `img{max-width:100%;height:auto}` → ảnh dọc tràn cao.
Sửa CSS:
```css
img { max-width: 100%; max-height: 95vh; width: auto; height: auto; object-fit: contain; }
figure { margin: 1em 0; text-align: center; }
```
Phát thuộc tính `width`/`height` cho `<img>` từ px thật (có sau `_process_image`) để giảm reflow-jump và giữ
tỷ lệ. (`vh`/`object-fit` được WebView hiện đại hỗ trợ — xem §9.)

### 4.2 Lỗi (2) — Cắt sai viền / cụt hình / dính chữ
- Thay `item.get_image(doc)` bằng `image_render.crop_figure(...)`: nới **padding nhỏ, đối xứng**
  (mặc định vài pt, ~2% cạnh) → cứu "cụt hình"; **clip vào mép trang** → không lỗi biên.
- **Trim viền trắng** đều, tất định sau render → bỏ "dư viền".
- Giữ ngưỡng **text-in-picture** (`TEXT_IN_PICTURE_MIN_CHARS=80`, `docling_adapter.py:22` / `ocr_hybrid.py:441`)
  chống "dính chữ"; padding cố ý nhỏ để không kéo chữ lân cận vào hình.

### 4.3 Lỗi (3) — Vị trí / thứ tự (phạm vi A: chỉ vị trí ẢNH)
- Giữ thứ tự ảnh theo `doc.iterate_items()` của Docling + **neo caption với figure** (đã có:
  `docling_adapter.py:209`, `ocr_hybrid.py:465`).
- Ảnh **nguyên trang** đặt đúng vị trí trang trong luồng (đã có: `reflow.build_blocks` `reflow.py:255`).
- **Không** sắp lại thứ tự đọc nhiều cột — để **issue #18**. Phần Spec 2 chỉ đảm bảo **không hồi quy** vị trí
  ảnh và caption dính đúng hình.

### 4.4 Lỗi (4) — Nét / nặng file
- Render ở **DPI mục tiêu 200** (cấu hình) cho **cả** figure (cropper) **và** ảnh nguyên trang — thay cho
  150 dpi heuristic (`convert.py:43`) và `images_scale=2.0`≈144 dpi (`docling_adapter.py:173`, `ocr_hybrid.py:562`).
- **Thay trần cứng 1200px** (`_IMG_MAX_EDGE`, `build_epub.py:78`) bằng knob `image_max_edge` (mặc định ~1800px),
  **chỉ downscale, không upscale** (bám `source_dpi`/px thật).
- Nén (chốt phương án A): **JPEG q~82** cho ảnh chụp/scan nhiều màu; **PNG** cho line-art ≤256 màu
  (giữ logic `_IMG_PALETTE_MAX` ở `build_epub.py:146`). Giữ bỏ ảnh `< _IMG_MIN_EDGE=64px`.

## 5. Cấu hình (`ConvertConfig` / CLI)

Knob mới, mặc định **tất định**:
- `image_dpi`: nâng 150 → **200**, dùng chung cả nguyên-trang & figure.
- `figure_padding_pt`: padding cắt figure (mặc định nhỏ).
- `image_max_edge`: thay hằng `_IMG_MAX_EDGE=1200` (mặc định ~1800).
- `jpeg_quality`: thay hằng `_IMG_JPEG_QUALITY=80` (mặc định ~82).

## 6. Phạm vi

**Trong Spec 2:**
- `ImageBlock` mang hình học (bbox + source_dpi).
- Cropper dùng chung `image_render.py` (padding + clip + DPI + trim).
- CSS `max-height`/`object-fit` + `<img>` width/height.
- DPI mục tiêu 200, `image_max_edge` cấu hình (downscale-only), nén JPEG/PNG theo nội dung.
- Neo caption với figure (không hồi quy).
- Tăng `PIPELINE_VERSION` + ADR + cập nhật docs.

**Ngoài Spec 2:**
- Reading-order nhiều cột (**issue #18**).
- WebP / định dạng ngoài JPEG+PNG core EPUB.
- OCR nội dung bên trong ảnh.
- Đụng pipeline chữ (Spec 1) hay `Table.rows`.

## 7. Versioning & ADR

- Tăng `PIPELINE_VERSION` 12 → **13** (`sepia_pipeline/__init__.py`) + changelog (output ảnh đổi tất định).
- **ADR mới** trong `05-tech-decisions.md`: "Geometry-aware image rendering — re-crop figure từ PDF
  (padding + DPI) thay vì dùng ảnh Docling cắt sẵn"; lý do, knob, rủi ro kích thước content pack.
- Cập nhật `03-pdf-pipeline.md` mô tả bước ảnh mới.

## 8. Kiểm thử

- `tests/test_image_render.py` — cropper thuần: padding clip vào mép trang; DPI→px đúng; trim viền trắng;
  **không upscale**; tất định (cùng input → cùng bytes).
- `tests/test_build_epub.py` — `_process_image`: cap/downscale-only theo `image_max_edge`; chọn JPEG vs PNG
  theo số màu; bỏ `<64px`; CSS chứa `max-height`; `<img>` có width/height.
- `tests/test_model.py` (hoặc test hiện có) — `ImageBlock` field mới mặc định `None`, caller cũ không vỡ.
- Tích hợp (`tests/test_convert.py`/fixture) — PDF có figure → EPUB: ảnh đủ viền, cỡ hợp lệ, caption dính
  đúng hình, không hồi quy vị trí.
- `uv run ruff format --check .` **và** `ruff check` + `pytest` xanh; CI không chạy đường online.

## 9. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Padding kéo chữ lân cận vào hình (dính chữ) | Padding nhỏ, đối xứng; giữ ngưỡng text-in-picture; trim viền |
| DPI cao → content pack nặng (APK) | `image_max_edge` cap + JPEG q82; chỉ downscale, không upscale |
| `vh`/`object-fit` khác nhau giữa WebView/foliate-js | Rủi ro thấp (WebView hiện đại); soát trên máy lúc QA emulator |
| Đổi output phá tất định/CI | Cropper thuần PyMuPDF, tất định; chốt `PIPELINE_VERSION`=13 |
| Trim viền cắt nhầm nội dung sáng màu | Trim theo viền trắng đồng nhất + ngưỡng an toàn; có thể tắt qua flag |

## 10. Tệp ảnh hưởng

- **Thêm:** `sepia_pipeline/image_render.py`, `tests/test_image_render.py`.
- **Sửa:** `sepia_pipeline/model.py` (ImageBlock), `sepia_pipeline/docling_adapter.py` +
  `sepia_pipeline/ocr_hybrid.py` (dùng cropper, mang bbox/dpi), `sepia_pipeline/extract.py` /
  `sepia_pipeline/convert.py` (nguyên-trang dpi + geometry), `sepia_pipeline/build_epub.py`
  (CSS/cap/nén/img attrs), `sepia_pipeline/__init__.py` (`PIPELINE_VERSION`→13),
  `sepia_pipeline/__main__.py` (knob mới), `docs/03-pdf-pipeline.md`, `docs/05-tech-decisions.md` (ADR).

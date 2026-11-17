# Thiết kế — Bước sửa lỗi OCR (viết lại nguyên văn, offline)

> Trạng thái: ĐÃ DUYỆT thiết kế (2026-11-17). Kế tiếp: viết kế hoạch thực thi.
> Liên quan: [ADR-009](../../05-tech-decisions.md) (OCR Vision + cache), [SPIKE-5](../../spikes/spike-5-reocr-vision.md),
> [03-pdf-pipeline.md](../../03-pdf-pipeline.md), issue #20.

## 1. Mục tiêu & bối cảnh

Pipeline đã OCR lại sách scan bằng Apple Vision (ADR-009), giảm lỗi mạnh, nhưng SPIKE-5 cho thấy **vẫn
sót lỗi chính tả tiếng Việt** trong text OCR. Mục tiêu: thêm một **bước hậu xử lý tất định, offline hoàn
toàn** để **sửa nguyên văn** (chỉ sửa lỗi OCR, **không** tóm tắt, **không** đổi nội dung) trước khi dựng EPUB.

**Ràng buộc bắt buộc:**
- **Offline hoàn toàn** — không gọi dịch vụ/model online (nội dung sách không ra mạng; NFR-2, NFR-6).
- **Tất định** — chạy được CI Linux (không phụ thuộc macOS/Vision); không phá triết lý ADR-009.
- **Giữ nguyên văn tuyệt đối** — không bao giờ đổi một từ đang đúng; chỗ mơ hồ thì để nguyên.
- **Ít phụ thuộc, một người bảo trì** (NFR-4) — ưu tiên luật + bảng tĩnh, không thêm model nặng.

### Hai lớp lỗi (SPIKE-5)
1. **Vỡ cấu trúc âm tiết** — `phưdng→phương`, `nhiéu→nhiều`, ký tự rác `» ® _`. Token sai **không** còn
   là âm tiết Việt hợp lệ → **bắt được** bằng bảng nhầm + validator âm tiết. **← phạm vi v1.**
2. **Sai 1 dấu nhưng vẫn hợp lệ** — `phổi→phối`, `nằm→năm`. Cả hai đều là âm tiết hợp lệ → validator
   không thấy, cần **ngữ cảnh**. **← ngoài phạm vi v1** (xem §6).

## 2. Kiến trúc & điểm chèn

Module mới **`sepia_pipeline/ocr_rewrite.py`** — hàm thuần trên mô hình bất biến, theo đúng mẫu
`reflow.tidy_bullet_markers` / `drop_garbage_blocks`.

Hàm công khai:
```python
def fix_ocr_blocks(
    blocks: list[Block],
    table: ConfusionTable,
    config: RewriteConfig,
) -> tuple[list[Block], RewriteReport]
```

**Điểm chèn** (`convert.py`, trong `convert_pdf`): **ngay sau khi `blocks` được dựng** (sau nhánh if/else
chọn engine, quanh dòng ~206) và **trước `tidy_bullet_markers`** (dòng ~225).

**Gate** (như `drop_garbage_blocks`, `convert.py:224,229`): chỉ chạy khi
`is_ocr_source and looks_vietnamese(book_text)`. Sách born-digital Unicode **không bị đụng**.

Chỉ xử lý `.text` của `Heading` và `Paragraph`; trả block mới bằng `dataclasses.replace(b, text=...)`.
`ImageBlock`, `Table` giữ nguyên ở v1 (xem §6).

**Versioning:** tăng `PIPELINE_VERSION` 11→12 (`sepia_pipeline/__init__.py:48`) + ghi changelog theo quy
ước các dòng vXX. **Không** đụng `OcrCache` — đây là hậu xử lý tất định thuộc nhánh `convert`, không phải
tầng OCR engine; khoá phiên bản đúng chỗ là `PIPELINE_VERSION`.

## 3. Thuật toán sửa

### 3.1 Tách token
Tách text thành chuỗi xen kẽ **word-token** (dãy chữ cái tiếng Việt, có thể kèm `'`/`-` bên trong) và
**dải phân cách** (khoảng trắng + dấu câu). Ghép lại **bảo toàn** mọi phân cách (không đổi khoảng trắng,
xuống dòng, dấu câu). Chuẩn hoá NFC đã do `reflow.normalize_text` lo trước đó.

### 3.2 Quyết định mỗi word-token
```
nếu is_vietnamese_syllable(token.casefold()):      # đã đúng
    giữ nguyên
ngược lại:
    candidates = sinh_ung_vien(token)              # §3.3
    valid = { c ∈ candidates : is_vietnamese_syllable(c) và c != token }
    nếu len(valid) == 1:  thay bằng phần tử đó (khôi phục hoa/thường gốc)
    nếu len(valid) == 0:  giữ nguyên, ghi report "invalid-left"
    nếu len(valid)  > 1:  giữ nguyên, ghi report "ambiguous-left"
```
- Token < `min_token_len` (mặc định 2): bỏ qua (giữ nguyên).
- Khôi phục hoa/thường: nếu token gốc viết hoa chữ đầu / viết hoa toàn bộ, áp lại cho ứng viên.

### 3.3 Sinh ứng viên (có chặn bùng nổ)
1. **Bỏ ký tự rác trong từ**: loại bỏ các ký tự thuộc `garbage_chars` (`» ® _` …) lẫn trong token →
   một biến thể "đã rửa".
2. **Thay theo bảng nhầm**: với mỗi vị trí ký tự có trong `confusions`, phân nhánh sang các ký tự thay
   thế. Chặn bùng nổ: tối đa `max_substitutions` vị trí thay đồng thời (mặc định 2) và tổng
   `max_candidates` ứng viên (mặc định 64) — vượt thì dừng sinh (an toàn: token giữ nguyên).
- Tất định: duyệt vị trí trái→phải, thứ tự thay thế theo thứ tự khai báo trong bảng.

## 4. Dữ liệu "để học" (tài sản tri thức trong repo)

- **`sepia_pipeline/data/ocr_confusion.toml`** — đóng gói trong package (thêm vào `tool.setuptools`
  package-data nếu cần). Cấu trúc:
  ```toml
  # garbage_chars: ký tự rác loại khỏi trong token khi sinh ứng viên
  garbage_chars = ["»", "®", "_"]

  # [confusions]: ký tự OCR -> các ký tự thật nó có thể là (sinh ứng viên)
  [confusions]
  "d" = ["đ"]
  "é" = ["ề", "ế", "ệ"]
  "o" = ["ơ", "ô"]
  # ... seed từ bảng nhầm SPIKE-5
  ```
- **`sepia_pipeline/data/ocr_exceptions.toml`** — ghi đè & bảo vệ:
  ```toml
  # overrides: thay chính xác token (sau casefold) -> token đúng, ưu tiên hơn §3
  [overrides]
  "phuong" = "phương"   # ví dụ

  # protected: token (casefold) KHÔNG BAO GIỜ đụng, kể cả khi validator coi là rác
  protected = ["kcal", "mmhg"]
  ```
- **Vòng học**: mỗi lần convert xuất **`out/<book>/ocr_rewrite.json`** (report §5). Người/Claude soát →
  bồi thêm cặp nhầm / ngoại lệ vào 2 file trên → cuốn sau tốt hơn. Vẫn offline, tất định.

## 5. Report & cấu hình

```python
@dataclass(frozen=True)
class Correction:
    page: int
    before: str
    after: str
    rule: str          # "confusion" | "garbage" | "override"

@dataclass(frozen=True)
class RewriteReport:
    tokens_scanned: int
    corrected: int
    ambiguous_left: int
    invalid_left: int
    samples: tuple[Correction, ...]   # giới hạn số mẫu để nhẹ

@dataclass(frozen=True)
class RewriteConfig:
    enabled: bool = True
    min_token_len: int = 2
    max_substitutions: int = 2
    max_candidates: int = 64
    report_path: Path | None = None   # ghi ocr_rewrite.json nếu set
```
`convert` in tóm tắt ngắn (số token sửa / mơ hồ / bỏ) ra stdout như các bước khác; ghi file nếu
`report_path` được set.

## 6. Phạm vi

**Trong v1:**
- Lỗi vỡ cấu trúc âm tiết + ký tự rác trong từ, trên `Heading`/`Paragraph`.
- Thay thế an toàn khi **đúng một** ứng viên hợp lệ; `overrides`/`protected` từ file ngoại lệ.

**Ngoài v1 (ghi rõ limitation, để Hướng B/C sau):**
- Lỗi "sai 1 dấu vẫn hợp lệ" (`phổi→phối`) — cần mô hình ngôn ngữ/ngữ cảnh.
- **Chữ dính nhau** (`củangười`) — tách từ cần từ điển/segmentation; v1 không làm (sẽ bỏ qua an toàn).
- Text trong `Table.rows`.
- Đo CER/WER trong code (giữ triết lý `quality.py`: không ground-truth trong pipeline).

## 7. Kiểm thử

- **`tests/test_ocr_rewrite.py`** — hàm thuần, fixture dữ liệu nhỏ (bảng nhầm giả lập + thật):
  - `phưdng→phương`, `nhiéu→nhiều` (sửa đúng 1 ứng viên).
  - Token mơ hồ (≥2 ứng viên hợp lệ) → giữ nguyên + đếm `ambiguous_left`.
  - Từ đang đúng → không đụng.
  - Ký tự rác trong từ bị rửa; `overrides`/`protected` hoạt động.
  - Giữ hoa/thường; bảo toàn khoảng trắng/dấu câu; chặn bùng nổ (token nhiều ký tự nhầm → không treo).
- **`tests/test_convert.py`** — 1 case tích hợp: fixture `scan_ocr` (sinh bằng code trong `conftest.py`,
  không sách thật) có lỗi hệ thống → sau convert text đã sửa; sách born-digital **không** bị đụng.
- Chạy `ruff` + `pytest` xanh; cập nhật `test_cli`/version nếu in `PIPELINE_VERSION`.

## 8. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Sửa oan từ đúng (đổi nghĩa) | Chỉ đụng token **không** hợp lệ; mơ hồ → giữ nguyên; `protected` list |
| Bùng nổ tổ hợp ứng viên | `max_substitutions`/`max_candidates`; vượt ngưỡng → giữ nguyên |
| Bảng nhầm sai gây lỗi hệ thống | Report + vòng soát; test hồi quy cho từng cặp thêm vào |
| Phá tính tất định CI | Thuần Python, không gọi Vision/online; duyệt thứ tự cố định |
| Đụng sách born-digital | Gate `is_ocr_source and looks_vietnamese` |

## 9. Tệp ảnh hưởng (tóm tắt)

- **Thêm**: `sepia_pipeline/ocr_rewrite.py`, `sepia_pipeline/data/ocr_confusion.toml`,
  `sepia_pipeline/data/ocr_exceptions.toml`, `tests/test_ocr_rewrite.py`.
- **Sửa**: `sepia_pipeline/convert.py` (chèn bước + gate), `sepia_pipeline/__init__.py`
  (`PIPELINE_VERSION`→12 + changelog), `pyproject.toml` (package-data cho `data/*.toml` nếu cần),
  `tests/test_convert.py` (case tích hợp), `docs/03-pdf-pipeline.md` (mô tả bước mới).

# Thiết kế — Spec 1 (CHỮ): Ảnh trang là nguồn chân lý + sửa lỗi OCR

> Trạng thái: ĐÃ DUYỆT hướng (2026-11-18). Kế tiếp: viết kế hoạch thực thi.
> **Thay thế** bản "Hướng A (sửa luật)" trước đó — Hướng A nay là **Lớp 1** trong kiến trúc này.
> Liên quan: [ADR-009](../../05-tech-decisions.md) (OCR Vision + cache), [SPIKE-5](../../spikes/spike-5-reocr-vision.md),
> [03-pdf-pipeline.md](../../03-pdf-pipeline.md), issue #20. **Spec 2 (ẢNH)** tách riêng, làm sau.

## 1. Vấn đề & mục tiêu

PDF (nhất là sách scan có lớp chữ ẩn ABBYY) hay bị **"chèn"/lỗi ở lớp text** → trích thẳng lớp text cho
chữ **không chính xác**. SPIKE-5 chứng minh: **OCR lại từ ảnh trang** cho chữ đúng hơn rõ rệt. Mục tiêu
của Spec 1: **coi ảnh trang là nguồn chân lý** cho các sách mà lớp text không đáng tin, rồi **sửa lỗi
OCR mà không đổi nội dung** (viết lại nguyên văn, không tóm tắt), trước khi dựng EPUB.

**Ràng buộc (đã chốt với tác giả 2026-11-18):**
- App KMP **offline tuyệt đối** — không đổi (NFR-2/6 nói về *app*).
- Pipeline: **mặc định offline + tất định (chạy CI)**. Bước dùng model online là **opt-in, TẮT sẵn**.
- **Giữ nguyên văn** — không đổi từ đang đúng; chỗ mơ hồ giữ nguyên; lớp LLM có chốt chặn ảo giác.
- Ít phụ thuộc, một người bảo trì (NFR-4) — đường mặc định không kéo model nặng.

## 2. Kiến trúc 3 lớp

Nguồn chữ đi qua tối đa 3 lớp; mỗi lớp là hàm thuần trên `list[Block]` bất biến:

```
PDF ─(detect)─► [định tuyến nguồn chữ]
                   │
   ┌───────────────┴────────────────┐
   ▼ (born-digital sạch)            ▼ (scan / lớp text không đáng tin)
 lớp text PDF (như hiện tại)      Lớp 0: Vision OCR từ ảnh trang (ADR-009, cache)
   │                                 │
   └──────────────┬──────────────────┘
                  ▼
   Lớp 1: sửa luật (ocr_rewrite.py) — TẤT ĐỊNH, luôn bật cho nguồn OCR
                  ▼
   Lớp 2: LLM "chép lại" khối nghi ngờ — OPT-IN, tắt sẵn
                  ▼
            tidy_bullet_markers → drop_garbage → ... → build_epub
```

### 2.1 Lớp 0 — Vision OCR là nguồn chân lý (mở rộng trigger)
- Hiện Vision chỉ bật cho nhãn `scan_ocr`. Spec 1 **mở rộng**: ngoài `scan_ocr`, định tuyến sang Vision
  khi lớp text PDF **không đáng tin** — tiêu chí dựa trên `detect` + `vietnamese_score(book_text)` thấp
  / `garbage_ratio` cao hơn ngưỡng. Sách **born-digital Unicode sạch** vẫn **giữ lớp text PDF** (lớp đó
  mới là chân lý, OCR lại chỉ tệ hơn).
- Vision chạy offline (macOS), **cache** theo ADR-009 (khoá = SHA-256 PDF + engine + macOS/Vision ver).
  CI Linux đọc cache; miss → giữ nguyên hành vi hiện tại (cảnh báo, không chặn).
- **Không đổi** cấu trúc `OcrCache`; chỉ đổi điều kiện *khi nào* dùng Vision.

### 2.2 Lớp 1 — Sửa luật tất định (`ocr_rewrite.py`) — nguyên "Hướng A"
Module mới `sepia_pipeline/ocr_rewrite.py`, hàm thuần:
```python
def fix_ocr_blocks(blocks, table: ConfusionTable, config: RewriteConfig)
    -> tuple[list[Block], RewriteReport]
```
Chèn trong `convert.py` **sau khi dựng `list[Block]`, trước `tidy_bullet_markers`**; gate
`is_ocr_source and looks_vietnamese(book_text)`. Chỉ sửa `.text` của `Heading`/`Paragraph` qua
`dataclasses.replace`.

**Thuật toán (an toàn tuyệt đối):** với mỗi word-token
1. `is_vietnamese_syllable(token.casefold())` đã hợp lệ → **giữ nguyên**.
2. Không hợp lệ → sinh ứng viên: bỏ ký tự rác trong từ (`» ® _`…) + thay theo **bảng nhầm** (ế/ề→é,
   d→đ, o→{ơ,ô}…), chặn bùng nổ (≤`max_substitutions` vị trí, ≤`max_candidates`).
3. Lọc ứng viên thành âm tiết hợp lệ: **đúng 1** → thay (giữ hoa/thường); **0 hoặc >1** → giữ nguyên +
   ghi report.
→ Chỉ đụng token **đã sai**, chỉ khi **không mơ hồ** ⇒ rủi ro đổi nghĩa = 0.

Bảo toàn khoảng trắng/dấu câu/xuống dòng. Token `< min_token_len` bỏ qua.

### 2.3 Lớp 2 — LLM "chép lại" khối nghi ngờ (opt-in, tắt sẵn)
Bắt lớp lỗi mà Lớp 0+1 **không** sửa được: **sai 1 dấu vẫn hợp lệ** (`phổi→phối`), **chữ dính nhau**
(`củangười`) — cần đọc hiểu ngữ cảnh ("như người tự học đi chép").

- **Mặc định TẮT.** Bật bằng cờ `--llm-proofread` (+ extra tương ứng). Khi tắt: đường pipeline **không
  chạm mạng, tất định, chạy CI** như cũ.
- **Chọn khối gửi** (không gửi cả sách): khối `Heading`/`Paragraph` có `confidence < conf_threshold`
  (độ tin Vision, đã có ở `model.py`) **hoặc** `vietnamese_score(block.text) < vn_threshold`. Trang
  không nghi ngờ bỏ qua → nhanh + rẻ.
- **Đầu vào LLM**: crop ảnh vùng khối (hoặc ảnh trang) + text OCR hiện tại làm gợi ý. **Prompt**: *chép
  lại trung thực đúng những gì thấy trong ảnh, chỉ sửa lỗi OCR; KHÔNG tóm tắt, KHÔNG thêm/bớt ý, giữ
  nguyên thứ tự.* Đầu ra = text đã sửa.
- **Chốt chặn ảo giác (giữ nguyên văn)**: so text LLM với text OCR bằng tỷ lệ ký tự (Levenshtein/ratio).
  Nếu lệch quá `max_drift` (vd > 35%) → **bác**, giữ text OCR + gắn cờ `llm-rejected` trong report. Tránh
  LLM bịa/viết thêm.
- **Trừu tượng hoá nhà cung cấp** (`Proofreader` interface):
  - `NullProofreader` — mặc định, no-op (đường offline).
  - `ClaudeProofreader` — online (extra `llm-online`), gọi API vision. **Chỉ chạy khi có cờ**; log rõ
    trang nào gửi lên mạng.
  - (tương lai) `LocalVLMProofreader` — model local (Qwen2-VL/MiniCPM qua Ollama, extra `llm-local`) cho
    ai muốn 100% offline mà vẫn "đọc hiểu". Không làm ở v1.
- **Cache kết quả LLM** theo khoá `(hash(block.text) + hash(page_image_region) + model_id + prompt_ver)`
  → rerun ổn định; nhưng đây vẫn là đường **không chạy CI**.
- **Riêng tư**: chỉ gửi ảnh khi có cờ online tường minh; sách của chính tác giả, trên máy tác giả.

## 3. Dữ liệu "để học" (tài sản tri thức trong repo)
- `sepia_pipeline/data/ocr_confusion.toml` — `garbage_chars` + `[confusions]` ký tự→ứng viên (seed từ
  SPIKE-5). Đóng gói trong package.
- `sepia_pipeline/data/ocr_exceptions.toml` — `[overrides]` (wrong→right, ưu tiên trước §2.2) +
  `protected` (từ cấm đụng).
- Mỗi convert xuất `out/<book>/ocr_rewrite.json` (report §4) → người/Claude soát → bồi bảng nhầm/ngoại
  lệ. Vòng học offline, tất định.

## 4. Report & cấu hình
```python
@dataclass(frozen=True)
class Correction: page:int; before:str; after:str; rule:str  # confusion|garbage|override|llm

@dataclass(frozen=True)
class RewriteReport:
    tokens_scanned:int; corrected:int; ambiguous_left:int; invalid_left:int
    llm_blocks:int = 0; llm_rejected:int = 0
    samples: tuple[Correction, ...] = ()

@dataclass(frozen=True)
class RewriteConfig:
    enabled:bool=True; min_token_len:int=2; max_substitutions:int=2; max_candidates:int=64
    report_path: Path|None=None

@dataclass(frozen=True)
class ProofreadConfig:
    enabled:bool=False                 # --llm-proofread
    provider:str="null"                # null|claude|local
    conf_threshold:float=0.80          # độ tin Vision dưới ngưỡng → nghi ngờ (khởi đầu, tinh chỉnh)
    vn_threshold:float=0.90            # vietnamese_score dưới ngưỡng → nghi ngờ (khởi đầu, tinh chỉnh)
    max_drift:float=0.35               # lệch ký tự LLM-vs-OCR vượt mức → bác
    cache_dir: Path|None=None
```
`convert` in tóm tắt ngắn ra stdout (số token sửa / mơ hồ / khối LLM / LLM bị bác); ghi file nếu set.

## 5. Phạm vi
**Trong Spec 1:**
- Lớp 0: mở rộng trigger Vision (born-digital sạch giữ lớp text).
- Lớp 1: `ocr_rewrite.py` (sửa luật, tất định) + 2 file dữ liệu học.
- Lớp 2: khung `Proofreader` + `NullProofreader` + `ClaudeProofreader` (online, opt-in) + chốt chặn ảo
  giác + cache; chọn khối theo confidence/score.

**Ngoài Spec 1:**
- `LocalVLMProofreader` (model local) — để sau.
- Toàn bộ **Spec 2 (ẢNH)**: cắt/cỡ/nét/vị trí hình cho EPUB.
- Đo CER/WER trong code pipeline (giữ triết lý `quality.py`; đo ở spike nếu cần).
- Text trong `Table.rows`.

## 6. Versioning & ADR
- Tăng `PIPELINE_VERSION` 11→12 (`sepia_pipeline/__init__.py:48`) + changelog. (Đường mặc định đổi output
  do Lớp 0 trigger + Lớp 1.) Lớp 2 bật cờ không nằm trong version tất định.
- **ADR mới** (nháp trong 05-tech-decisions): "LLM proofread opt-in trong pipeline (mặc định offline)" —
  ghi rõ ranh giới app-offline vs pipeline-opt-in-online, lý do, cờ bật, rủi ro riêng tư.

## 7. Kiểm thử
- `tests/test_ocr_rewrite.py` — Lớp 1 thuần: `phưdng→phương`; mơ hồ giữ nguyên; từ đúng không đụng; bỏ
  rác; `overrides`/`protected`; giữ hoa/thường; chặn bùng nổ.
- `tests/test_convert.py` — tích hợp: fixture `scan_ocr` (sinh bằng code) có lỗi hệ thống → sau convert
  đã sửa; born-digital **không** bị đụng; định tuyến Vision theo ngưỡng.
- `tests/test_proofread.py` — Lớp 2 với `FakeProofreader` (không gọi mạng): chọn đúng khối nghi ngờ;
  chốt chặn ảo giác **bác** output lệch quá ngưỡng; `NullProofreader` = no-op; cache hoạt động.
- `ruff` + `pytest` xanh; CI **không** chạy đường online (mặc định tắt).

## 8. Rủi ro & giảm thiểu
| Rủi ro | Giảm thiểu |
|---|---|
| Lớp 1 sửa oan từ đúng | Chỉ đụng token không hợp lệ; mơ hồ → giữ; `protected` |
| LLM bịa/viết thêm (đổi nội dung) | Chốt chặn drift; chỉ chép lại; so với OCR; bác nếu lệch |
| Rò ảnh sách ra mạng ngoài ý | Mặc định TẮT; chỉ chạy khi có cờ online; log trang đã gửi |
| Phá tất định/CI | Lớp 0+1 thuần Python/cache; Lớp 2 tắt mặc định, không chạy CI |
| Vision OCR lại oan sách born-digital | Ngưỡng định tuyến; sách sạch giữ lớp text PDF |
| Phụ thuộc nặng | Online qua extra `llm-online`; local để sau; core không kéo model |

## 9. Tệp ảnh hưởng
- **Thêm**: `sepia_pipeline/ocr_rewrite.py`, `sepia_pipeline/proofread.py` (interface + Null + Claude),
  `sepia_pipeline/data/ocr_confusion.toml`, `sepia_pipeline/data/ocr_exceptions.toml`,
  `tests/test_ocr_rewrite.py`, `tests/test_proofread.py`.
- **Sửa**: `sepia_pipeline/convert.py` (định tuyến Vision mở rộng + chèn Lớp 1 + hook Lớp 2),
  `sepia_pipeline/__main__.py` (cờ `--llm-proofread`), `sepia_pipeline/__init__.py` (`PIPELINE_VERSION`→12),
  `pyproject.toml` (extra `llm-online`; package-data `data/*.toml`), `tests/test_convert.py`,
  `docs/05-tech-decisions.md` (ADR mới), `docs/03-pdf-pipeline.md` (mô tả 3 lớp).

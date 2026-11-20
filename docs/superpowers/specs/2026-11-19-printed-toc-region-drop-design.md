# Thiết kế — Bỏ vùng Mục lục in sẵn (neo theo mốc "MỤC LỤC")

> Trạng thái: ĐÃ DUYỆT hướng (2026-11-19). Kế tiếp: viết kế hoạch thực thi.
> Liên quan: issue #20 (clean-display), [ADR-011](../../05-tech-decisions.md), `drop_printed_toc` trong
> `sepia_pipeline/reflow.py`. Độc lập với Spec 2 (ẢNH, đã merge PR #35).

## 1. Vấn đề & mục tiêu

Trang **Mục lục in sẵn** của sách scan (ví dụ *Tự Học Đông Y*) render thành **văn bản lộn xộn** trong
EPUB: số trang đứng riêng (`46`/`48`/`50`/`58`), mục vỡ ("10. Bệnh tật là cuộc chiến…" không số cuối
dòng), dấu dẫn méo (`:..... 56`, `74 • •• • 8.`), và **tiêu đề chương lặp** ("Chương 1 / BƯỚC VÀO THẾ
GIỚI ĐÔNG Y") bị gán `Heading` → vừa bẩn nav vừa nhân đôi tên chương.

`drop_printed_toc` hiện có 3 cơ chế, tất cả dò theo **dấu dẫn (≥4 chấm/`…`/`__`) + số trang cuối dòng**.
Mục lục OCR-vỡ của sách này **không khớp** dạng đó nên lọt nguyên vùng vào nội dung.

**Mục tiêu:** bỏ **cả vùng mục lục in sẵn** một cách tất định, offline, an toàn — **không** đụng phần mở
đầu thật (LỜI NÓI ĐẦU…) hay thân bài thật ngay sau mục lục.

**Bối cảnh cấu trúc (đã khảo sát trên EPUB v13, `chap_0001.xhtml`):** cùng một "file chương" trộn
(a) bìa/front-matter rác, (b) **LỜI NÓI ĐẦU + 4 đoạn mở đầu — nội dung THẬT**, (c) **Mục lục in sẵn** bắt
đầu từ heading **"MỰC LỰC"** (OCR của "MỤC LỤC"), kéo dài qua các mục vỡ tới "…280 11. Đau thắt lưng…",
rồi (d) **thân bài THẬT** ("Mùa xuân là khoảng thời gian từ tiết Lập xuân…"). Mục lục **kẹp giữa** (b) và
(d).

## 2. Hướng: Cơ chế 4 — bỏ vùng neo theo mốc

Thêm **cơ chế thứ 4** vào `drop_printed_toc` (hàm thuần trên `list[Block]`, áp cả hai engine), **bổ sung**
3 cơ chế hiện có (không thay). Kích hoạt **chỉ khi** thấy mốc "MỤC LỤC" ⇒ sách không có mục lục in sẵn:
**0 thay đổi**.

### 2.1 Nhận mốc (chịu lỗi OCR) — `_is_toc_marker(block)`
`Heading`/`Paragraph` mà `text` sau khi **bỏ dấu + hoa hoá + gộp khoảng trắng** bằng `"MUC LUC"`, **và
ngắn** (số chữ cái ≤ `toc_marker_max_letters`, mặc định 10) để không trúng câu văn có cụm "mục lục".
- "MỤC LỤC" → "MUC LUC" ✓; "MỰC LỰC" → "MUC LUC" ✓ (bỏ dấu khử nhiễu dấu).
- "mục lục của chương này rất dài" → dài > ngưỡng → **false**.

### 2.2 Quét vùng
Với **mỗi** khối là mốc (chỉ số `m`): đánh dấu bỏ `m` và mọi khối sau nó cho tới **biên kết thúc** (§2.3).
Nhiều mốc trong sách → xử từng mốc.

### 2.3 Biên kết thúc = văn xuôi thật
Khối đầu tiên thoả **tất cả**:
- là `Paragraph`, **không** phải `_is_toc_entry_text`,
- độ dài không-trắng ≥ `toc_body_min_chars` (mặc định **60**),
- **không** là số-trang đứng riêng (`is_page_number_line`),
- có **chữ thường** (câu văn, không phải tiêu đề in hoa).
→ **dừng trước** khối này (giữ nó); vùng kết thúc. Mọi khối trong vùng bị bỏ (kể cả "Chương N"/tên chương
in hoa lặp, số đứng riêng).

### 2.4 Chốt an toàn
- Cap vùng ở `toc_region_max_blocks` (mặc định **60**): nếu quét hết cap mà **chưa** gặp biên → **không bỏ
  gì từ mốc này**, phát **cảnh báo** (`collect_warnings`) "nghi mục lục in sẵn không chốt được biên". Tránh
  ăn nhầm cả sách khi nhận diện sai.
- Phần **trước** mốc không bao giờ bị đụng (mở đầu thật an toàn).
- 3 cơ chế cũ giữ nguyên (vẫn bắt mục có dấu-dẫn ở nơi khác).

## 3. Cấu hình (`ReflowConfig`)

Thêm:
- `toc_marker_max_letters: int = 10`
- `toc_body_min_chars: int = 60`
- `toc_region_max_blocks: int = 60`

Mốc "MỤC LỤC" là **hằng** trong module (chuẩn hoá bỏ dấu == `"MUC LUC"`); lõi nhắm tiếng Việt.

## 4. Phạm vi

**Trong:** `_is_toc_marker` + cơ chế 4 (quét vùng + biên + cap) trong `drop_printed_toc`; 3 cấu hình mới;
cảnh báo khi không chốt được biên; tăng `PIPELINE_VERSION`.

**Ngoài:** dọn **trang bìa**/front-matter rác (BÙI HUY / tên sách) — vấn đề khác, để sau. Mục lục **không**
có mốc "MỤC LỤC" (dựa thuần dấu-dẫn) — 3 cơ chế cũ lo. Sửa chất lượng OCR chữ (Spec 1). Thứ tự đọc nhiều
cột (#18).

## 5. Versioning

- `PIPELINE_VERSION` 13 → **14** (`sepia_pipeline/__init__.py`) + changelog (output đổi cho sách có mục
  lục in sẵn kiểu vỡ).

## 6. Kiểm thử (`tests/test_reflow.py` hoặc file TOC hiện có)

- `_is_toc_marker`: "MỤC LỤC"/"MỰC LỰC"/"muc luc" → true; câu dài chứa "mục lục" → false; "MỤC LỤC CHƯƠNG
  TRÌNH ABC…" (dài) → false.
- Cơ chế 4 (thuần, dựng `list[Block]` tay): `[Para(mở đầu thật dài), Heading("MỤC LỤC"), Para("10. …"),
  Para("46"), Heading("Chương 1"), Heading("BƯỚC VÀO…"), Para("thân bài thật dài, chữ thường…")]`
  → giữ đoạn mở đầu + thân bài thật; bỏ mốc + mọi mục giữa; tiêu đề chương lặp bị bỏ.
- Không mốc → danh sách **nguyên vẹn**.
- Cap: mốc + 61 khối toc-ish không có biên → **không bỏ**, có cảnh báo.
- Biên: đoạn văn xuôi thật (≥60 ký tự, chữ thường, không số-trang) **kết thúc** vùng và **được giữ**.
- Tích hợp nhẹ (nếu rẻ): không phá các test `drop_printed_toc` cũ (3 cơ chế vẫn chạy).

## 7. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Nhận nhầm biên sớm (mục TOC là câu dài chữ thường) → sót đuôi mục lục | Mục TOC thường ngắn/có số; ngưỡng 60 ký tự + loại `_is_toc_entry_text`; 3 cơ chế cũ bắt phần sót |
| Vùng ăn lan nuốt nội dung thật | Cap `toc_region_max_blocks` + chỉ chạy **sau** mốc; không chốt biên → **không bỏ** + cảnh báo |
| Bỏ nhầm sách không có mục lục | Chỉ kích hoạt khi có mốc "MỤC LỤC" ngắn chuẩn hoá |
| Mốc "MỤC LỤC" OCR quá méo (vd "M∪C LUC") | Chuẩn hoá bỏ dấu bắt case phổ biến; ca cực đoan chấp nhận lọt (3 cơ chế cũ đỡ phần có dấu-dẫn) |

## 8. Tệp ảnh hưởng

- **Sửa:** `sepia_pipeline/reflow.py` (`_is_toc_marker` + cơ chế 4 trong `drop_printed_toc`; `ReflowConfig`
  3 trường; cảnh báo biên trong `collect_warnings` nếu tiện), `sepia_pipeline/__init__.py`
  (`PIPELINE_VERSION`→14 + changelog), `tests/` (test cơ chế 4), `docs/03-pdf-pipeline.md` /
  `docs/05-tech-decisions.md` (ghi chú cơ chế 4 — nối ADR-011).

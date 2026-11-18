# Spec 1 (CHỮ) — Kế hoạch thực thi: sửa lỗi OCR + ảnh trang là nguồn chân lý

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm bước hậu xử lý sửa lỗi OCR tiếng Việt vào pipeline (giữ nguyên văn), mở rộng OCR-từ-ảnh làm nguồn chân lý, và khung LLM "chép lại" opt-in — tất cả giữ đường mặc định offline + tất định.

**Architecture:** 3 lớp trên `list[Block]` bất biến trong `convert.convert_pdf`: Lớp 0 (Vision OCR, mở rộng trigger) → Lớp 1 (`ocr_rewrite.py`, sửa luật tất định) → Lớp 2 (`proofread.py`, LLM opt-in, tắt sẵn). Hàm thuần theo mẫu `reflow.tidy_bullet_markers`.

**Tech Stack:** Python 3.11 (tomllib, importlib.resources, dataclasses), pytest, ruff, uv. Spec: [docs/superpowers/specs/2026-11-18-text-reocr-rewrite-design.md](../specs/2026-11-18-text-reocr-rewrite-design.md).

## Global Constraints

- Mọi dataclass mới: `@dataclass(frozen=True)` (bất biến — [rules/python/coding-style]).
- Type annotation trên mọi chữ ký hàm. Comment/docstring tiếng Việt khớp codebase.
- Đường mặc định: **offline + tất định**, chạy CI Linux. Lớp 2 **mặc định TẮT**, không chạm mạng, **không** chạy ở CI.
- **Giữ nguyên văn**: chỉ sửa token đã sai; mơ hồ → giữ nguyên. Lớp 2 có chốt chặn drift.
- Gate OCR: chỉ chạy Lớp 1/2 khi `is_ocr_source and looks_vietnamese(book_text)`.
- `PIPELINE_VERSION`: 11 → **12** (`sepia_pipeline/__init__.py:48`) + 1 dòng changelog theo đúng quy ước vXX.
- Lệnh chạy từ thư mục `pdf-pipeline/`: test `uv run pytest ...`, lint `uv run ruff check .`.
- Commit nhỏ, thường xuyên; cuối commit thêm:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

- `sepia_pipeline/ocr_rewrite.py` — **Lớp 1**: `ConfusionTable`, `RewriteConfig`, `Correction`, `RewriteReport`, tokenizer, sinh ứng viên, `fix_token`, `fix_text`, `fix_ocr_blocks`.
- `sepia_pipeline/data/ocr_confusion.toml` — bảng nhầm + ký tự rác (đóng gói).
- `sepia_pipeline/data/ocr_exceptions.toml` — overrides + protected (đóng gói).
- `sepia_pipeline/proofread.py` — **Lớp 2**: `Proofreader` protocol, `NullProofreader`, `ClaudeProofreader`, `ProofreadConfig`, `select_suspicious_blocks`, `_within_drift`, `proofread_blocks`.
- `sepia_pipeline/convert.py` — chèn Lớp 0 trigger + Lớp 1 + hook Lớp 2.
- `sepia_pipeline/__main__.py` — cờ `--llm-proofread`, `--llm-provider`.
- `sepia_pipeline/__init__.py` — `PIPELINE_VERSION` → 12.
- `pyproject.toml` — package-data `data/*.toml`, extra `llm-online`.
- `tests/test_ocr_rewrite.py`, `tests/test_proofread.py`, sửa `tests/test_convert.py`.

---

# PHASE 1 — Lớp 1: sửa luật tất định (ưu tiên cao nhất)

## Task 1: Dữ liệu bảng nhầm + loader `ConfusionTable`

**Files:**
- Create: `sepia_pipeline/data/ocr_confusion.toml`
- Create: `sepia_pipeline/data/ocr_exceptions.toml`
- Create: `sepia_pipeline/ocr_rewrite.py`
- Test: `tests/test_ocr_rewrite.py`

**Interfaces:**
- Produces: `ConfusionTable` (frozen dataclass) với các trường `confusions: dict[str, tuple[str, ...]]`, `garbage_chars: frozenset[str]`, `overrides: dict[str, str]`, `protected: frozenset[str]`; classmethod `ConfusionTable.load(confusion_path: Path, exceptions_path: Path) -> ConfusionTable`; classmethod `ConfusionTable.default() -> ConfusionTable` (đọc 2 file đóng gói qua `importlib.resources`).

- [ ] **Step 1: Viết 2 file dữ liệu seed**

`sepia_pipeline/data/ocr_confusion.toml`:
```toml
# Ký tự rác loại khỏi token khi sinh ứng viên sửa (OCR đọc nhầm ký hiệu thành các dấu này).
garbage_chars = ["»", "®", "_", "¬", "~"]

# [confusions]: ký tự OCR -> danh sách ký tự THẬT nó có thể là. Hướng = (ký tự OCR đọc ra) -> (ký tự
# đúng), seed từ SPIKE-5 (vd ơ bị đọc thành "d": phương->phưdng; ề bị đọc thành "é": nhiều->nhiéu).
# Duyệt trái→phải, thử theo thứ tự khai báo (tất định).
#
# LƯU Ý THIẾT KẾ: validator chỉ biết CẤU TRÚC âm tiết, không biết dấu thanh nào đúng. Nếu một ký tự
# tone (vd "é") ánh xạ sang NHIỀU mục (ề/ế/ệ) thì mọi biến thể đều hợp lệ về cấu trúc → >1 ứng viên →
# "mơ hồ" → GIỮ NGUYÊN (không sửa). Vì vậy seed dùng MỘT mục tiêu trội (do curation theo sách). Lỗi
# tone còn lại thuộc Lớp 2. Ký tự ĐỔI CẤU TRÚC (vd "d"->"ơ") thường cho đúng 1 ứng viên hợp lệ → sửa được.
[confusions]
"d" = ["ơ"]
"é" = ["ề"]
"ó" = ["ố"]
"đ" = ["ớ"]
```

`sepia_pipeline/data/ocr_exceptions.toml`:
```toml
# [overrides]: token (sau casefold) -> token đúng. Ưu tiên TRƯỚC luật sinh ứng viên.
[overrides]

# protected: token (sau casefold) KHÔNG BAO GIỜ đụng, kể cả khi validator coi là rác.
protected = ["kcal", "mmhg", "vitamin"]
```

- [ ] **Step 2: Viết test thất bại cho loader**

`tests/test_ocr_rewrite.py`:
```python
from pathlib import Path

from sepia_pipeline.ocr_rewrite import ConfusionTable


def test_confusion_table_default_loads_bundled_data():
    table = ConfusionTable.default()
    assert "ơ" in table.confusions["d"]
    assert "»" in table.garbage_chars
    assert "kcal" in table.protected


def test_confusion_table_load_from_files(tmp_path: Path):
    conf = tmp_path / "c.toml"
    conf.write_text('garbage_chars = ["_"]\n[confusions]\n"d" = ["đ"]\n', encoding="utf-8")
    exc = tmp_path / "e.toml"
    exc.write_text('[overrides]\n"phuong" = "phương"\nprotected = ["dna"]\n', encoding="utf-8")
    table = ConfusionTable.load(conf, exc)
    assert table.confusions["d"] == ("đ",)
    assert table.overrides["phuong"] == "phương"
    assert "dna" in table.protected
    assert "_" in table.garbage_chars
```

- [ ] **Step 3: Chạy test — xác nhận FAIL**

Run: `uv run pytest tests/test_ocr_rewrite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sepia_pipeline.ocr_rewrite'`

- [ ] **Step 4: Viết module tối thiểu (loader)**

`sepia_pipeline/ocr_rewrite.py`:
```python
"""Lớp 1 — sửa lỗi OCR tiếng Việt bằng luật (tất định, offline). Xem docs/superpowers/specs.

Chỉ đụng token KHÔNG phải âm tiết Việt hợp lệ; chỉ thay khi có ĐÚNG MỘT ứng viên hợp lệ
(không mơ hồ) → giữ nguyên văn tuyệt đối. Hàm thuần trên ``list[Block]`` bất biến.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class ConfusionTable:
    confusions: dict[str, tuple[str, ...]]
    garbage_chars: frozenset[str]
    overrides: dict[str, str]
    protected: frozenset[str]

    @classmethod
    def load(cls, confusion_path: Path, exceptions_path: Path) -> ConfusionTable:
        conf = tomllib.loads(confusion_path.read_text(encoding="utf-8"))
        exc = tomllib.loads(exceptions_path.read_text(encoding="utf-8"))
        confusions = {k: tuple(v) for k, v in conf.get("confusions", {}).items()}
        return cls(
            confusions=confusions,
            garbage_chars=frozenset(conf.get("garbage_chars", [])),
            overrides={k.casefold(): v for k, v in exc.get("overrides", {}).items()},
            protected=frozenset(p.casefold() for p in exc.get("protected", [])),
        )

    @classmethod
    def default(cls) -> ConfusionTable:
        data = resources.files("sepia_pipeline") / "data"
        with resources.as_file(data / "ocr_confusion.toml") as cpath, resources.as_file(
            data / "ocr_exceptions.toml"
        ) as epath:
            return cls.load(cpath, epath)
```

- [ ] **Step 5: Chạy test — xác nhận PASS**

Run: `uv run pytest tests/test_ocr_rewrite.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add sepia_pipeline/ocr_rewrite.py sepia_pipeline/data/ tests/test_ocr_rewrite.py
git commit -m "feat(pipeline): ConfusionTable + dữ liệu seed sửa OCR (Lớp 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Tokenizer giữ nguyên phân cách + khôi phục hoa/thường

**Files:**
- Modify: `sepia_pipeline/ocr_rewrite.py`
- Test: `tests/test_ocr_rewrite.py`

**Interfaces:**
- Produces: `_tokenize(text: str) -> list[tuple[str, bool]]` (mỗi phần tử `(chuỗi, is_word)`; nối lại đúng `text` gốc); `_restore_case(candidate: str, original: str) -> str`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_ocr_rewrite.py`:
```python
from sepia_pipeline.ocr_rewrite import _restore_case, _tokenize


def test_tokenize_roundtrip_preserves_everything():
    text = "Phương  thuốc,\nnhiều đốt."
    parts = _tokenize(text)
    assert "".join(s for s, _ in parts) == text
    assert ("Phương", True) in parts
    assert any(not is_word and "," in s for s, is_word in parts)


def test_restore_case():
    assert _restore_case("phương", "phưdng") == "phương"
    assert _restore_case("phương", "Phưdng") == "Phương"
    assert _restore_case("phương", "PHƯDNG") == "PHƯƠNG"
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `uv run pytest tests/test_ocr_rewrite.py -k "tokenize or restore_case" -v`
Expected: FAIL — `cannot import name '_tokenize'`

- [ ] **Step 3: Thêm implementation**

Thêm vào `sepia_pipeline/ocr_rewrite.py`:
```python
import re

# Token "chữ": dãy ký tự chữ cái (Unicode) có thể kèm ' hoặc - bên trong. Mọi thứ khác là phân cách.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['\-][^\W\d_]+)*", re.UNICODE)


def _tokenize(text: str) -> list[tuple[str, bool]]:
    """Tách ``text`` thành chuỗi xen kẽ (token-chữ, True) và (phân-cách, False), nối lại = gốc."""
    parts: list[tuple[str, bool]] = []
    pos = 0
    for m in _WORD_RE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos : m.start()], False))
        parts.append((m.group(), True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], False))
    return parts


def _restore_case(candidate: str, original: str) -> str:
    """Áp kiểu hoa/thường của ``original`` lên ``candidate`` (toàn hoa / hoa chữ đầu / nguyên)."""
    if original.isupper():
        return candidate.upper()
    if original[:1].isupper():
        return candidate[:1].upper() + candidate[1:]
    return candidate
```

- [ ] **Step 4: Chạy test — PASS**

Run: `uv run pytest tests/test_ocr_rewrite.py -k "tokenize or restore_case" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sepia_pipeline/ocr_rewrite.py tests/test_ocr_rewrite.py
git commit -m "feat(pipeline): tokenizer giữ phân cách + khôi phục hoa/thường (Lớp 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Sinh ứng viên + `fix_token` (confusion + rửa rác, chặn bùng nổ)

**Files:**
- Modify: `sepia_pipeline/ocr_rewrite.py`
- Test: `tests/test_ocr_rewrite.py`

**Interfaces:**
- Consumes: `is_vietnamese_syllable` từ `sepia_pipeline.vietnamese`; `ConfusionTable`, `_restore_case`.
- Produces: `RewriteConfig` (frozen: `enabled=True`, `min_token_len=2`, `max_substitutions=2`, `max_candidates=64`, `report_path: Path|None=None`); `fix_token(token: str, table: ConfusionTable, config: RewriteConfig) -> tuple[str, str | None]` trả `(token_mới, rule)` với `rule ∈ {"confusion","garbage","override",None}` (None = không đổi).

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_ocr_rewrite.py`:
```python
import dataclasses

import pytest

from sepia_pipeline.ocr_rewrite import RewriteConfig, fix_token

TABLE = ConfusionTable.default()
CFG = RewriteConfig()


@pytest.mark.parametrize(
    "wrong, right",
    [("phưdng", "phương"), ("nhiéu", "nhiều")],
)
def test_fix_token_repairs_structure_breaking(wrong, right):
    out, rule = fix_token(wrong, TABLE, CFG)
    assert out == right
    assert rule == "confusion"


def test_fix_token_leaves_valid_word_untouched():
    out, rule = fix_token("phương", TABLE, CFG)
    assert out == "phương"
    assert rule is None


def test_fix_token_strips_in_word_garbage():
    out, rule = fix_token("nhiề»u", TABLE, CFG)
    assert out == "nhiều"
    assert rule in {"garbage", "confusion"}


def test_fix_token_no_valid_candidate_kept():
    # token không sinh được ứng viên hợp lệ nào (0 ứng viên) → giữ nguyên (an toàn).
    out, rule = fix_token("xqzw", TABLE, CFG)
    assert out == "xqzw"
    assert rule is None


def test_fix_token_multi_target_is_ambiguous_kept():
    # Nếu curation để một ký tự tone ánh xạ ĐA MỤC TIÊU, mọi biến thể hợp lệ cấu trúc → >1 ứng viên
    # → mơ hồ → giữ nguyên. Dựng bảng tạm để kiểm quy tắc an toàn (không phụ thuộc seed mặc định).
    multi = dataclasses.replace(ConfusionTable.default(), confusions={"é": ("ề", "ế", "ệ")})
    out, rule = fix_token("nhiéu", multi, CFG)
    assert out == "nhiéu"
    assert rule is None


def test_fix_token_short_token_skipped():
    out, rule = fix_token("đ", TABLE, CFG)
    assert out == "đ"
    assert rule is None
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `uv run pytest tests/test_ocr_rewrite.py -k fix_token -v`
Expected: FAIL — `cannot import name 'RewriteConfig'`

- [ ] **Step 3: Thêm implementation**

Thêm vào `sepia_pipeline/ocr_rewrite.py`:
```python
from .vietnamese import is_vietnamese_syllable


@dataclass(frozen=True)
class RewriteConfig:
    enabled: bool = True
    min_token_len: int = 2
    max_substitutions: int = 2
    max_candidates: int = 64
    report_path: Path | None = None


def _strip_garbage(token: str, garbage: frozenset[str]) -> str:
    return "".join(ch for ch in token if ch not in garbage)


def _gen_candidates(token: str, table: ConfusionTable, config: RewriteConfig) -> set[str]:
    """Sinh ứng viên (chữ thường) từ token thường: thay ≤max_substitutions vị trí theo bảng nhầm.

    BFS theo số vị trí đã thay; dừng khi vượt ``max_candidates`` (an toàn: trả những gì đã có).
    """
    base = token
    frontier: set[str] = {base}
    seen: set[str] = {base}
    for _depth in range(config.max_substitutions):
        nxt: set[str] = set()
        for cand in frontier:
            for i, ch in enumerate(cand):
                for repl in table.confusions.get(ch, ()):  # type: ignore[union-attr]
                    new = cand[:i] + repl + cand[i + 1 :]
                    if new not in seen:
                        seen.add(new)
                        nxt.add(new)
                        if len(seen) > config.max_candidates:
                            return seen
        frontier = nxt
    return seen


def fix_token(token: str, table: ConfusionTable, config: RewriteConfig) -> tuple[str, str | None]:
    """Trả (token_mới, rule). Chỉ sửa token KHÔNG hợp lệ & khi có ĐÚNG 1 ứng viên hợp lệ."""
    low = token.casefold()
    if low in table.protected:
        return token, None
    if low in table.overrides:
        return _restore_case(table.overrides[low], token), "override"
    if len(token) < config.min_token_len:
        return token, None
    if is_vietnamese_syllable(low):
        return token, None

    washed = _strip_garbage(low, table.garbage_chars)
    rule = "confusion"
    valid: set[str] = set()
    if washed != low and is_vietnamese_syllable(washed):
        valid.add(washed)
        rule = "garbage"
    for cand in _gen_candidates(washed, table, config):
        if cand != low and is_vietnamese_syllable(cand):
            valid.add(cand)

    if len(valid) == 1:
        return _restore_case(next(iter(valid)), token), rule
    return token, None  # 0 hoặc >1 (mơ hồ) → giữ nguyên
```

- [ ] **Step 4: Chạy test — PASS**

Run: `uv run pytest tests/test_ocr_rewrite.py -k fix_token -v`
Expected: PASS. Nếu một `confusion` seed làm token hợp lệ nào đó thành >1 ứng viên gây fail, tinh chỉnh `ocr_confusion.toml` (thu hẹp danh sách) — KHÔNG nới lỏng quy tắc "đúng 1".

- [ ] **Step 5: Commit**

```bash
git add sepia_pipeline/ocr_rewrite.py tests/test_ocr_rewrite.py
git commit -m "feat(pipeline): fix_token sinh ứng viên + chọn khi đúng-1 (Lớp 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `fix_text` + `fix_ocr_blocks` + report

**Files:**
- Modify: `sepia_pipeline/ocr_rewrite.py`
- Test: `tests/test_ocr_rewrite.py`

**Interfaces:**
- Consumes: `_tokenize`, `fix_token`, model `Heading`/`Paragraph`/`Block`.
- Produces: `Correction` (frozen: `page:int`, `before:str`, `after:str`, `rule:str`); `RewriteReport` (frozen: `tokens_scanned:int`, `corrected:int`, `ambiguous_left:int`, `invalid_left:int`, `llm_blocks:int=0`, `llm_rejected:int=0`, `samples:tuple[Correction,...]=()`); `fix_text(text:str, table, config, *, page:int=0) -> tuple[str, list[Correction]]`; `fix_ocr_blocks(blocks:list[Block], table, config) -> tuple[list[Block], RewriteReport]`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_ocr_rewrite.py`:
```python
import dataclasses

from sepia_pipeline.model import ImageBlock, Paragraph
from sepia_pipeline.ocr_rewrite import fix_ocr_blocks, fix_text


def test_fix_text_preserves_punctuation_and_fixes():
    out, corr = fix_text("Phưdng thuốc, nhiéu đốt.", TABLE, CFG)
    assert out == "Phương thuốc, nhiều đốt."
    assert {c.after for c in corr} == {"Phương", "nhiều"}


def test_fix_ocr_blocks_only_text_blocks_and_counts():
    blocks = [
        Paragraph(text="Phưdng thuốc", page=3),
        ImageBlock(png=b"x", page=3),
    ]
    out, report = fix_ocr_blocks(blocks, TABLE, CFG)
    assert out[0].text == "Phương thuốc"
    assert isinstance(out[1], ImageBlock)  # ảnh không bị đụng
    assert report.corrected == 1
    assert report.tokens_scanned >= 2


def test_fix_ocr_blocks_disabled_is_noop():
    blocks = [Paragraph(text="Phưdng", page=1)]
    out, _ = fix_ocr_blocks(blocks, TABLE, dataclasses.replace(CFG, enabled=False))
    assert out[0].text == "Phưdng"
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `uv run pytest tests/test_ocr_rewrite.py -k "fix_text or fix_ocr_blocks" -v`
Expected: FAIL — `cannot import name 'fix_text'`

- [ ] **Step 3: Thêm implementation**

Thêm vào `sepia_pipeline/ocr_rewrite.py`:
```python
import dataclasses as _dc

from .model import Block, Heading, Paragraph

_MAX_SAMPLES = 50


@dataclass(frozen=True)
class Correction:
    page: int
    before: str
    after: str
    rule: str


@dataclass(frozen=True)
class RewriteReport:
    tokens_scanned: int
    corrected: int
    ambiguous_left: int
    invalid_left: int
    llm_blocks: int = 0
    llm_rejected: int = 0
    samples: tuple[Correction, ...] = ()


def fix_text(
    text: str, table: ConfusionTable, config: RewriteConfig, *, page: int = 0
) -> tuple[str, list[Correction]]:
    pieces: list[str] = []
    corrections: list[Correction] = []
    for piece, is_word in _tokenize(text):
        if not is_word:
            pieces.append(piece)
            continue
        new, rule = fix_token(piece, table, config)
        pieces.append(new)
        if rule is not None and new != piece:
            corrections.append(Correction(page=page, before=piece, after=new, rule=rule))
    return "".join(pieces), corrections


def fix_ocr_blocks(
    blocks: list[Block], table: ConfusionTable, config: RewriteConfig
) -> tuple[list[Block], RewriteReport]:
    if not config.enabled:
        return list(blocks), RewriteReport(0, 0, 0, 0)
    out: list[Block] = []
    scanned = corrected = 0
    samples: list[Correction] = []
    for b in blocks:
        if isinstance(b, Heading | Paragraph):
            scanned += sum(1 for _, w in _tokenize(b.text) if w)
            new_text, corr = fix_text(b.text, table, config, page=b.page)
            corrected += len(corr)
            if len(samples) < _MAX_SAMPLES:
                samples.extend(corr[: _MAX_SAMPLES - len(samples)])
            out.append(_dc.replace(b, text=new_text) if corr else b)
        else:
            out.append(b)
    return out, RewriteReport(
        tokens_scanned=scanned,
        corrected=corrected,
        ambiguous_left=0,
        invalid_left=0,
        samples=tuple(samples),
    )
```

> Ghi chú: `ambiguous_left`/`invalid_left` để 0 ở v1 (đếm chi tiết là cải tiến sau, không chặn mục tiêu). Nếu muốn đếm ngay, mở rộng `fix_token` trả thêm lý do — ngoài phạm vi task này.

- [ ] **Step 4: Chạy test — PASS**

Run: `uv run pytest tests/test_ocr_rewrite.py -v`
Expected: PASS (toàn bộ file)

- [ ] **Step 5: Lint**

Run: `uv run ruff check sepia_pipeline/ocr_rewrite.py`
Expected: không lỗi (sửa nếu có).

- [ ] **Step 6: Commit**

```bash
git add sepia_pipeline/ocr_rewrite.py tests/test_ocr_rewrite.py
git commit -m "feat(pipeline): fix_text + fix_ocr_blocks + RewriteReport (Lớp 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Nối Lớp 1 vào `convert.py` + bump version + package-data

**Files:**
- Modify: `sepia_pipeline/convert.py:224-233` (chèn sau `tidy_bullet_markers`, trước `book_text`)
- Modify: `sepia_pipeline/__init__.py:48` (`PIPELINE_VERSION` → 12 + changelog)
- Modify: `pyproject.toml` (package-data `data/*.toml`)
- Test: `tests/test_convert.py`

**Interfaces:**
- Consumes: `fix_ocr_blocks`, `ConfusionTable`, `RewriteConfig` từ `ocr_rewrite`.

- [ ] **Step 1: Viết test tích hợp thất bại**

Thêm vào `tests/test_convert.py` (dùng fixture `scan_ocr`-style sẵn có; nếu cần token sai, chèn qua block — xem conftest). Test tối thiểu kiểm "convert không vỡ và sửa text qua hàm chung":
```python
from sepia_pipeline.model import Paragraph
from sepia_pipeline.ocr_rewrite import ConfusionTable, RewriteConfig, fix_ocr_blocks


def test_convert_layer1_fixes_blocks_via_shared_fn():
    blocks = [Paragraph(text="Phưdng thuốc nhiéu", page=1)]
    out, report = fix_ocr_blocks(blocks, ConfusionTable.default(), RewriteConfig())
    assert out[0].text == "Phương thuốc nhiều"
    assert report.corrected == 2
```
(Test tích hợp đầy-đủ qua `convert_pdf` phụ thuộc fixture OCR; giữ ở mức hàm chung + để bộ test `test_convert.py` hiện có xác nhận không hồi quy.)

- [ ] **Step 2: Chạy — FAIL**

Run: `uv run pytest tests/test_convert.py::test_convert_layer1_fixes_blocks_via_shared_fn -v`
Expected: FAIL (import lỗi nếu chưa có) hoặc PASS nếu Phase 1 trước đã xong — nếu PASS, vẫn tiếp tục wiring ở Step 3.

- [ ] **Step 3: Chèn vào `convert.py`**

Ngay sau khối (dòng ~225–226):
```python
    is_ocr_source = is_scan_ocr or engine_used == "docling"
    if is_ocr_source:
        blocks = tidy_bullet_markers(blocks)
```
thêm:
```python
    # Lớp 1 (Spec 1): sửa lỗi OCR tiếng Việt bằng luật — tất định, chỉ đụng token đã sai & không mơ
    # hồ (giữ nguyên văn). Cùng cổng is_ocr_source như tidy/garbage. Sửa TRƯỚC khi tính book_text/
    # lọc rác để điểm âm tiết cao hơn → giảm bỏ oan.
    rewrite_report = None
    if is_ocr_source:
        from .ocr_rewrite import ConfusionTable, RewriteConfig, fix_ocr_blocks

        blocks, rewrite_report = fix_ocr_blocks(
            blocks, ConfusionTable.default(), RewriteConfig()
        )
        if rewrite_report.corrected:
            warnings.append(f"ocr-rewrite: sửa {rewrite_report.corrected} token")
```

- [ ] **Step 4: Bump `PIPELINE_VERSION`**

Trong `sepia_pipeline/__init__.py`: đổi dòng 48 `PIPELINE_VERSION = 11` → `12`, và thêm ngay trên đó khối changelog:
```python
# v12: SỬA LỖI OCR tiếng Việt bằng luật (Lớp 1, Spec 1 CHỮ). Sau tidy_bullet_markers, trước lọc rác:
#      token KHÔNG phải âm tiết Việt hợp lệ → thử bảng nhầm (ocr_confusion.toml) + rửa ký tự rác; thay
#      khi có ĐÚNG 1 ứng viên hợp lệ (mơ hồ/0 → giữ nguyên). Gate is_ocr_source. → chữ thân bài đổi.
```

- [ ] **Step 5: Thêm package-data vào `pyproject.toml`**

Trong bảng cấu hình setuptools (cạnh khai báo package), đảm bảo gói kèm TOML:
```toml
[tool.setuptools.package-data]
sepia_pipeline = ["data/*.toml"]
```
(Nếu đã có `[tool.setuptools.package-data]`, thêm dòng `sepia_pipeline`; nếu dùng khai báo khác, bổ sung tương đương.)

- [ ] **Step 6: Chạy toàn bộ test — PASS, không hồi quy**

Run: `uv run pytest -q`
Expected: tất cả PASS. Nếu `test_cli`/bản in version so sánh `11`, cập nhật kỳ vọng sang `12`.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check .
git add sepia_pipeline/convert.py sepia_pipeline/__init__.py pyproject.toml tests/test_convert.py
git commit -m "feat(pipeline): nối Lớp 1 sửa OCR vào convert + PIPELINE_VERSION=12

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

# PHASE 2 — Lớp 0: mở rộng trigger Vision (ảnh trang là nguồn chân lý)

## Task 6: Định tuyến sang Vision khi lớp text PDF không đáng tin

**Files:**
- Modify: `sepia_pipeline/convert.py` (gần `_choose_engine` / chỗ tính `is_scan_ocr`)
- Test: `tests/test_engine_routing.py`

**Interfaces:**
- Consumes: `vietnamese_score`, `looks_vietnamese` từ `vietnamese`; `Document` model.
- Produces: `should_prefer_image_ocr(doc_model: Document, *, vn_floor: float = 0.75) -> bool`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_engine_routing.py`:
```python
from sepia_pipeline.convert import should_prefer_image_ocr
from sepia_pipeline.model import Document, Line, Page, TextSpan


def _doc(text: str) -> Document:
    span = TextSpan(text=text, font="X", size=10.0)
    line = Line(page=1, bbox=(0, 0, 100, 10), spans=(span,))
    page = Page(number=1, width=100, height=100, lines=(line,))
    return Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="s")


def test_prefer_image_ocr_when_vietnamese_but_low_score():
    # tiếng Việt thật nhưng lớp text hỏng dấu hệ thống → điểm âm tiết thấp
    assert should_prefer_image_ocr(_doc("phưdng thuóc nhiéu trưđc ngưài")) is True


def test_no_prefer_when_clean_vietnamese():
    assert should_prefer_image_ocr(_doc("phương thuốc nhiều trước người đông y")) is False


def test_no_prefer_when_not_vietnamese():
    assert should_prefer_image_ocr(_doc("the quick brown fox jumps over")) is False
```

- [ ] **Step 2: Chạy — FAIL**

Run: `uv run pytest tests/test_engine_routing.py -k prefer_image_ocr -v`
Expected: FAIL — `cannot import name 'should_prefer_image_ocr'`

- [ ] **Step 3: Implementation trong `convert.py`**

```python
from .vietnamese import vietnamese_score  # nếu chưa import


def should_prefer_image_ocr(doc_model: "Document", *, vn_floor: float = 0.75) -> bool:
    """True nếu lớp text PDF KHÔNG đáng tin cho sách tiếng Việt → nên OCR lại từ ảnh trang.

    Điều kiện: sách là tiếng Việt (``looks_vietnamese``) NHƯNG ``vietnamese_score`` thấp (lỗi dấu hệ
    thống của lớp chữ ẩn). Sách born-digital sạch có điểm cao → trả False (giữ lớp text PDF).
    """
    text = " ".join(
        s.text for p in doc_model.pages for ln in p.lines for s in ln.spans
    )
    if not looks_vietnamese(text):
        return False
    return vietnamese_score(text) < vn_floor
```

- [ ] **Step 4: Nối vào định tuyến engine**

Ở chỗ quyết định dùng Vision/hybrid: khi `ocr_cache_status == "present"` và `should_prefer_image_ocr(doc_model)` True thì đi route hybrid **dù** `is_scan_ocr` False. Cụ thể, mở rộng điều kiện route hybrid để OR thêm cờ này (giữ nguyên hành vi `scan_ocr`). Nếu không có cache Vision → giữ nguyên đường hiện tại + thêm 1 cảnh báo gợi ý chạy `sepia-pipeline ocr`.

- [ ] **Step 5: Chạy test — PASS + không hồi quy**

Run: `uv run pytest tests/test_engine_routing.py -v && uv run pytest -q`
Expected: PASS toàn bộ.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check .
git add sepia_pipeline/convert.py tests/test_engine_routing.py
git commit -m "feat(pipeline): mở rộng trigger Vision khi lớp text PDF không đáng tin (Lớp 0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

# PHASE 3 — Lớp 2: LLM "chép lại" opt-in (tắt sẵn, không chạy CI)

## Task 7: Khung `Proofreader` + chọn khối nghi ngờ + chốt chặn drift (không mạng)

**Files:**
- Create: `sepia_pipeline/proofread.py`
- Test: `tests/test_proofread.py`

**Interfaces:**
- Consumes: `Heading`/`Paragraph`/`Block`, `vietnamese_score`.
- Produces: `ProofreadConfig` (frozen: `enabled=False`, `provider="null"`, `conf_threshold=0.80`, `vn_threshold=0.90`, `max_drift=0.35`, `cache_dir: Path|None=None`); `Proofreader` Protocol (`transcribe(block_text: str, page_image: bytes | None) -> str`); `NullProofreader`; `select_suspicious_blocks(blocks, config) -> list[int]` (chỉ số khối nghi ngờ); `_within_drift(ocr: str, llm: str, max_drift: float) -> bool`; `proofread_blocks(blocks, reader, config) -> tuple[list[Block], int, int]` trả `(blocks_mới, n_llm, n_rejected)`.

- [ ] **Step 1: Viết test thất bại (dùng FakeProofreader, KHÔNG mạng)**

`tests/test_proofread.py`:
```python
import dataclasses

from sepia_pipeline.model import Heading, Paragraph
from sepia_pipeline.proofread import (
    NullProofreader,
    ProofreadConfig,
    _within_drift,
    proofread_blocks,
    select_suspicious_blocks,
)


class FakeProofreader:
    def __init__(self, mapping):
        self.mapping = mapping

    def transcribe(self, block_text, page_image):
        return self.mapping.get(block_text, block_text)


def test_select_suspicious_by_confidence():
    blocks = [
        Paragraph(text="chắc chắn", page=1, confidence=0.99),
        Paragraph(text="ngờ vực", page=1, confidence=0.40),
    ]
    idx = select_suspicious_blocks(blocks, ProofreadConfig(enabled=True))
    assert idx == [1]


def test_within_drift():
    assert _within_drift("phổi nằm", "phối nằm", 0.35) is True
    assert _within_drift("một dòng ngắn", "một đoạn dài bịa thêm rất nhiều chữ", 0.35) is False


def test_proofread_replaces_and_guards_hallucination():
    blocks = [Paragraph(text="phôi nàm", page=1, confidence=0.3)]
    reader = FakeProofreader({"phôi nàm": "phổi nằm"})
    cfg = ProofreadConfig(enabled=True, conf_threshold=0.8)
    out, n_llm, n_rej = proofread_blocks(blocks, reader, cfg)
    assert out[0].text == "phổi nằm"
    assert (n_llm, n_rej) == (1, 0)

    bad = FakeProofreader({"phôi nàm": "đây là văn bản bịa hoàn toàn khác dài dòng thêm thắt"})
    out2, _, n_rej2 = proofread_blocks(blocks, bad, cfg)
    assert out2[0].text == "phôi nàm"  # bị bác → giữ OCR
    assert n_rej2 == 1


def test_disabled_and_null_are_noop():
    blocks = [Paragraph(text="x", page=1, confidence=0.1)]
    out, n_llm, _ = proofread_blocks(blocks, NullProofreader(), ProofreadConfig(enabled=False))
    assert out[0].text == "x" and n_llm == 0
```

- [ ] **Step 2: Chạy — FAIL**

Run: `uv run pytest tests/test_proofread.py -v`
Expected: FAIL — `No module named 'sepia_pipeline.proofread'`

- [ ] **Step 3: Implementation**

`sepia_pipeline/proofread.py`:
```python
"""Lớp 2 — LLM "chép lại" khối OCR nghi ngờ. MẶC ĐỊNH TẮT, opt-in, không chạy CI.

Chỉ gửi khối điểm tin cậy thấp; chốt chặn ảo giác bằng drift ký tự để giữ nguyên văn.
"""

from __future__ import annotations

import dataclasses as _dc
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

from .model import Block, Heading, Paragraph
from .vietnamese import vietnamese_score


@dataclass(frozen=True)
class ProofreadConfig:
    enabled: bool = False
    provider: str = "null"
    conf_threshold: float = 0.80
    vn_threshold: float = 0.90
    max_drift: float = 0.35
    cache_dir: Path | None = None


class Proofreader(Protocol):
    def transcribe(self, block_text: str, page_image: bytes | None) -> str: ...


class NullProofreader:
    def transcribe(self, block_text: str, page_image: bytes | None) -> str:
        return block_text


def select_suspicious_blocks(blocks: list[Block], config: ProofreadConfig) -> list[int]:
    out: list[int] = []
    for i, b in enumerate(blocks):
        if not isinstance(b, Heading | Paragraph):
            continue
        conf = b.confidence
        low_conf = conf is not None and conf < config.conf_threshold
        low_vn = vietnamese_score(b.text) < config.vn_threshold
        if low_conf or low_vn:
            out.append(i)
    return out


def _within_drift(ocr: str, llm: str, max_drift: float) -> bool:
    """True nếu LLM đủ gần OCR (không bịa). drift = 1 - tỷ lệ giống; vượt max_drift → bác."""
    ratio = SequenceMatcher(None, ocr, llm).ratio()
    return (1.0 - ratio) <= max_drift


def proofread_blocks(
    blocks: list[Block], reader: Proofreader, config: ProofreadConfig
) -> tuple[list[Block], int, int]:
    if not config.enabled:
        return list(blocks), 0, 0
    suspicious = set(select_suspicious_blocks(blocks, config))
    out: list[Block] = []
    n_llm = n_rejected = 0
    for i, b in enumerate(blocks):
        if i not in suspicious or not isinstance(b, Heading | Paragraph):
            out.append(b)
            continue
        n_llm += 1
        new_text = reader.transcribe(b.text, None)
        if new_text != b.text and _within_drift(b.text, new_text, config.max_drift):
            out.append(_dc.replace(b, text=new_text))
        else:
            if new_text != b.text:
                n_rejected += 1
            out.append(b)
    return out, n_llm, n_rejected
```

- [ ] **Step 4: Chạy — PASS**

Run: `uv run pytest tests/test_proofread.py -v`
Expected: PASS

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check sepia_pipeline/proofread.py tests/test_proofread.py
git add sepia_pipeline/proofread.py tests/test_proofread.py
git commit -m "feat(pipeline): khung Proofreader + chọn khối + chốt chặn drift (Lớp 2, offline)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `ClaudeProofreader` (online, extra) + cờ CLI `--llm-proofread` + nối convert

**Files:**
- Modify: `sepia_pipeline/proofread.py` (thêm `ClaudeProofreader`, `make_proofreader`)
- Modify: `sepia_pipeline/__main__.py` (cờ convert)
- Modify: `sepia_pipeline/convert.py` (hook Lớp 2, mặc định tắt)
- Modify: `pyproject.toml` (extra `llm-online`)
- Test: `tests/test_proofread.py`

**Interfaces:**
- Produces: `make_proofreader(config: ProofreadConfig) -> Proofreader` (`"null"`→`NullProofreader`, `"claude"`→`ClaudeProofreader`); `ClaudeProofreader` dùng SDK `anthropic` (chỉ import khi khởi tạo).

- [ ] **Step 1: Viết test (chỉ factory + default-off; KHÔNG gọi mạng)**

Thêm vào `tests/test_proofread.py`:
```python
from sepia_pipeline.proofread import make_proofreader


def test_make_proofreader_null_default():
    reader = make_proofreader(ProofreadConfig())
    assert reader.transcribe("abc", None) == "abc"
```

- [ ] **Step 2: Chạy — FAIL**

Run: `uv run pytest tests/test_proofread.py -k make_proofreader -v`
Expected: FAIL — `cannot import name 'make_proofreader'`

- [ ] **Step 3: Thêm factory + ClaudeProofreader**

Thêm vào `sepia_pipeline/proofread.py`:
```python
_PROMPT = (
    "Bạn nhận một đoạn văn tiếng Việt do OCR tạo ra, có thể sai dấu hoặc dính chữ. "
    "Hãy CHÉP LẠI đúng nội dung: chỉ sửa lỗi OCR, KHÔNG tóm tắt, KHÔNG thêm/bớt ý, "
    "giữ nguyên thứ tự và dấu câu. Chỉ trả về văn bản đã sửa, không giải thích.\n\n"
)


class ClaudeProofreader:
    """Gọi API Claude để chép lại (ONLINE). Chỉ dùng khi tác giả bật cờ; gửi text lên mạng."""

    def __init__(self, model: str = "claude-opus-4-8") -> None:
        import anthropic  # chỉ import khi thực sự dùng (extra llm-online)

        self._client = anthropic.Anthropic()
        self._model = model

    def transcribe(self, block_text: str, page_image: bytes | None) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": _PROMPT + block_text}],
        )
        return "".join(part.text for part in msg.content if part.type == "text").strip()


def make_proofreader(config: ProofreadConfig) -> Proofreader:
    if config.provider == "claude":
        return ClaudeProofreader()
    return NullProofreader()
```

- [ ] **Step 4: Cờ CLI**

Trong `sepia_pipeline/__main__.py`, cạnh các `p_convert.add_argument(...)` (dòng ~186):
```python
    p_convert.add_argument(
        "--llm-proofread",
        action="store_true",
        help="Bật Lớp 2: LLM chép lại khối nghi ngờ (ONLINE, gửi text lên mạng, chậm)",
    )
    p_convert.add_argument(
        "--llm-provider", default="claude", help="Nhà cung cấp LLM (claude). Mặc định claude"
    )
```
Và trong `_cmd_convert`, truyền xuống `convert_pdf(...)`:
```python
        llm_proofread=args.llm_proofread,
        llm_provider=args.llm_provider,
```

- [ ] **Step 5: Hook vào `convert_pdf`**

Thêm tham số `convert_pdf(..., llm_proofread: bool = False, llm_provider: str = "claude")`. Sau Lớp 1 (sau khi lọc rác/toc, trước `build_epub`), chèn:
```python
    if llm_proofread and is_ocr_source:
        from .proofread import ProofreadConfig, make_proofreader, proofread_blocks

        pcfg = ProofreadConfig(enabled=True, provider=llm_provider)
        blocks, n_llm, n_rej = proofread_blocks(blocks, make_proofreader(pcfg), pcfg)
        warnings.append(f"llm-proofread: {n_llm} khối qua LLM, {n_rej} bị bác (drift)")
```

- [ ] **Step 6: Extra trong `pyproject.toml`**

Trong `[project.optional-dependencies]`:
```toml
llm-online = ["anthropic>=0.40"]
```

- [ ] **Step 7: Chạy test + không hồi quy (đường mặc định TẮT)**

Run: `uv run pytest -q`
Expected: PASS toàn bộ. CI không bật cờ → Lớp 2 không chạy, không cần `anthropic`.

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff check .
git add sepia_pipeline/proofread.py sepia_pipeline/__main__.py sepia_pipeline/convert.py pyproject.toml tests/test_proofread.py
git commit -m "feat(pipeline): ClaudeProofreader + cờ --llm-proofread (Lớp 2, opt-in online)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

# PHASE 4 — Tài liệu & ADR

## Task 9: ADR mới + cập nhật docs/03

**Files:**
- Modify: `docs/05-tech-decisions.md` (ADR mới)
- Modify: `docs/03-pdf-pipeline.md` (mô tả 3 lớp)

- [ ] **Step 1: Thêm ADR**

Trong `docs/05-tech-decisions.md`, thêm ADR (đánh số tiếp theo, vd ADR-011):
```markdown
### ADR-011 — LLM proofread opt-in trong pipeline (mặc định offline)
Pipeline chạy trên máy tác giả, tách rời app (AGPL). Sửa lỗi OCR theo 3 lớp: Vision OCR + luật
(offline, tất định, mặc định) và một lớp LLM "chép lại" khối nghi ngờ **mặc định TẮT**. App KMP vẫn
offline tuyệt đối (NFR-2/6). Bật lớp LLM bằng `--llm-proofread` (online, gửi text/ảnh lên mạng — sách
của chính tác giả); có chốt chặn drift chống ảo giác. Lý do: lỗi "sai 1 dấu vẫn hợp lệ" + chữ dính nhau
cần đọc hiểu ngữ cảnh. Rủi ro riêng tư: chỉ khi bật cờ, log trang đã gửi.
```

- [ ] **Step 2: Cập nhật `docs/03-pdf-pipeline.md`**

Trong phần kiến trúc pipeline (§2 hoặc §8), thêm mô tả bước "sửa lỗi OCR 3 lớp" chèn sau dựng blocks, trước lọc rác; nêu rõ Lớp 2 mặc định tắt.

- [ ] **Step 3: Commit**

```bash
git add docs/05-tech-decisions.md docs/03-pdf-pipeline.md
git commit -m "docs: ADR-011 LLM proofread opt-in + mô tả sửa OCR 3 lớp

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Hoàn tất

- [ ] Chạy toàn bộ: `uv run ruff check . && uv run pytest -q` → xanh.
- [ ] Tạo PR `feat/ocr-rewrite` → `master` (CI: pipeline + app phải pass).

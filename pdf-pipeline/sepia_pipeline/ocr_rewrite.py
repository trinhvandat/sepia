"""Lớp 1 — sửa lỗi OCR tiếng Việt bằng luật (tất định, offline). Xem docs/superpowers/specs.

Chỉ đụng token KHÔNG phải âm tiết Việt hợp lệ; chỉ thay khi có ĐÚNG MỘT ứng viên hợp lệ
(không mơ hồ) → giữ nguyên văn tuyệt đối. Hàm thuần trên ``list[Block]`` bất biến.
"""

from __future__ import annotations

import dataclasses as _dc
import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .model import Block, Heading, Paragraph
from .vietnamese import is_vietnamese_syllable


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
        overrides_dict = exc.get("overrides", {})
        protected_list = overrides_dict.get("protected", [])
        overrides = {
            k.casefold(): v
            for k, v in overrides_dict.items()
            if k != "protected"
        }
        return cls(
            confusions=confusions,
            garbage_chars=frozenset(conf.get("garbage_chars", [])),
            overrides=overrides,
            protected=frozenset(p.casefold() for p in protected_list),
        )

    @classmethod
    def default(cls) -> ConfusionTable:
        data = resources.files("sepia_pipeline") / "data"
        with resources.as_file(data / "ocr_confusion.toml") as cpath, resources.as_file(
            data / "ocr_exceptions.toml"
        ) as epath:
            return cls.load(cpath, epath)


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


@dataclass(frozen=True)
class RewriteConfig:
    """Cấu hình sửa lỗi OCR (token-level)."""

    enabled: bool = True
    min_token_len: int = 2
    max_substitutions: int = 2
    max_candidates: int = 64
    report_path: Path | None = None


def _strip_garbage(token: str, garbage: frozenset[str]) -> str:
    """Loại bỏ ký tự rác trong token."""
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
                for repl in table.confusions.get(ch, ()):
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
    if washed != low and is_vietnamese_syllable(washed):
        return _restore_case(washed, token), "garbage"

    valid: set[str] = set()
    for cand in _gen_candidates(washed, table, config):
        if cand != low and is_vietnamese_syllable(cand):
            valid.add(cand)

    if len(valid) == 1:
        return _restore_case(next(iter(valid)), token), "confusion"
    return token, None  # 0 hoặc >1 (mơ hồ) → giữ nguyên


_MAX_SAMPLES = 50


@dataclass(frozen=True)
class Correction:
    """Một lần sửa token đơn trong văn bản."""

    page: int
    before: str
    after: str
    rule: str


@dataclass(frozen=True)
class RewriteReport:
    """Báo cáo thống kê sửa lỗi OCR toàn bộ danh sách block."""

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
    """Sửa một đoạn text, trả (text_mới, danh_sách_sửa).

    Mỗi token hợp lệ được xử lý qua fix_token; phân cách (dấu, khoảng trắng) giữ nguyên.
    """
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
    """Sửa danh sách block (Heading/Paragraph), không đụng ImageBlock/Table.

    Trả (blocks_mới, báo_cáo).
    """
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

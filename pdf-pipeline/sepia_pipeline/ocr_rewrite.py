"""Lớp 1 — sửa lỗi OCR tiếng Việt bằng luật (tất định, offline). Xem docs/superpowers/specs.

Chỉ đụng token KHÔNG phải âm tiết Việt hợp lệ; chỉ thay khi có ĐÚNG MỘT ứng viên hợp lệ
(không mơ hồ) → giữ nguyên văn tuyệt đối. Hàm thuần trên ``list[Block]`` bất biến.
"""

from __future__ import annotations

import re
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

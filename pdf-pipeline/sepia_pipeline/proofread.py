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

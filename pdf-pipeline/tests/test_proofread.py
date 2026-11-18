from sepia_pipeline.model import Paragraph
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

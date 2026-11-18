import dataclasses
from pathlib import Path

import pytest

from sepia_pipeline.ocr_rewrite import (
    ConfusionTable,
    RewriteConfig,
    _restore_case,
    _tokenize,
    fix_token,
)


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


def test_fix_token_garbage_short_circuits_before_confusion():
    # Regression: garbage stripping must win before confusion search runs.
    # Token: "nhiề»u" (» is garbage; stripped → "nhiều" is valid)
    # Create a ConfusionTable where the stripped form ALSO has a character
    # that confusion could map to another valid syllable (e.g., "ề" → "ế").
    # With the bug: both "nhiều" (from garbage) and "nhiếu" (from confusion)
    # would be in valid set → ambiguous → kept unfixed.
    # With the fix: garbage short-circuits → returns "nhiều" with rule="garbage".
    hybrid_table = dataclasses.replace(
        ConfusionTable.default(),
        confusions={"»": (), "ề": ("ế",)},  # » is garbage (empty target), ề→ế for confusion
        garbage_chars=frozenset({"»"}),
    )
    out, rule = fix_token("nhiề»u", hybrid_table, CFG)
    assert out == "nhiều"
    assert rule == "garbage"  # Must be "garbage", not None (ambiguous)

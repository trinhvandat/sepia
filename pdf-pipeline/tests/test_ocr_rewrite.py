from pathlib import Path

from sepia_pipeline.ocr_rewrite import ConfusionTable, _restore_case, _tokenize


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

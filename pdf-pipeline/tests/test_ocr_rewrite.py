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

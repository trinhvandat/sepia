"""Spec 2: default DPI ảnh = 200, có figure_padding_pt; PIPELINE_VERSION = 13."""

from __future__ import annotations

from sepia_pipeline import PIPELINE_VERSION
from sepia_pipeline.convert import ConvertConfig


def test_image_dpi_default_200() -> None:
    assert ConvertConfig().image_dpi == 200


def test_figure_padding_default() -> None:
    assert ConvertConfig().figure_padding_pt == 4.0


def test_pipeline_version_bumped() -> None:
    assert PIPELINE_VERSION == 13

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from panel_compiler import compiler
from panel_compiler.renderers import RenderedFigure


def _panel(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect id="fig" x="0" y="0" width="80" height="60"/>'
        "</svg>"
    )


def test_rendered_file_cleanup_runs_after_embedding(
    tmp_path: Path, monkeypatch
) -> None:
    _panel(tmp_path / "panel.svg")
    (tmp_path / "figure.pdf").write_text("%PDF-1.4\n")
    tempdir = tmp_path / "rendered"
    tempdir.mkdir()
    svg = tempdir / "out.svg"
    svg.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 60">'
        '<rect x="0" y="0" width="80" height="60"/>'
        "</svg>"
    )

    monkeypatch.setattr(
        compiler,
        "render_file_to_svg",
        lambda source_path: RenderedFigure(svg, tempdir),
    )

    tree = compiler._compile_tree(
        {"panel": "panel.svg", "fig": "figure.pdf"},
        tmp_path / "pc.yaml",
    )

    assert tree is not None
    assert not tempdir.exists()


def test_rendered_file_cleanup_runs_when_embedding_fails(
    tmp_path: Path, monkeypatch
) -> None:
    _panel(tmp_path / "panel.svg")
    (tmp_path / "figure.pdf").write_text("%PDF-1.4\n")
    tempdir = tmp_path / "rendered"
    tempdir.mkdir()
    svg = tempdir / "out.svg"
    svg.write_text("not svg")

    monkeypatch.setattr(
        compiler,
        "render_file_to_svg",
        lambda source_path: RenderedFigure(svg, tempdir),
    )

    with pytest.raises(ET.ParseError):
        compiler._compile_tree(
            {"panel": "panel.svg", "fig": "figure.pdf"},
            tmp_path / "pc.yaml",
        )

    assert not tempdir.exists()

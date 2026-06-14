from pathlib import Path

import pc
from panel_compiler import renderers
from panel_compiler.renderers import RenderedFigure


def test_pc_exports_core_api() -> None:
    assert pc.SVGDimensions is not None
    assert pc.compile_panel is not None
    assert pc._compile_tree is not None


def test_pc_pdf_to_svg_preserves_legacy_path_return(
    tmp_path: Path, monkeypatch
) -> None:
    svg_path = tmp_path / "out.svg"

    monkeypatch.setattr(
        renderers,
        "pdf_to_svg",
        lambda pdf_path: RenderedFigure(svg_path),
    )

    assert pc.pdf_to_svg(tmp_path / "figure.pdf") == svg_path

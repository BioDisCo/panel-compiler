import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from panel_compiler import compiler
from panel_compiler.compiler import _compile_tree

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


def _make_panel(path: Path, width: int = 200, height: int = 100) -> None:
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{INKSCAPE_NS}"'
        f' width="400" height="300" viewBox="0 0 400 300">'
        f'<g inkscape:label="plot" width="{width}" height="{height}"/>'
        f"</svg>"
    )


def _make_figure(path: Path, width: int = 200, height: int = 100) -> None:
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect id="bg" x="0" y="0" width="{width}" height="{height}"/>'
        f"</svg>"
    )


def test_missing_panel_key_logs_and_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("ERROR", logger="pc"):
        tree = _compile_tree({}, tmp_path / "pc.yaml")

    assert tree is None
    assert "Config missing required 'panel' key" in caplog.text


def test_missing_panel_file_logs_and_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("ERROR", logger="pc"):
        tree = _compile_tree({"panel": "missing.svg"}, tmp_path / "pc.yaml")

    assert tree is None
    assert "Panel file not found" in caplog.text


def test_neither_file_nor_tex_specified_skips_group(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _make_panel(tmp_path / "panel.svg")

    with caplog.at_level("WARNING", logger="pc"):
        tree = _compile_tree({"panel": "panel.svg", "plot": {}}, tmp_path / "pc.yaml")

    assert tree is not None
    assert "No SVG file or LaTeX text specified for plot" in caplog.text
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert len(list(group)) == 0


def test_missing_figure_file_skips_group(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _make_panel(tmp_path / "panel.svg")

    with caplog.at_level("WARNING", logger="pc"):
        tree = _compile_tree(
            {"panel": "panel.svg", "plot": "missing.svg"}, tmp_path / "pc.yaml"
        )

    assert tree is not None
    assert "File not found" in caplog.text
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert len(list(group)) == 0


def test_unsupported_figure_type_skips_group(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _make_panel(tmp_path / "panel.svg")
    (tmp_path / "figure.gif").write_bytes(b"GIF89a")

    with caplog.at_level("WARNING", logger="pc"):
        tree = _compile_tree(
            {"panel": "panel.svg", "plot": "figure.gif"}, tmp_path / "pc.yaml"
        )

    assert tree is not None
    assert "Failed to render file for plot" in caplog.text
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert len(list(group)) == 0


def test_latex_render_failure_skips_group(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    _make_panel(tmp_path / "panel.svg")
    monkeypatch.setattr(compiler, "render_latex_to_svg", lambda tex_text: [])

    with caplog.at_level("WARNING", logger="pc"):
        tree = _compile_tree(
            {"panel": "panel.svg", "plot": {"tex": r"\sin(x)"}}, tmp_path / "pc.yaml"
        )

    assert tree is not None
    assert "Failed to render LaTeX for plot" in caplog.text
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert len(list(group)) == 0


def test_invalid_fontsize_falls_back_to_default(tmp_path: Path, monkeypatch) -> None:
    """A non-numeric `size` must not crash -- it silently falls back to 10pt."""
    _make_panel(tmp_path / "panel.svg")
    monkeypatch.setattr(
        compiler,
        "render_latex_to_svg",
        lambda tex_text: [ET.fromstring('<path d="M 0 0"/>')],
    )

    tree = _compile_tree(
        {"panel": "panel.svg", "plot": {"tex": "x", "size": "not-a-size"}},
        tmp_path / "pc.yaml",
    )

    assert tree is not None
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    wrapper = list(group)[0]
    assert wrapper.get("transform") == f"scale({10.0 / 12.0})"


def test_group_dimensions_take_priority_over_config_fallback(tmp_path: Path) -> None:
    """Explicit placeholder dimensions take priority over the config fallback."""
    _make_panel(tmp_path / "panel.svg", width=200, height=100)
    _make_figure(tmp_path / "fig.svg", width=400, height=100)

    tree = _compile_tree(
        {
            "panel": "panel.svg",
            "plot": {"file": "fig.svg", "fit": "width", "width": 800, "height": 100},
        },
        tmp_path / "pc.yaml",
    )

    assert tree is not None
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    wrapper = list(group)[0]
    assert wrapper.get("transform") == "scale(0.5)"


def test_group_without_dimensions_embeds_unscaled(tmp_path: Path) -> None:
    (tmp_path / "panel.svg").write_text(
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{INKSCAPE_NS}"'
        f' width="400" height="300" viewBox="0 0 400 300">'
        f'<g inkscape:label="plot"/>'
        f"</svg>"
    )
    _make_figure(tmp_path / "fig.svg", width=200, height=100)

    tree = _compile_tree(
        {"panel": "panel.svg", "plot": "fig.svg"}, tmp_path / "pc.yaml"
    )

    assert tree is not None
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    wrapper = list(group)[0]
    assert wrapper.get("transform") is None


@pytest.mark.parametrize("size", [24, 24.0, "24", "24pt"])
def test_numeric_and_string_font_sizes_agree(tmp_path: Path, monkeypatch, size) -> None:
    _make_panel(tmp_path / "panel.svg")
    monkeypatch.setattr(
        compiler,
        "render_latex_to_svg",
        lambda text: [ET.fromstring('<path d="M 0 0"/>')],
    )
    tree = _compile_tree(
        {"panel": "panel.svg", "plot": {"tex": "x", "size": size}},
        tmp_path / "pc.yaml",
    )
    assert tree is not None
    group = tree.getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert group[0].get("transform") == "scale(2.0)"

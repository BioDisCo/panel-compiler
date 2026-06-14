import xml.etree.ElementTree as ET
from pathlib import Path
from subprocess import CompletedProcess

from panel_compiler import config as config_module
from panel_compiler import renderers
from panel_compiler.compiler import _compile_one
from panel_compiler.config import compile_panel

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


def _make_panel(
    path: Path, label: str = "plot", width: int = 200, height: int = 100
) -> None:
    path.write_text(
        f"<?xml version='1.0' encoding='utf-8'?>"
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{INKSCAPE_NS}"'
        f' width="400" height="300" viewBox="0 0 400 300">'
        f'<g inkscape:label="{label}" width="{width}" height="{height}"/>'
        f"</svg>"
    )


def _make_figure(path: Path, width: int = 200, height: int = 100) -> None:
    path.write_text(
        f"<?xml version='1.0' encoding='utf-8'?>"
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect id="bg" x="0" y="0" width="{width}" height="{height}" fill="blue"/>'
        f"</svg>"
    )


def test_compile_svg_figure(tmp_path: Path) -> None:
    _make_panel(tmp_path / "panel.svg")
    _make_figure(tmp_path / "fig.svg")
    output = tmp_path / "out.svg"

    _compile_one(
        {"panel": "panel.svg", "plot": {"file": "fig.svg", "fit": "contain"}},
        tmp_path / "pc.yaml",
        output,
    )

    assert output.exists()
    group = ET.parse(output).getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert len(list(group)) > 0


def test_compile_shorthand_string(tmp_path: Path) -> None:
    _make_panel(tmp_path / "panel.svg")
    _make_figure(tmp_path / "fig.svg")
    output = tmp_path / "out.svg"

    _compile_one(
        {"panel": "panel.svg", "plot": "fig.svg"}, tmp_path / "pc.yaml", output
    )

    assert output.exists()


def test_compile_tex_file_figure(tmp_path: Path, monkeypatch) -> None:
    _make_panel(tmp_path / "panel.svg", width=200, height=100)
    (tmp_path / "figure.tex").write_text(
        "\\documentclass[tikz,border=2pt]{standalone}\n"
        "\\usepackage{tikz}\n"
        "\\begin{document}\n"
        "\\begin{tikzpicture}\\draw (0,0) rectangle (2,1);\\end{tikzpicture}\n"
        "\\end{document}\n"
    )
    output = tmp_path / "out.svg"

    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "pdflatex":
            output_dir = Path(cmd[cmd.index("-output-directory") + 1])
            jobname = cmd[cmd.index("-jobname") + 1]
            (output_dir / f"{jobname}.pdf").write_text("%PDF-1.4\n")
        elif cmd[0] == "pdf2svg":
            svg_file = Path(cmd[2])
            svg_file.write_text(
                "<?xml version='1.0' encoding='utf-8'?>"
                '<svg xmlns="http://www.w3.org/2000/svg"'
                ' width="400" height="100" viewBox="0 0 400 100">'
                '<rect id="tikz-box" x="0" y="0" width="400" height="100"/>'
                "</svg>"
            )
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    _compile_one(
        {"panel": "panel.svg", "plot": {"file": "figure.tex", "fit": "width"}},
        tmp_path / "pc.yaml",
        output,
    )

    group = ET.parse(output).getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert calls == ["pdflatex", "pdf2svg"]
    assert "scale(0.5)" in (list(group)[0].get("transform") or "")


def test_scale_applied(tmp_path: Path) -> None:
    """Figure 400x100 into group 200x100 with fit=width → scale 0.5."""
    _make_panel(tmp_path / "panel.svg", width=200, height=100)
    _make_figure(tmp_path / "fig.svg", width=400, height=100)
    output = tmp_path / "out.svg"

    _compile_one(
        {"panel": "panel.svg", "plot": {"file": "fig.svg", "fit": "width"}},
        tmp_path / "pc.yaml",
        output,
    )

    group = ET.parse(output).getroot().find(f".//*[@{{{INKSCAPE_NS}}}label='plot']")
    assert group is not None
    assert "scale(0.5)" in (list(group)[0].get("transform") or "")


def test_missing_group_skips_gracefully(tmp_path: Path) -> None:
    _make_panel(tmp_path / "panel.svg", label="plot")
    _make_figure(tmp_path / "fig.svg")
    output = tmp_path / "out.svg"

    # "other" label doesn't exist — should not crash, output still written
    _compile_one(
        {"panel": "panel.svg", "other": "fig.svg"}, tmp_path / "pc.yaml", output
    )

    assert output.exists()


def test_per_output_dpi_keyed_form(tmp_path: Path, monkeypatch) -> None:
    """`output` entry `name.png:` with a nested `dpi` is passed to the writer."""
    _make_panel(tmp_path / "panel.svg")
    _make_figure(tmp_path / "fig.svg")
    config = tmp_path / "pc.yaml"
    config.write_text(
        "panel: panel.svg\n"
        "output:\n"
        "  - out.svg\n"
        "  - out.png:\n"
        "      dpi: 600\n"
        "plot:\n"
        "  file: fig.svg\n"
    )

    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(
        config_module,
        "_write_output",
        lambda tree, path, dpi=None: calls.append((path.name, dpi)),
    )
    compile_panel(config, tmp_path / "fallback.svg")

    assert ("out.svg", None) in calls
    assert ("out.png", 600) in calls


def test_per_output_dpi_file_form(tmp_path: Path, monkeypatch) -> None:
    """`output` entry `{file: name.png, dpi: N}` is also accepted."""
    _make_panel(tmp_path / "panel.svg")
    _make_figure(tmp_path / "fig.svg")
    config = tmp_path / "pc.yaml"
    config.write_text(
        "panel: panel.svg\n"
        "output:\n"
        "  - file: out.png\n"
        "    dpi: 300\n"
        "plot:\n"
        "  file: fig.svg\n"
    )

    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(
        config_module,
        "_write_output",
        lambda tree, path, dpi=None: calls.append((path.name, dpi)),
    )
    compile_panel(config, tmp_path / "fallback.svg")

    assert ("out.png", 300) in calls


def test_multi_output(tmp_path: Path) -> None:
    _make_panel(tmp_path / "panel.svg")
    _make_figure(tmp_path / "fig.svg")
    config = tmp_path / "pc.yaml"
    config.write_text(
        "panel: panel.svg\noutput:\n  - out1.svg\n  - out2.svg\nplot:\n  file: fig.svg\n"
    )

    compile_panel(config, tmp_path / "fallback.svg")

    assert (tmp_path / "out1.svg").exists()
    assert (tmp_path / "out2.svg").exists()

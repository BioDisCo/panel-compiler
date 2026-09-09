from pathlib import Path

import pc
from panel_compiler import compiler, config, renderers
from panel_compiler.renderers import RenderedFigure

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


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


def _write_minimal_config(config_path: Path) -> None:
    panel = config_path.parent / "panel.svg"
    panel.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{INKSCAPE_NS}"'
        f' width="100" height="100" viewBox="0 0 100 100">'
        f'<g inkscape:label="plot"/>'
        f"</svg>"
    )
    config_path.write_text("panel: panel.svg\n")


def test_pc_compile_panel_restores_write_output_after_call(
    tmp_path: Path, monkeypatch
) -> None:
    """A monkeypatch of ``pc._write_output`` must not leak into ``panel_compiler.config``
    past the call that propagated it, or every later caller of
    ``panel_compiler.config.compile_panel`` silently inherits the stub."""
    config_path = tmp_path / "pc.yaml"
    _write_minimal_config(config_path)
    original = config._write_output

    monkeypatch.setattr(pc, "_write_output", lambda tree, path, dpi=None: None)
    pc.compile_panel(config_path, tmp_path / "out.svg")

    assert config._write_output is original


def test_pc_compile_one_restores_write_output_after_call(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "pc.yaml"
    _write_minimal_config(config_path)
    original = compiler._write_output

    monkeypatch.setattr(pc, "_write_output", lambda tree, path, dpi=None: None)
    pc._compile_one({"panel": "panel.svg"}, config_path, tmp_path / "out.svg")

    assert compiler._write_output is original


def test_pc_main_honors_write_output_patch(tmp_path: Path, monkeypatch) -> None:
    """``pc.main()`` must route through the same monkeypatched writer as the other
    compatibility wrappers, since ``panel_compiler.cli.main`` calls
    ``panel_compiler.config.compile_panel`` directly."""
    config_path = tmp_path / "pc.yaml"
    _write_minimal_config(config_path)

    calls: list[Path] = []
    monkeypatch.setattr(
        pc, "_write_output", lambda tree, path, dpi=None: calls.append(path)
    )
    monkeypatch.setattr("sys.argv", ["pc", str(config_path)])
    monkeypatch.chdir(tmp_path)

    pc.main()

    assert calls == [config_path.with_suffix(".svg")]
    assert not calls[0].exists()


def test_pc_main_restores_write_output_after_call(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "pc.yaml"
    _write_minimal_config(config_path)
    original = config._write_output

    monkeypatch.setattr(pc, "_write_output", lambda tree, path, dpi=None: None)
    monkeypatch.setattr("sys.argv", ["pc", str(config_path)])
    monkeypatch.chdir(tmp_path)
    pc.main()

    assert config._write_output is original


def test_pc_pdf_to_svg_registers_tempdir_for_exit_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    """The legacy ``Path``-only return has no cleanup handle, so the temp dir must
    at least be reclaimed at process exit instead of leaking for the process's life."""
    tempdir = tmp_path / "rendered"
    tempdir.mkdir()
    svg_path = tempdir / "out.svg"
    svg_path.write_text("<svg/>")

    monkeypatch.setattr(
        renderers, "pdf_to_svg", lambda pdf_path: RenderedFigure(svg_path, tempdir)
    )
    registered: list = []
    monkeypatch.setattr(pc.atexit, "register", registered.append)

    result = pc.pdf_to_svg(tmp_path / "figure.pdf")

    assert result == svg_path
    assert len(registered) == 1
    registered[0]()
    assert not tempdir.exists()


def test_pc_tex_file_to_svg_registers_tempdir_for_exit_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    tempdir = tmp_path / "rendered"
    tempdir.mkdir()
    svg_path = tempdir / "out.svg"
    svg_path.write_text("<svg/>")

    monkeypatch.setattr(
        renderers,
        "tex_file_to_svg",
        lambda tex_path: RenderedFigure(svg_path, tempdir),
    )
    registered: list = []
    monkeypatch.setattr(pc.atexit, "register", registered.append)

    result = pc.tex_file_to_svg(tmp_path / "figure.tex")

    assert result == svg_path
    assert len(registered) == 1
    registered[0]()
    assert not tempdir.exists()


def test_pc_pdf_to_svg_passes_through_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(renderers, "pdf_to_svg", lambda pdf_path: None)
    assert pc.pdf_to_svg(tmp_path / "figure.pdf") is None


def test_pc_tex_file_to_svg_passes_through_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(renderers, "tex_file_to_svg", lambda tex_path: None)
    assert pc.tex_file_to_svg(tmp_path / "figure.tex") is None


def test_pc_pdf_to_svg_no_registration_without_tempdir(
    tmp_path: Path, monkeypatch
) -> None:
    """A ``RenderedFigure`` that owns no temp dir (plain source pass-through) must
    not register a spurious cleanup."""
    svg_path = tmp_path / "out.svg"
    monkeypatch.setattr(
        renderers, "pdf_to_svg", lambda pdf_path: RenderedFigure(svg_path)
    )
    registered: list = []
    monkeypatch.setattr(pc.atexit, "register", registered.append)

    assert pc.pdf_to_svg(tmp_path / "figure.pdf") == svg_path
    assert registered == []

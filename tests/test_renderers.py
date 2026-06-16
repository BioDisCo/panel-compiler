from pathlib import Path
from subprocess import CompletedProcess

import pytest

from panel_compiler import renderers


def test_render_file_to_svg_returns_source_for_svg(tmp_path: Path) -> None:
    svg = tmp_path / "figure.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')

    rendered = renderers.render_file_to_svg(svg)

    assert rendered is not None
    assert rendered.svg_path == svg
    assert rendered.tempdir is None


def test_render_file_to_svg_rejects_unsupported_suffix(tmp_path: Path) -> None:
    rendered = renderers.render_file_to_svg(tmp_path / "figure.gif")

    assert rendered is None


def _tiny_png(width: int, height: int) -> bytes:
    """Minimal PNG header (signature + IHDR) -- enough to read the size."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"\x00\x00\x00\x0dIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big")
    return sig + ihdr + b"\x08\x02\x00\x00\x00"


def test_render_file_to_svg_wraps_png(tmp_path: Path) -> None:
    png = tmp_path / "figure.png"
    png.write_bytes(_tiny_png(40, 20))

    rendered = renderers.render_file_to_svg(png)

    assert rendered is not None
    text = rendered.svg_path.read_text()
    assert 'viewBox="0 0 40 20"' in text
    assert "<image" in text
    assert "data:image/png;base64," in text

    assert rendered.tempdir is not None
    rendered.cleanup()
    assert not rendered.tempdir.exists()


def test_pdf_to_svg_cleans_tempdir_on_failure(tmp_path: Path, monkeypatch) -> None:
    seen_svg_path: Path | None = None

    def fake_run(cmd, **kwargs):
        nonlocal seen_svg_path
        seen_svg_path = Path(cmd[2])
        return CompletedProcess(cmd, 1, "", "conversion failed")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    rendered = renderers.pdf_to_svg(tmp_path / "figure.pdf")

    assert rendered is None
    assert seen_svg_path is not None
    assert not seen_svg_path.parent.exists()


def test_tex_file_to_svg_uses_source_directory_as_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    tex = tmp_path / "nested" / "figure.tex"
    tex.parent.mkdir()
    tex.write_text("\\documentclass{standalone}\\begin{document}x\\end{document}")
    cwd_seen: Path | None = None

    def fake_run(cmd, **kwargs):
        nonlocal cwd_seen
        if cmd[0] == "pdflatex":
            cwd_seen = kwargs["cwd"]
            assert cmd[-1] == "figure.tex"
            output_dir = Path(cmd[cmd.index("-output-directory") + 1])
            jobname = cmd[cmd.index("-jobname") + 1]
            (output_dir / f"{jobname}.pdf").write_text("%PDF-1.4\n")
        elif cmd[0] == "pdf2svg":
            Path(cmd[2]).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    rendered = renderers.tex_file_to_svg(tex)

    assert rendered is not None
    assert cwd_seen == tex.parent
    assert rendered.svg_path.exists()
    rendered.cleanup()
    assert not rendered.svg_path.parent.exists()


def test_tex_file_to_svg_logs_pdflatex_failure_context(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    tex = tmp_path / "bad.tex"
    tex.write_text("\\documentclass{standalone}\\begin{document}\\bad\\end{document}")

    def fake_run(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-output-directory") + 1])
        jobname = cmd[cmd.index("-jobname") + 1]
        (output_dir / f"{jobname}.log").write_text(
            "\n".join(
                [
                    "line before error",
                    "./bad.tex:1: Undefined control sequence.",
                    "l.1 \\bad",
                ]
            )
        )
        return CompletedProcess(cmd, 1, "stdout detail", "stderr detail")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.tex_file_to_svg(tex)

    assert rendered is None
    log_text = caplog.text
    assert "Failed to compile TeX figure" in log_text
    assert str(tex) in log_text
    assert "Command: pdflatex" in log_text
    assert f"Working directory: {tmp_path}" in log_text
    assert "./bad.tex:1: Undefined control sequence." in log_text
    assert "stdout detail" in log_text
    assert "stderr detail" in log_text


def test_inline_latex_logs_pdflatex_failure_context(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_run(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-output-directory") + 1])
        (output_dir / "doc.log").write_text(
            "./doc.tex:8: Missing $ inserted.\nl.8 \\bad"
        )
        return CompletedProcess(cmd, 1, "", "inline stderr")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("ERROR", logger="pc"):
        content = renderers.render_latex_to_svg("\\bad")

    assert content == []
    log_text = caplog.text
    assert "Failed to render inline LaTeX" in log_text
    assert "Command: pdflatex" in log_text
    assert "./doc.tex:8: Missing $ inserted." in log_text
    assert "inline stderr" in log_text

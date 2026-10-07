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
    ihdr = (
        b"\x00\x00\x00\x0dIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big")
    )
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


def test_tail_text_truncates_long_output() -> None:
    text = "\n".join(f"line {i}" for i in range(50))
    tail = renderers._tail_text(text, max_lines=10)
    lines = tail.splitlines()
    assert lines[0] == "..."
    assert lines[1:] == [f"line {i}" for i in range(40, 50)]


def test_read_text_tail_returns_empty_for_unreadable_path(tmp_path: Path) -> None:
    assert renderers._read_text_tail(tmp_path / "missing.log") == ""


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


def test_tex_file_to_svg_missing_pdf_after_pdflatex_logs_and_returns_none(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """pdflatex can exit 0 without producing the expected PDF (e.g. a document
    class that swallows errors) -- this must be treated as a failure, not crash
    on a missing file."""
    tex = tmp_path / "figure.tex"
    tex.write_text("\\documentclass{standalone}\\begin{document}x\\end{document}")

    def fake_run(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-output-directory") + 1])
        jobname = cmd[cmd.index("-jobname") + 1]
        (output_dir / f"{jobname}.log").write_text("no PDF output requested")
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.tex_file_to_svg(tex)

    assert rendered is None
    assert "did not produce expected PDF" in caplog.text
    assert "no PDF output requested" in caplog.text


def test_tex_file_to_svg_cleans_up_when_pdf_to_svg_fails(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    tex = tmp_path / "figure.tex"
    tex.write_text("\\documentclass{standalone}\\begin{document}x\\end{document}")
    real_mkdtemp = renderers.tempfile.mkdtemp
    outer_tmpdir: Path | None = None

    def spy_mkdtemp(*args, **kwargs):
        nonlocal outer_tmpdir
        path = Path(real_mkdtemp(*args, **kwargs))
        if outer_tmpdir is None:
            outer_tmpdir = path
        return str(path)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "pdflatex":
            output_dir = Path(cmd[cmd.index("-output-directory") + 1])
            jobname = cmd[cmd.index("-jobname") + 1]
            (output_dir / f"{jobname}.pdf").write_text("%PDF-1.4\n")
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 1, "", "pdf2svg failed")

    monkeypatch.setattr(renderers.tempfile, "mkdtemp", spy_mkdtemp)
    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.tex_file_to_svg(tex)

    assert rendered is None
    assert "Failed to convert LaTeX PDF to SVG" in caplog.text
    assert outer_tmpdir is not None
    assert not outer_tmpdir.exists()


def test_png_size_rejects_non_png_data() -> None:
    assert renderers._png_size(b"not a png at all") is None


def test_jpeg_size_rejects_non_jpeg_data() -> None:
    assert renderers._jpeg_size(b"not a jpeg at all") is None


def test_jpeg_size_parses_sof0_after_app0_segment() -> None:
    app0 = b"\xff\xe0\x00\x04\x00\x00"  # APP0 marker, length 4 (2 payload bytes)
    sof0 = (
        b"\xff\xc0"  # SOF0 marker
        b"\x00\x11"  # segment length
        b"\x08"  # precision
        b"\x00\x1e"  # height = 30
        b"\x00\x32"  # width = 50
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00"  # padding past i + 9 < n check
    )
    data = b"\xff\xd8" + app0 + sof0

    assert renderers._jpeg_size(data) == (50, 30)


def test_jpeg_size_skips_stray_non_marker_bytes() -> None:
    stray = b"\x00"
    sof0 = (
        b"\xff\xc0"
        b"\x00\x11"
        b"\x08"
        b"\x00\x1e"  # height = 30
        b"\x00\x32"  # width = 50
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    )
    data = b"\xff\xd8" + stray + sof0

    assert renderers._jpeg_size(data) == (50, 30)


def test_jpeg_size_returns_none_when_no_sof_found() -> None:
    app0 = b"\xff\xe0\x00\x04\x00\x00"
    data = b"\xff\xd8" + app0 + b"\x00\x00\x00\x00"

    assert renderers._jpeg_size(data) is None


def test_render_file_to_svg_routes_pdf_through_pdf_to_svg(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(cmd, **kwargs):
        Path(cmd[2]).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    rendered = renderers.render_file_to_svg(tmp_path / "figure.pdf")

    assert rendered is not None
    assert rendered.svg_path.exists()
    rendered.cleanup()


def test_render_latex_to_svg_returns_content_on_success(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_run(cmd, **kwargs):
        if cmd[0] == "pdflatex":
            output_dir = Path(cmd[cmd.index("-output-directory") + 1])
            (output_dir / "doc.pdf").write_text("%PDF-1.4\n")
        elif cmd[0] == "inkscape":
            svg_file = Path(cmd[cmd.index("--export-filename") + 1])
            svg_file.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<path id="glyph" d="M 0 0 L 1 1"/>'
                "</svg>"
            )
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("DEBUG", logger="pc"):
        content = renderers.render_latex_to_svg(r"\sin(x)")

    assert len(content) == 1
    assert content[0].get("id") == "glyph"
    assert "Successfully rendered LaTeX" in caplog.text


def test_image_to_svg_rejects_unreadable_dimensions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"not actually a png")

    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.image_to_svg(image_path)

    assert rendered is None
    assert "Could not read image dimensions" in caplog.text


def test_render_latex_to_svg_logs_inkscape_failure(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_run(cmd, **kwargs):
        if cmd[0] == "pdflatex":
            output_dir = Path(cmd[cmd.index("-output-directory") + 1])
            (output_dir / "doc.pdf").write_text("%PDF-1.4\n")
            return CompletedProcess(cmd, 0, "", "")
        return CompletedProcess(cmd, 1, "", "inkscape blew up")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)

    with caplog.at_level("ERROR", logger="pc"):
        content = renderers.render_latex_to_svg("x")

    assert content == []
    assert "Inkscape conversion failed for LaTeX" in caplog.text
    assert "inkscape blew up" in caplog.text


def test_render_latex_to_svg_logs_unexpected_exception(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def raise_oserror(cmd, **kwargs):
        raise OSError("pdflatex not found")

    monkeypatch.setattr(renderers.subprocess, "run", raise_oserror)

    with caplog.at_level("ERROR", logger="pc"):
        content = renderers.render_latex_to_svg("x")

    assert content == []
    assert "Error type: OSError" in caplog.text
    assert "pdflatex not found" in caplog.text


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


@pytest.mark.parametrize(
    "source_suffix,missing_tool",
    [
        (".pdf", "pdf2svg"),
        (".tex", "pdflatex"),
        (".tex", "pdf2svg"),
    ],
)
def test_missing_converter_logs_error_and_cleans_all_tempdirs(
    tmp_path: Path, monkeypatch, caplog, source_suffix: str, missing_tool: str
) -> None:
    source = tmp_path / f"figure{source_suffix}"
    source.write_text("source")
    monkeypatch.setattr(renderers.tempfile, "tempdir", str(tmp_path))

    def fake_run(cmd, **kwargs):
        if cmd[0] == missing_tool:
            raise FileNotFoundError(f"No such executable: {missing_tool}")
        output_dir = Path(cmd[cmd.index("-output-directory") + 1])
        jobname = cmd[cmd.index("-jobname") + 1]
        (output_dir / f"{jobname}.pdf").write_bytes(b"%PDF-1.4")
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(renderers.subprocess, "run", fake_run)
    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.render_file_to_svg(source)

    assert rendered is None
    assert missing_tool in caplog.text
    assert list(tmp_path.iterdir()) == [source]


def test_pdf_conversion_without_output_is_a_failure(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(renderers.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        renderers.subprocess,
        "run",
        lambda cmd, **kwargs: CompletedProcess(cmd, 0, "", ""),
    )
    with caplog.at_level("ERROR", logger="pc"):
        rendered = renderers.pdf_to_svg(tmp_path / "figure.pdf")
    assert rendered is None
    assert "did not produce" in caplog.text
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "data", [_tiny_png(10, 20)[:18], _tiny_png(0, 20), _tiny_png(10, 0)]
)
def test_png_with_incomplete_or_zero_dimensions_is_rejected(data: bytes) -> None:
    assert renderers._png_size(data) is None

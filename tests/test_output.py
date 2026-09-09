import xml.etree.ElementTree as ET
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from panel_compiler import output


def _tiny_tree() -> "ET.ElementTree[ET.Element]":
    return ET.ElementTree(ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg"/>'))


def test_write_output_svg_writes_tree_directly(tmp_path: Path) -> None:
    out = tmp_path / "panel.svg"
    output._write_output(_tiny_tree(), out)

    assert out.exists()
    assert "<svg" in out.read_text()


def test_write_output_pdf_invokes_inkscape_without_dpi(
    tmp_path: Path, monkeypatch
) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(output.subprocess, "run", fake_run)
    out = tmp_path / "panel.pdf"

    output._write_output(_tiny_tree(), out)

    assert len(seen) == 1
    cmd = seen[0]
    assert cmd[0] == "inkscape"
    assert "--export-type=pdf" in cmd
    assert cmd[cmd.index("--export-filename") + 1] == str(out)
    assert not any(arg.startswith("--export-dpi") for arg in cmd)


def test_write_output_png_passes_dpi_flag(tmp_path: Path, monkeypatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(output.subprocess, "run", fake_run)
    out = tmp_path / "panel.png"

    output._write_output(_tiny_tree(), out, dpi=300.0)

    cmd = seen[0]
    assert "--export-type=png" in cmd
    assert "--export-dpi=300.0" in cmd


def test_write_output_logs_error_on_inkscape_failure(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_run(cmd, **kwargs):
        return CompletedProcess(cmd, 1, "", "inkscape exploded")

    monkeypatch.setattr(output.subprocess, "run", fake_run)
    out = tmp_path / "panel.pdf"

    with caplog.at_level("ERROR", logger="pc"):
        output._write_output(_tiny_tree(), out)

    assert not out.exists()
    assert "Inkscape PDF export failed" in caplog.text
    assert "inkscape exploded" in caplog.text

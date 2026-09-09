from pathlib import Path

import pytest

from panel_compiler import cli


def test_cli_default_config_is_pc_yaml(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pc.yaml").write_text("panel: panel.svg\n")
    calls: list[tuple[Path, Path]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        cli,
        "compile_panel",
        lambda config, output: calls.append((config, output)),
    )
    monkeypatch.setattr("sys.argv", ["pc"])

    cli.main()

    assert calls == [(Path("pc.yaml"), Path("pc.svg"))]


def test_cli_explicit_config_sets_matching_fallback_output(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "custom.yaml"
    config.write_text("panel: panel.svg\n")
    calls: list[tuple[Path, Path]] = []

    monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        cli,
        "compile_panel",
        lambda config, output: calls.append((config, output)),
    )
    monkeypatch.setattr("sys.argv", ["pc", str(config)])

    cli.main()

    assert calls == [(config, config.with_suffix(".svg"))]


def test_cli_missing_config_file_logs_error_and_does_not_compile(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[tuple[Path, Path]] = []

    monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        cli, "compile_panel", lambda config, output: calls.append((config, output))
    )
    monkeypatch.setattr("sys.argv", ["pc", str(tmp_path / "missing.yaml")])

    with caplog.at_level("ERROR", logger="pc"):
        cli.main()

    assert calls == []
    assert "Config file not found" in caplog.text


def test_cli_warns_about_missing_tools_on_path(
    tmp_path: Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / "pc.yaml"
    config.write_text("panel: panel.svg\n")

    monkeypatch.setattr(cli.shutil, "which", lambda tool: None)
    monkeypatch.setattr(cli, "compile_panel", lambda config, output: None)
    monkeypatch.setattr("sys.argv", ["pc", str(config)])

    with caplog.at_level("WARNING", logger="pc"):
        cli.main()

    assert "inkscape not found on PATH" in caplog.text
    assert "pdf2svg not found on PATH" in caplog.text
    assert "pdflatex not found on PATH" in caplog.text


def test_cli_version_falls_back_without_installed_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "version",
        lambda name: (_ for _ in ()).throw(cli.PackageNotFoundError(name)),
    )

    assert cli._package_version() == "unknown"

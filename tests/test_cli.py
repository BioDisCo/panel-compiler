from pathlib import Path

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

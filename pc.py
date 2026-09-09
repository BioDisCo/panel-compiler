#!/usr/bin/env python3
"""Compatibility module for the panel-compiler CLI and legacy imports."""

import atexit
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from panel_compiler import (
    RenderedFigure,
    SVGDimensions,
    _compile_tree,
    _inline_latex_glyphs,
    _rewrite_ids,
    _write_output,
    calculate_bbox,
    calculate_scale,
    get_group_dimensions,
    load_svg_content,
    render_file_to_svg,
    render_latex_to_svg,
)
from panel_compiler import cli as _cli
from panel_compiler import compiler as _compiler
from panel_compiler import config as _config
from panel_compiler import renderers as _renderers
from panel_compiler.renderers import subprocess

__all__ = [
    "RenderedFigure",
    "SVGDimensions",
    "_compile_one",
    "_compile_tree",
    "_inline_latex_glyphs",
    "_rewrite_ids",
    "_write_output",
    "calculate_bbox",
    "calculate_scale",
    "compile_panel",
    "get_group_dimensions",
    "load_svg_content",
    "main",
    "pdf_to_svg",
    "render_file_to_svg",
    "render_latex_to_svg",
    "subprocess",
    "tex_file_to_svg",
]


class _WriterModule(Protocol):
    _write_output: Callable[..., None]


@contextmanager
def _patched_write_output(*modules: _WriterModule) -> Iterator[None]:
    """Temporarily point each module's ``_write_output`` at ``pc._write_output``.

    Restores the original binding on exit so a monkeypatch of ``pc._write_output``
    cannot leak past the call that intentionally propagated it.
    """
    originals = [module._write_output for module in modules]
    for module in modules:
        module._write_output = _write_output
    try:
        yield
    finally:
        for module, original in zip(modules, originals):
            module._write_output = original


def _unwrap_rendered(rendered: RenderedFigure | None) -> Path | None:
    """Return a rendered figure's SVG path, registering its temp dir for
    process-exit cleanup since the legacy signature has no cleanup handle."""
    if rendered is None:
        return None
    if rendered.tempdir is not None:
        atexit.register(rendered.cleanup)
    return rendered.svg_path


def _compile_one(panel_config: dict, config_path: Path, output_path: Path) -> None:
    """Compatibility wrapper that honors monkeypatching ``pc._write_output``."""
    with _patched_write_output(_compiler):
        return _compiler._compile_one(panel_config, config_path, output_path)


def compile_panel(config_path: Path, fallback_output: Path) -> None:
    """Compatibility wrapper that honors monkeypatching ``pc._write_output``."""
    with _patched_write_output(_config):
        return _config.compile_panel(config_path, fallback_output)


def main() -> None:
    """Compatibility wrapper that honors monkeypatching ``pc._write_output``."""
    with _patched_write_output(_config):
        return _cli.main()


def pdf_to_svg(pdf_path: Path) -> Path | None:
    """Compatibility wrapper returning the converted SVG path."""
    return _unwrap_rendered(_renderers.pdf_to_svg(pdf_path))


def tex_file_to_svg(tex_path: Path) -> Path | None:
    """Compatibility wrapper returning the converted SVG path."""
    return _unwrap_rendered(_renderers.tex_file_to_svg(tex_path))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compatibility module for the panel-compiler CLI and legacy imports."""

from pathlib import Path

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
from panel_compiler import compiler as _compiler
from panel_compiler import config as _config
from panel_compiler import renderers as _renderers
from panel_compiler.cli import main
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


def _compile_one(panel_config: dict, config_path: Path, output_path: Path) -> None:
    """Compatibility wrapper that honors monkeypatching ``pc._write_output``."""
    _compiler._write_output = _write_output
    return _compiler._compile_one(panel_config, config_path, output_path)


def compile_panel(config_path: Path, fallback_output: Path) -> None:
    """Compatibility wrapper that honors monkeypatching ``pc._write_output``."""
    _config._write_output = _write_output
    return _config.compile_panel(config_path, fallback_output)


def pdf_to_svg(pdf_path: Path) -> Path | None:
    """Compatibility wrapper returning the converted SVG path."""
    rendered = _renderers.pdf_to_svg(pdf_path)
    return rendered.svg_path if rendered is not None else None


def tex_file_to_svg(tex_path: Path) -> Path | None:
    """Compatibility wrapper returning the converted SVG path."""
    rendered = _renderers.tex_file_to_svg(tex_path)
    return rendered.svg_path if rendered is not None else None


if __name__ == "__main__":
    main()

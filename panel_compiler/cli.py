"""Command-line interface for panel-compiler."""

import argparse
import logging
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from panel_compiler.config import compile_panel
from panel_compiler.logging_utils import ColorFormatter

logger = logging.getLogger("pc")


def _package_version() -> str:
    try:
        return version("panel-compiler")
    except PackageNotFoundError:
        return "unknown"


def main() -> None:
    """CLI entry point."""
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(
        description="Compile SVG figures into a panel template"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_package_version()}"
    )
    default_config = "pc.yaml"
    parser.add_argument(
        "config",
        nargs="?",
        default=default_config,
        help=f"Configuration YAML file (defaults to {default_config})",
    )
    args = parser.parse_args()

    for tool in ("inkscape", "pdf2svg", "pdflatex"):
        if shutil.which(tool) is None:
            logger.warning(
                f"{tool} not found on PATH - PDF and LaTeX features will fail"
            )

    config_path = Path(args.config)
    output_path = config_path.with_suffix(".svg")

    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return

    compile_panel(config_path, output_path)

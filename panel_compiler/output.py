"""Output writers for compiled panel SVG trees."""

import logging
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("pc")


def _write_output(
    tree: "ET.ElementTree[ET.Element]", output_path: Path, dpi: float | None = None
) -> None:
    """Write a compiled SVG tree to an SVG, PDF, or PNG output path."""
    export_type = output_path.suffix.lower().lstrip(".")
    if export_type in ("pdf", "png"):
        with tempfile.TemporaryDirectory() as tmpdir:
            svg_tmp = Path(tmpdir) / "out.svg"
            tree.write(svg_tmp, encoding="utf-8", xml_declaration=True)
            cmd = [
                "inkscape",
                str(svg_tmp),
                f"--export-type={export_type}",
                "--export-filename",
                str(output_path),
            ]
            if dpi is not None:
                cmd.append(f"--export-dpi={dpi}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(
                    f"Inkscape {export_type.upper()} export failed\n{result.stderr}"
                )
                return
    else:
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
    logger.info(f"Panel compiled to {output_path}")

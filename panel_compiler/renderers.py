"""Render supported figure sources into SVG content."""

from __future__ import annotations

import base64
import copy
import logging
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from panel_compiler.dimensions import SVGDimensions

logger = logging.getLogger("pc")
_MAX_LOG_LINES = 40
_LOCAL_URL = re.compile(r"url\(\s*(['\"]?)#([^\s'\"()]+)\1\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class RenderedFigure:
    """An SVG figure produced from a source file."""

    svg_path: Path
    tempdir: Path | None = None

    def cleanup(self) -> None:
        if self.tempdir is not None:
            shutil.rmtree(self.tempdir, ignore_errors=True)


def _rewrite_ids(elements: list[ET.Element], prefix: str) -> None:
    """Prefix all IDs and their references within elements to avoid conflicts."""
    ids = {
        value: f"{prefix}-{value}"
        for el in elements
        for node in el.iter()
        if (value := node.get("id"))
    }

    if not ids:
        return

    href_attrs = {
        "href",
        "{http://www.w3.org/1999/xlink}href",
    }

    def rewrite_url(match: re.Match) -> str:
        old_id = match.group(2)
        if old_id not in ids:
            return match.group(0)
        start, end = match.span(2)
        text = match.group(0)
        return text[: start - match.start()] + ids[old_id] + text[end - match.start() :]

    for el in elements:
        for node in el.iter():
            if id_val := node.get("id"):
                node.set("id", ids[id_val])
            for attr, value in list(node.attrib.items()):
                if attr in href_attrs:
                    if value.startswith("#") and value[1:] in ids:
                        node.set(attr, f"#{ids[value[1:]]}")
                elif attr != "id":
                    node.set(attr, _LOCAL_URL.sub(rewrite_url, value))
            if node.tag.rsplit("}", 1)[-1] == "style" and node.text:
                node.text = _LOCAL_URL.sub(rewrite_url, node.text)


def load_svg_content(svg_path: Path, id_prefix: str | None = None) -> list[ET.Element]:
    """Preserve the source viewport and presentation inside a nested SVG.

    Its viewport is sized in source user units; the compiler supplies the outer
    fit transform. Retaining viewBox also preserves nonzero coordinate origins.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    dims = SVGDimensions.from_element(root)
    root.set("width", str(dims.width))
    root.set("height", str(dims.height))
    root.set("x", "0")
    root.set("y", "0")
    elements = [root]
    if id_prefix:
        _rewrite_ids(elements, id_prefix)
    return elements


def pdf_to_svg(pdf_path: Path) -> RenderedFigure | None:
    """Convert PDF to SVG."""
    tmpdir = Path(tempfile.mkdtemp())
    svg_file = tmpdir / "out.svg"
    rendered = None
    try:
        result = subprocess.run(
            ["pdf2svg", str(pdf_path), str(svg_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"pdf2svg failed for {pdf_path}\n{result.stderr}")
        elif not svg_file.is_file():
            logger.error(f"pdf2svg did not produce expected SVG for {pdf_path}")
        else:
            rendered = RenderedFigure(svg_file, tmpdir)
        return rendered
    except OSError as exc:
        logger.error(f"pdf2svg failed for {pdf_path}: {exc}")
        return None
    finally:
        if rendered is None:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _tail_text(text: str, max_lines: int = _MAX_LOG_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(["..."] + lines[-max_lines:])


def _read_text_tail(path: Path, max_lines: int = _MAX_LOG_LINES) -> str:
    try:
        return _tail_text(path.read_text(errors="replace"), max_lines)
    except OSError:
        return ""


def _format_process_failure(
    *,
    title: str,
    command: list[str],
    result: subprocess.CompletedProcess,
    cwd: Path | None = None,
    log_path: Path | None = None,
) -> str:
    lines = [
        title,
        f"Command: {shlex.join(command)}",
        f"Exit code: {result.returncode}",
    ]
    if cwd is not None:
        lines.append(f"Working directory: {cwd}")

    if log_path is not None:
        log_tail = _read_text_tail(log_path)
        if log_tail:
            lines.extend([f"LaTeX log tail ({log_path.name}):", log_tail])

    if result.stdout.strip():
        lines.extend(["stdout tail:", _tail_text(result.stdout)])
    if result.stderr.strip():
        lines.extend(["stderr tail:", _tail_text(result.stderr)])

    return "\n".join(lines)


def tex_file_to_svg(tex_path: Path) -> RenderedFigure | None:
    """Compile a standalone LaTeX document and convert its PDF output to SVG."""
    with tempfile.TemporaryDirectory() as directory:
        tmpdir = Path(directory)
        jobname = "pc_tex_figure"
        command = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-output-directory",
            str(tmpdir),
            "-jobname",
            jobname,
            tex_path.name,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=tex_path.parent,
            )
        except OSError as exc:
            logger.error(f"pdflatex failed for {tex_path}: {exc}")
            return None

        log_path = tmpdir / f"{jobname}.log"
        if result.returncode != 0:
            logger.error(
                _format_process_failure(
                    title=f"Failed to compile TeX figure: {tex_path}",
                    command=command,
                    result=result,
                    cwd=tex_path.parent,
                    log_path=log_path,
                )
            )
            return None

        pdf_path = tmpdir / f"{jobname}.pdf"
        if not pdf_path.is_file():
            log_tail = _read_text_tail(log_path)
            details = [
                f"pdflatex did not produce expected PDF for TeX figure: {tex_path}",
                f"Expected PDF: {pdf_path}",
            ]
            if log_tail:
                details.extend([f"LaTeX log tail ({log_path.name}):", log_tail])
            logger.error("\n".join(details))
            return None

        # The PDF converter owns the returned SVG directory; LaTeX intermediates
        # can be removed on every exit, including a missing converter executable.
        rendered = pdf_to_svg(pdf_path)
        if rendered is None:
            logger.error(f"Failed to convert LaTeX PDF to SVG for {tex_path}")
        return rendered


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return (
                int.from_bytes(data[i + 7 : i + 9], "big"),
                int.from_bytes(data[i + 5 : i + 7], "big"),
            )
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


def image_to_svg(image_path: Path) -> RenderedFigure | None:
    """Wrap a raster image (PNG/JPEG) in an SVG so it fits a panel slot like any
    other figure. The image is embedded as a base64 data URI at its pixel size;
    the panel compiler then scales that to the placeholder."""
    data = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    size = _png_size(data) if suffix == ".png" else _jpeg_size(data)
    if size is None:
        logger.error(f"Could not read image dimensions for {image_path}")
        return None
    width, height = size
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    href = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    tmpdir = Path(tempfile.mkdtemp())
    svg_file = tmpdir / "out.svg"
    svg_file.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<image width="{width}" height="{height}" xlink:href="{href}"/></svg>'
    )
    return RenderedFigure(svg_file, tmpdir)


def render_file_to_svg(source_path: Path) -> RenderedFigure | None:
    """Render a supported source file to an SVG path."""
    suffix = source_path.suffix.lower()
    if suffix == ".svg":
        return RenderedFigure(source_path)
    if suffix == ".pdf":
        return pdf_to_svg(source_path)
    if suffix == ".tex":
        return tex_file_to_svg(source_path)
    if suffix in (".png", ".jpg", ".jpeg"):
        return image_to_svg(source_path)

    logger.warning(f"Unsupported figure file type '{suffix}' for {source_path}")
    return None


def render_latex_to_svg(latex_text: str) -> list[ET.Element]:
    """Render LaTeX text to SVG using pdflatex and inkscape."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            latex_doc = f"""\\documentclass{{article}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{geometry}}
\\geometry{{margin=5pt,paperwidth=500pt,paperheight=100pt}}
\\pagestyle{{empty}}
\\begin{{document}}
\\noindent
{latex_text}
\\end{{document}}
"""

            tex_file = tmpdir_path / "doc.tex"
            tex_file.write_text(latex_doc)

            command = [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-output-directory",
                str(tmpdir_path),
                str(tex_file),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(
                    _format_process_failure(
                        title=f"Failed to render inline LaTeX: {latex_text}",
                        command=command,
                        result=result,
                        log_path=tmpdir_path / "doc.log",
                    )
                )
                return []

            pdf_file = tmpdir_path / "doc.pdf"
            svg_file = tmpdir_path / "doc.svg"
            result = subprocess.run(
                [
                    "inkscape",
                    "--pdf-poppler",
                    str(pdf_file),
                    "--export-type=svg",
                    "--export-filename",
                    str(svg_file),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(
                    f"Inkscape conversion failed for LaTeX: {latex_text}\n{result.stderr}"
                )
                return []

            tree = ET.parse(svg_file)
            content = [copy.deepcopy(elem) for elem in tree.getroot()]

            logger.debug(f"Successfully rendered LaTeX: {latex_text}")
            return content

    except Exception as e:
        logger.error(
            f"Failed to render LaTeX text: {latex_text}\n"
            f"Error type: {type(e).__name__}\n"
            f"Error message: {e}"
        )
        return []


def _inline_latex_glyphs(elements: list[ET.Element]) -> None:
    """Replace <use> glyph references with inlined paths."""
    ns_xlink = "http://www.w3.org/1999/xlink"

    id_map: dict[str, ET.Element] = {}
    for root in elements:
        for node in root.iter():
            if node_id := node.get("id"):
                id_map[node_id] = node

    def _replace_uses(parent: ET.Element) -> None:
        for i, child in enumerate(list(parent)):
            _replace_uses(child)
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "use":
                continue
            href = child.get(f"{{{ns_xlink}}}href") or child.get("href", "")
            if not href.startswith("#"):
                continue
            ref = id_map.get(href[1:])
            if ref is None:
                continue
            x, y = child.get("x", "0"), child.get("y", "0")
            ns_prefix = child.tag.rsplit("}", 1)[0] + "}" if "}" in child.tag else ""
            g = ET.Element(f"{ns_prefix}g")
            try:
                if float(x) != 0.0 or float(y) != 0.0:
                    g.set("transform", f"translate({x},{y})")
            except ValueError:
                g.set("transform", f"translate({x},{y})")
            for sub in ref:
                g.append(copy.deepcopy(sub))
            parent.remove(child)
            parent.insert(i, g)

    for root in elements:
        _replace_uses(root)

    def _remove_defs(parent: ET.Element) -> None:
        for c in [
            c
            for c in parent
            if (c.tag.split("}")[-1] if "}" in c.tag else c.tag) == "defs"
        ]:
            parent.remove(c)
        for c in parent:
            _remove_defs(c)

    for el in [
        el
        for el in elements
        if (el.tag.split("}")[-1] if "}" in el.tag else el.tag) == "defs"
    ]:
        elements.remove(el)
    for root in elements:
        _remove_defs(root)

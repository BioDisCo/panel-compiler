"""Panel template compilation."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from panel_compiler.dimensions import (
    SVGDimensions,
    calculate_scale,
    get_group_dimensions,
)
from panel_compiler.output import _write_output
from panel_compiler.renderers import (
    _inline_latex_glyphs,
    _rewrite_ids,
    load_svg_content,
    render_file_to_svg,
    render_latex_to_svg,
)

logger = logging.getLogger("pc")

INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"
RESERVED_KEYS = {"panel", "output", "content_style"}
_DEFAULT_CONTENT_STYLE = ""


def _compile_one(panel_config: dict, config_path: Path, output_path: Path) -> None:
    """Compile a single panel from a config dict and write to one output path."""
    tree = _compile_tree(panel_config, config_path)
    if tree is not None:
        _write_output(tree, output_path)


def _compile_tree(
    panel_config: dict, config_path: Path
) -> "ET.ElementTree[ET.Element] | None":
    """Parse the template SVG, embed all figures, and return the compiled tree."""
    content_style = panel_config.get("content_style", _DEFAULT_CONTENT_STYLE)
    panel_str = panel_config.get("panel")
    if not panel_str:
        logger.error("Config missing required 'panel' key")
        return None
    panel_path = config_path.parent / panel_str

    if not panel_path.exists():
        logger.error(f"Panel file not found: {panel_path}")
        return None

    tree = ET.parse(panel_path)
    root = tree.getroot()
    parent_map = {child: parent for parent in root.iter() for child in parent}

    namespaces = {
        "svg": "http://www.w3.org/2000/svg",
        "xlink": "http://www.w3.org/1999/xlink",
        "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    for figure_id, figure_config in panel_config.items():
        if figure_id in RESERVED_KEYS:
            continue
        group = _find_placeholder(root, figure_id)
        if group is None:
            logger.warning(f"Group {figure_id} not found in panel {panel_str}")
            continue

        parsed = _parse_figure_config(figure_config)
        tex_text = parsed["tex_text"]
        fontsize = parsed["fontsize"]
        svg_file = parsed["svg_file"]

        try:
            if fontsize.endswith("pt"):
                fontsize_num = float(fontsize[:-2])
            else:
                fontsize_num = float(fontsize)
        except (ValueError, AttributeError):
            fontsize_num = 10.0

        if tex_text:
            content = render_latex_to_svg(tex_text)
            if not content:
                logger.warning(f"Failed to render LaTeX for {figure_id}")
                continue
            _rewrite_ids(content, figure_id)
            _inline_latex_glyphs(content)
            scale = fontsize_num / 12.0
            wrapper_class = "pc-tex-content"
        elif svg_file:
            rendered = _render_figure_file(
                svg_file=svg_file,
                figure_id=figure_id,
                group=group,
                config_path=config_path,
                config_width=parsed["config_width"],
                config_height=parsed["config_height"],
                fit=parsed["fit"],
            )
            if rendered is None:
                continue
            content, scale = rendered
            wrapper_class = "pc-content"
        else:
            logger.warning(f"No SVG file or LaTeX text specified for {figure_id}")
            continue

        group = _prepare_placeholder(group, figure_id, parent_map)
        _append_wrapped_content(group, content, scale, wrapper_class)

    _ensure_style_reset(root, content_style)
    return tree


def _find_placeholder(root: ET.Element, figure_id: str) -> ET.Element | None:
    group = root.find(f".//*[@{INKSCAPE_LABEL}='{figure_id}']")
    if group is None:
        group = root.find(f".//*[@label='{figure_id}']")
    if group is None:
        group = root.find(f".//*[@id='{figure_id}']")
    return group


def _parse_figure_config(figure_config) -> dict:
    tex_text = None
    fontsize = "10pt"
    if isinstance(figure_config, dict):
        svg_file = figure_config.get("file") or figure_config.get("svg")
        fit = figure_config.get("fit", "contain")
        config_width = figure_config.get("width")
        config_height = figure_config.get("height")
        tex_text = figure_config.get("tex")
        fontsize = figure_config.get("size", "10pt")
    else:
        svg_file = figure_config
        fit = "contain"
        config_width = None
        config_height = None
    return {
        "config_height": config_height,
        "config_width": config_width,
        "fit": fit,
        "fontsize": fontsize,
        "svg_file": svg_file,
        "tex_text": tex_text,
    }


def _render_figure_file(
    *,
    svg_file: str,
    figure_id: str,
    group: ET.Element,
    config_path: Path,
    config_width,
    config_height,
    fit: str,
) -> tuple[list[ET.Element], float] | None:
    src_path = config_path.parent / svg_file
    if not src_path.exists():
        logger.warning(f"File not found: {src_path}")
        return None

    rendered = render_file_to_svg(src_path)
    if rendered is None:
        logger.warning(f"Failed to render file for {figure_id}: {src_path}")
        return None

    try:
        config_dims = None
        if config_width and config_height:
            config_dims = SVGDimensions(
                width=float(config_width), height=float(config_height)
            )

        source_dims = SVGDimensions.from_svg(rendered.svg_path)
        target_dims = get_group_dimensions(group, config_dims)

        if target_dims is None:
            logger.debug(
                f"Group {figure_id} has no width/height attributes and none specified "
                "in config. Embedding without scaling."
            )
            scale = 1.0
        else:
            scale = calculate_scale(source_dims, target_dims, fit)

        content = load_svg_content(rendered.svg_path, id_prefix=figure_id)
        return content, scale
    finally:
        rendered.cleanup()


def _prepare_placeholder(
    group: ET.Element,
    figure_id: str,
    parent_map: dict[ET.Element, ET.Element],
) -> ET.Element:
    original_attribs = dict(group.attrib)
    tag_name = group.tag.split("}")[-1] if "}" in group.tag else group.tag

    if tag_name == "rect":
        ns = group.tag.split("}")[0] + "}" if "}" in group.tag else ""
        container = ET.Element(f"{ns}g")
        container.set("id", figure_id)
        x = original_attribs.get("x", "0")
        y = original_attribs.get("y", "0")
        transforms = []
        if original_transform := original_attribs.get("transform"):
            transforms.append(original_transform)
        transforms.append(f"translate({x},{y})")
        container.set("transform", " ".join(transforms))
        if w := original_attribs.get("width"):
            container.set("data-pc-width", w)
        if h := original_attribs.get("height"):
            container.set("data-pc-height", h)
        parent = parent_map[group]
        idx = list(parent).index(group)
        parent.remove(group)
        parent.insert(idx, container)
        return container

    group.clear()
    group.attrib.update(original_attribs)
    return group


def _append_wrapped_content(
    group: ET.Element,
    content: list[ET.Element],
    scale: float,
    wrapper_class: str,
) -> None:
    ns = group.tag.split("}")[0] + "}" if "}" in group.tag else ""
    wrapper = ET.Element(f"{ns}g")
    if scale != 1.0:
        wrapper.set("transform", f"scale({scale})")
    wrapper.set("class", wrapper_class)
    for element in content:
        wrapper.append(element)
    group.append(wrapper)


def _ensure_style_reset(root: ET.Element, content_style: str) -> None:
    ns_svg = "{http://www.w3.org/2000/svg}"
    defs = root.find(f"{ns_svg}defs")
    if defs is None:
        defs = root.find("defs")
    if defs is None:
        defs = ET.SubElement(root, f"{ns_svg}defs")
    for old in defs.findall(f"{ns_svg}style") + defs.findall("style"):
        if old.text and ".pc-tex-content" in old.text:
            defs.remove(old)
    rules = []
    if content_style:
        rules.append(
            ".pc-content path, .pc-content circle, .pc-content polygon "
            f"{{ {content_style} }}"
        )
    rules.append(
        ".pc-tex-content path, .pc-tex-content circle, .pc-tex-content polygon "
        "{ stroke: none !important; fill: initial; }"
    )
    style_reset = ET.SubElement(defs, f"{ns_svg}style")
    style_reset.set("type", "text/css")
    style_reset.text = "\n".join(rules)

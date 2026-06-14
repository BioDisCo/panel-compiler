"""SVG dimension and scaling helpers."""

import xml.etree.ElementTree as ET
import re
from pathlib import Path


class SVGDimensions:
    """SVG dimensions in source user units, for computing scale transforms."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height

    @classmethod
    def from_svg(cls, svg_path: Path) -> "SVGDimensions":
        """Return the source user-unit extent of an SVG (viewBox dimensions).

        The scale transform ``scale(s)`` multiplies element coordinates by ``s``
        in the *target* SVG's user-unit space. Physical units (pt, mm, ...) on
        the ``width``/``height`` attributes are irrelevant for that ratio; only
        the viewBox extent, which matches element coordinate ranges, matters.
        """
        tree = ET.parse(svg_path)
        root = tree.getroot()

        viewbox = root.get("viewBox")
        if viewbox:
            parts = [part for part in re.split(r"[\s,]+", viewbox.strip()) if part]
            if len(parts) != 4:
                raise ValueError(f"Cannot parse viewBox for {svg_path}: {viewbox}")
            return cls(width=float(parts[2]), height=float(parts[3]))

        width_attr = root.get("width")
        height_attr = root.get("height")
        if width_attr and height_attr:
            try:
                return cls(width=float(width_attr), height=float(height_attr))
            except ValueError:
                raise ValueError(
                    f"Cannot determine user-unit dimensions for {svg_path}: "
                    "no viewBox and physical-unit width/height are ambiguous"
                )

        raise ValueError(f"Cannot determine dimensions for {svg_path}")


def get_group_dimensions(
    group: ET.Element,
    config_dims: SVGDimensions | None = None,
) -> SVGDimensions | None:
    """Extract dimensions from group attributes, config, or bounding box."""
    pc_w = group.get("data-pc-width")
    pc_h = group.get("data-pc-height")
    if pc_w and pc_h:
        return SVGDimensions(width=float(pc_w), height=float(pc_h))

    width = group.get("width")
    height = group.get("height")
    if width and height:
        return SVGDimensions(width=float(width), height=float(height))

    if config_dims:
        return config_dims

    bbox = calculate_bbox(group)
    if bbox:
        return bbox

    return None


def calculate_bbox(element: ET.Element) -> SVGDimensions | None:
    """Calculate bounding box from element and its children."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for elem in element.iter():
        x = elem.get("x")
        y = elem.get("y")
        w = elem.get("width")
        h = elem.get("height")

        if x and w:
            min_x = min(min_x, float(x))
            max_x = max(max_x, float(x) + float(w))
        if y and h:
            min_y = min(min_y, float(y))
            max_y = max(max_y, float(y) + float(h))

        cx = elem.get("cx")
        cy = elem.get("cy")
        r = elem.get("r")
        if cx and cy and r:
            cx_f, cy_f, r_f = float(cx), float(cy), float(r)
            min_x = min(min_x, cx_f - r_f)
            max_x = max(max_x, cx_f + r_f)
            min_y = min(min_y, cy_f - r_f)
            max_y = max(max_y, cy_f + r_f)

    if min_x != float("inf") and max_x != float("-inf"):
        width = max_x - min_x
        height = max_y - min_y if min_y != float("inf") else width
        if width > 0 and height > 0:
            return SVGDimensions(width=width, height=height)

    return None


def calculate_scale(
    source_dims: SVGDimensions,
    target_dims: SVGDimensions,
    fit: str,
) -> float:
    """Calculate scale factor based on fit strategy."""
    if fit == "height":
        return target_dims.height / source_dims.height
    if fit == "width":
        return target_dims.width / source_dims.width
    if fit == "contain":
        return min(
            target_dims.width / source_dims.width,
            target_dims.height / source_dims.height,
        )
    raise ValueError(f"Unknown fit option: {fit}")

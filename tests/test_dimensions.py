import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from panel_compiler.dimensions import (
    SVGDimensions,
    calculate_bbox,
    calculate_scale,
    get_group_dimensions,
)


def test_from_viewbox(tmp_path: Path) -> None:
    f = tmp_path / "s.svg"
    f.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 150"/>')
    dims = SVGDimensions.from_svg(f)
    assert dims.width == 300
    assert dims.height == 150


def test_from_width_height(tmp_path: Path) -> None:
    f = tmp_path / "s.svg"
    f.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40"/>')
    dims = SVGDimensions.from_svg(f)
    assert dims.width == 80
    assert dims.height == 40


def test_viewbox_takes_priority(tmp_path: Path) -> None:
    f = tmp_path / "s.svg"
    f.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40" viewBox="0 0 300 150"/>'
    )
    assert SVGDimensions.from_svg(f).width == 300


def test_missing_dims_raises(tmp_path: Path) -> None:
    f = tmp_path / "s.svg"
    f.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(ValueError):
        SVGDimensions.from_svg(f)


@pytest.mark.parametrize(
    "fit,expected",
    [
        ("height", 2.0),
        ("width", 0.5),
        ("contain", 0.5),
    ],
)
def test_calculate_scale(fit: str, expected: float) -> None:
    # source 200x100, target 100x200
    src = SVGDimensions(200, 100)
    tgt = SVGDimensions(100, 200)
    assert calculate_scale(src, tgt, fit) == pytest.approx(expected)


def test_calculate_scale_unknown_fit() -> None:
    s = SVGDimensions(100, 100)
    with pytest.raises(ValueError):
        calculate_scale(s, s, "bad")


def test_bbox_from_rect() -> None:
    elem = ET.fromstring(
        '<g xmlns="http://www.w3.org/2000/svg">'
        '<rect x="10" y="20" width="80" height="40"/>'
        "</g>"
    )
    bbox = calculate_bbox(elem)
    assert bbox is not None
    assert bbox.width == pytest.approx(80)
    assert bbox.height == pytest.approx(40)


def test_bbox_from_circle() -> None:
    elem = ET.fromstring(
        '<g xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="30"/></g>'
    )
    bbox = calculate_bbox(elem)
    assert bbox is not None
    assert bbox.width == pytest.approx(60)
    assert bbox.height == pytest.approx(60)


def test_get_group_dims_from_attribs() -> None:
    g = ET.fromstring('<g xmlns="http://www.w3.org/2000/svg" width="100" height="50"/>')
    dims = get_group_dimensions(g)
    assert dims is not None
    assert dims.width == 100
    assert dims.height == 50


def test_get_group_dims_from_config_fallback() -> None:
    g = ET.fromstring('<g xmlns="http://www.w3.org/2000/svg"/>')
    dims = get_group_dimensions(g, SVGDimensions(120, 60))
    assert dims is not None
    assert dims.width == 120


def test_get_group_dims_none_when_empty() -> None:
    g = ET.fromstring('<g xmlns="http://www.w3.org/2000/svg"/>')
    assert get_group_dimensions(g) is None

import xml.etree.ElementTree as ET

import pytest

from panel_compiler.renderers import _rewrite_ids


def test_prefixes_id() -> None:
    elem = ET.fromstring('<g xmlns="http://www.w3.org/2000/svg" id="foo"/>')
    _rewrite_ids([elem], "pfx")
    assert elem.get("id") == "pfx-foo"


def test_updates_href() -> None:
    elem = ET.fromstring(
        '<g xmlns="http://www.w3.org/2000/svg"><use href="#foo"/><g id="foo"/></g>'
    )
    _rewrite_ids([elem], "pfx")
    use = elem.find("{http://www.w3.org/2000/svg}use")
    assert use is not None
    assert use.get("href") == "#pfx-foo"


def test_updates_style_url() -> None:
    elem = ET.fromstring(
        '<g xmlns="http://www.w3.org/2000/svg">'
        '<path id="clip1"/>'
        '<rect style="clip-path: url(#clip1)"/>'
        "</g>"
    )
    _rewrite_ids([elem], "fig")
    rect = elem.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None
    assert "url(#fig-clip1)" in (rect.get("style") or "")


def test_updates_stroke_url() -> None:
    elem = ET.fromstring(
        '<g xmlns="http://www.w3.org/2000/svg">'
        '<linearGradient id="grad"/>'
        '<path stroke="url(#grad)"/>'
        "</g>"
    )
    _rewrite_ids([elem], "fig")
    path = elem.find("{http://www.w3.org/2000/svg}path")
    assert path is not None
    assert path.get("stroke") == "url(#fig-grad)"


def test_no_ids_is_noop() -> None:
    elem = ET.fromstring('<g xmlns="http://www.w3.org/2000/svg"><rect/></g>')
    _rewrite_ids([elem], "pfx")  # must not raise


def test_references_are_rewritten_once_and_only_on_exact_matches() -> None:
    elem = ET.fromstring(
        '<g><path id="a"/><path id="ab"/><path id="pfx-a"/>'
        '<use href="#a"/><use href="#ab"/><use href="#absent"/></g>'
    )
    _rewrite_ids([elem], "pfx")
    assert [use.get("href") for use in elem.findall("use")] == [
        "#pfx-a",
        "#pfx-ab",
        "#absent",
    ]


def test_colors_and_external_references_are_preserved() -> None:
    elem = ET.fromstring(
        '<g><path id="fff"/><path fill="#fff" stroke="#ffffff"/>'
        '<use href="other.svg#fff"/><path fill="url(other.svg#fff)"/></g>'
    )
    _rewrite_ids([elem], "plot")
    paths = elem.findall("path")
    assert paths[1].get("fill") == "#fff"
    assert paths[1].get("stroke") == "#ffffff"
    assert elem.find("use").get("href") == "other.svg#fff"
    assert paths[2].get("fill") == "url(other.svg#fff)"


@pytest.mark.parametrize("url", ["url(#grad)", "url( '#grad' )", 'url( "#grad" )'])
def test_local_urls_in_attributes_and_styles(url: str) -> None:
    elem = ET.Element("g")
    ET.SubElement(elem, "linearGradient", id="grad")
    path = ET.SubElement(elem, "path", fill=url, style=f"stroke: {url}; fill: #fff")
    stylesheet = ET.SubElement(elem, "style")
    stylesheet.text = f".curve {{ fill: {url}; color: #fff }}"
    _rewrite_ids([elem], "plot")
    expected = url.replace("#grad", "#plot-grad")
    assert path.get("fill") == expected
    assert path.get("style") == f"stroke: {expected}; fill: #fff"
    assert stylesheet.text == f".curve {{ fill: {expected}; color: #fff }}"

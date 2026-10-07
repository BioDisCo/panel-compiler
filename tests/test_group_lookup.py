from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from panel_compiler.compiler import _compile_tree

NS_INK = "http://www.inkscape.org/namespaces/inkscape"
NS_SVG = "http://www.w3.org/2000/svg"


def _figure(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50">'
        '<rect x="0" y="0" width="50" height="50" fill="green"/>'
        "</svg>"
    )


def _panel_with(path: Path, extra_attrs: str) -> None:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="{NS_SVG}" xmlns:inkscape="{NS_INK}" viewBox="0 0 100 100">'
        f'<g {extra_attrs} width="60" height="60"/>'
        "</svg>"
    )


def test_lookup_by_inkscape_label(tmp_path: Path) -> None:
    _figure(tmp_path / "f.svg")
    _panel_with(tmp_path / "p.svg", 'inkscape:label="myplot"')
    tree = _compile_tree({"panel": "p.svg", "myplot": "f.svg"}, tmp_path / "pc.yaml")
    assert tree is not None
    g = tree.getroot().find(f".//*[@{{{NS_INK}}}label='myplot']")
    assert g is not None and list(g)


def test_lookup_by_label_attribute(tmp_path: Path) -> None:
    _figure(tmp_path / "f.svg")
    _panel_with(tmp_path / "p.svg", 'label="myplot"')
    tree = _compile_tree({"panel": "p.svg", "myplot": "f.svg"}, tmp_path / "pc.yaml")
    assert tree is not None
    g = tree.getroot().find(".//*[@label='myplot']")
    assert g is not None and list(g)


def test_lookup_by_id(tmp_path: Path) -> None:
    _figure(tmp_path / "f.svg")
    _panel_with(tmp_path / "p.svg", 'id="myplot"')
    tree = _compile_tree({"panel": "p.svg", "myplot": "f.svg"}, tmp_path / "pc.yaml")
    assert tree is not None
    g = tree.getroot().find(".//*[@id='myplot']")
    assert g is not None and list(g)


@pytest.mark.parametrize("label", ["Euler's plot", 'plot "A"', 'Euler\'s "A"'])
def test_labels_with_quotes_are_literal(tmp_path: Path, label: str) -> None:
    _figure(tmp_path / "f.svg")
    root = ET.Element(f"{{{NS_SVG}}}svg")
    ET.SubElement(root, f"{{{NS_SVG}}}g", {f"{{{NS_INK}}}label": label})
    ET.ElementTree(root).write(tmp_path / "p.svg")

    tree = _compile_tree({"panel": "p.svg", label: "f.svg"}, tmp_path / "pc.yaml")

    assert tree is not None
    assert len(tree.getroot()[0]) == 1


def test_rect_keeps_identity_and_labels_on_recompile(tmp_path: Path) -> None:
    _figure(tmp_path / "f.svg")
    panel = tmp_path / "p.svg"
    panel.write_text(
        f'<svg xmlns="{NS_SVG}" xmlns:inkscape="{NS_INK}">'
        '<rect id="rect17" inkscape:label="myplot" label="alias" '
        'x="5" y="7" width="60" height="60"/>'
        '<use href="#rect17"/></svg>'
    )
    config = {"panel": "p.svg", "myplot": "f.svg"}
    for _ in range(3):
        tree = _compile_tree(config, tmp_path / "pc.yaml")
        assert tree is not None
        group = tree.getroot().find(".//*[@id='rect17']")
        assert group is not None
        assert group.get(f"{{{NS_INK}}}label") == "myplot"
        assert group.get("label") == "alias"
        assert group.get("transform") == "translate(5,7)"
        assert len(group) == 1
        tree.write(panel)


def test_embedded_labels_do_not_shadow_template_placeholders(tmp_path: Path) -> None:
    (tmp_path / "f.svg").write_text(
        f'<svg xmlns="{NS_SVG}" viewBox="0 0 50 50">'
        '<g label="second"><rect width="50" height="50"/></g></svg>'
    )
    (tmp_path / "p.svg").write_text(
        f'<svg xmlns="{NS_SVG}"><g id="first"/><g id="second"/></svg>'
    )
    config = {"panel": "p.svg", "first": "f.svg", "second": "f.svg"}
    for _ in range(2):
        tree = _compile_tree(config, tmp_path / "pc.yaml")
        assert tree is not None
        second = tree.getroot().find(".//*[@id='second']")
        assert second is not None and len(second) == 1
        tree.write(tmp_path / "p.svg")

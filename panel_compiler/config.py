"""Configuration loading and panel compilation orchestration."""

import logging
from pathlib import Path

import yaml

from panel_compiler.compiler import _compile_tree
from panel_compiler.output import _write_output

logger = logging.getLogger("pc")


class _WarnDuplicatesLoader(yaml.SafeLoader):
    pass


def _construct_mapping_warn_duplicates(
    loader: yaml.SafeLoader, node: yaml.MappingNode
) -> dict:
    pairs: list[tuple] = loader.construct_pairs(node)
    seen: dict[str, int] = {}
    for key, _ in pairs:
        if key in seen:
            logger.warning(
                f"Duplicate YAML key '{key}' - later value overwrites earlier one; "
                "use a list of panel blocks to define multiple panels"
            )
        seen[key] = 1
    return dict(pairs)


_WarnDuplicatesLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_warn_duplicates,
)


def compile_panel(config_path: Path, fallback_output: Path) -> None:
    """Compile one or more panels from a config file."""
    with open(config_path) as f:
        config = yaml.load(f, Loader=_WarnDuplicatesLoader)

    if isinstance(config, list):
        for item in config:
            raw = item.get("output")
            if not raw:
                logger.error("Each panel block must have an 'output' key")
                continue
            tree = _compile_tree(item, config_path)
            if tree is not None:
                for output_path, dpi in _resolve_outputs(raw, fallback_output, config_path):
                    _write_output(tree, output_path, dpi)
    else:
        tree = _compile_tree(config, config_path)
        if tree is not None:
            for output_path, dpi in _resolve_outputs(
                config.get("output"), fallback_output, config_path
            ):
                _write_output(tree, output_path, dpi)


def _resolve_outputs(
    raw, fallback: Path, config_path: Path
) -> list[tuple[Path, float | None]]:
    """Resolve the ``output`` value to (path, dpi) pairs."""
    if not raw:
        return [(fallback, None)]
    resolved: list[tuple[Path, float | None]] = []
    for item in raw if isinstance(raw, list) else [raw]:
        if isinstance(item, str):
            name, opts = item, {}
        elif isinstance(item, dict):
            if "file" in item:
                name, opts = item["file"], item
            else:
                name, opts = next(iter(item.items()))
                opts = opts or {}
        else:
            logger.error(f"Invalid output entry: {item!r}")
            continue
        resolved.append((config_path.parent / name, opts.get("dpi")))
    return resolved

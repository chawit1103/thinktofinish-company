from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    value = os.environ.get("TTF_COMPANY_DATA") or os.environ.get("PLUGIN_DATA")
    if value:
        path = Path(value).expanduser().resolve()
    else:
        path = (plugin_root() / ".local-data").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml(relative_path: str) -> dict[str, Any]:
    """Load policy data without a runtime YAML dependency.

    Runtime policy files have a generated JSON twin next to the human-readable
    YAML. The public function name stays stable for internal callers.
    """
    path = plugin_root() / relative_path
    json_path = path.with_suffix(".json")
    source = json_path if json_path.exists() else path
    if source.suffix != ".json":
        raise RuntimeError(f"Missing runtime JSON policy twin for {relative_path}")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return value

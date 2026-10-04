from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict:
    p = path or ROOT / "config.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    ocr = Path(data.get("ocr_bin", "~/Desktop/adb-scripts/ocr")).expanduser()
    out = Path(data.get("output_dir", "~/Desktop/kuaiji-auto-platform/data/runs")).expanduser()
    data["ocr_bin"] = ocr
    data["output_dir"] = out
    return data

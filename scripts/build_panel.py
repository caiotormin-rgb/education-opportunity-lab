#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from education_opportunity_lab.cli import build_panel_main


if __name__ == "__main__":
    raise SystemExit(build_panel_main())

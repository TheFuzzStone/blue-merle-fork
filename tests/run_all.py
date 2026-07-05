#!/usr/bin/env python3
"""Minimal pytest-less runner for the tests/ suite.

Usage:  python3 tests/run_all.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def main() -> int:
    # Stub pyserial so imports in imei_generate.py succeed on dev hosts.
    sys.modules.setdefault(
        "serial",
        types.SimpleNamespace(
            Serial=lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("Serial not available in unit tests")),
            SerialException=Exception,
        ),
    )

    test_dir = Path(__file__).resolve().parent
    passed = failed = 0
    for test_file in sorted(test_dir.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(test_file.stem, test_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            fn = getattr(mod, name)
            try:
                fn()
                passed += 1
                print(f"PASS: {test_file.stem}::{name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL: {test_file.stem}::{name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"ERROR: {test_file.stem}::{name}: {type(exc).__name__}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Tests for the iPhone-model pool used by RANDOMIZE_HOSTNAME.

We don't invoke RANDOMIZE_HOSTNAME here — it does `uci set/commit`
which would mutate the dev host's UCI. Instead we exercise the pool
file directly and verify the shell picker returns entries from it.

iPad models were removed from this codebase when SSID rotation started
using a name-based Personal-Hotspot pattern (SSID = "<Name>'s iPhone"),
so the hostname now consistently mirrors an iPhone identity as well.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IPHONE = ROOT / "files" / "lib" / "blue-merle" / "iphone-models.txt"


def _load(p: Path) -> list[str]:
    out = []
    with open(p) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if line:
                out.append(line)
    return out


# ---- List sanity ----

def test_iphone_list_non_empty():
    assert _load(IPHONE), "iphone-models.txt has no entries"


def test_all_entries_are_valid_hostnames():
    """RFC 952/1123: hostname is 1..63 chars of [A-Za-z0-9-]."""
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
    for name in _load(IPHONE):
        assert pattern.match(name), \
            f"{name!r} is not a valid hostname"
        assert not name.endswith("-"), \
            f"{name!r} ends with '-'"


def test_no_duplicates():
    names = _load(IPHONE)
    assert len(names) == len(set(names)), \
        "iphone-models.txt contains duplicates"


# ---- End-to-end via installed picker ----

FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"


def _sh(script: str) -> str:
    return subprocess.run(
        ["/bin/sh", "-c", script],
        capture_output=True, text=True, check=True,
    ).stdout


def test_shell_picker_returns_something_from_the_list():
    """Every pick must land in the model list."""
    pool = set(_load(IPHONE))
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 20); do
            _pick_random_line {IPHONE!s}
        done
    '''
    out = _sh(script).strip().splitlines()
    for got in out:
        assert got in pool, f"picker returned {got!r} not in list"


def test_hostname_picker_does_not_always_return_first_line():
    """Regression check for the 'iPhone-X on every reboot' bug: even if
    the underlying random source misbehaves, _pick_random_line must
    produce diverse output.
    """
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 25); do
            _pick_random_line {IPHONE!s}
        done
    '''
    out = _sh(script).strip().splitlines()
    unique = set(out)
    # With 25 models and 25 draws, expect at least 5 distinct.
    assert len(unique) >= 5, \
        f"hostname picker too deterministic: {out}"

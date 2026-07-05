"""Tests for the SSID list (us-first-names.txt) and its composition
into "<Name>'s iPhone" broadcast strings.

We don't run RANDOMIZE_SSID directly here — that would call `uci set`
on the dev host. Instead we exercise the pool file and mirror the
shell composition logic.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES_FILE = ROOT / "files" / "lib" / "blue-merle" / "us-first-names.txt"


def _load(p: Path) -> list[str]:
    out = []
    with open(p) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if line:
                out.append(line)
    return out


# ---- List sanity ----

def test_us_names_list_non_empty():
    assert _load(NAMES_FILE), "us-first-names.txt has no entries"


def test_us_names_size_is_reasonable():
    """The plan called for 200-300 names; sanity-check we're in that ballpark."""
    n = len(_load(NAMES_FILE))
    assert 100 <= n <= 500, f"unexpected list size: {n}"


def test_us_names_are_ascii_letters_only():
    """RANDOMIZE_SSID's shell guard rejects entries with anything other
    than ASCII letters. If we ship a name with a space, apostrophe or
    non-latin character it will be silently dropped at rotation time
    — better to catch that in a test."""
    pattern = re.compile(r"^[A-Za-z]+$")
    for name in _load(NAMES_FILE):
        assert pattern.match(name), f"invalid name in pool: {name!r}"


def test_us_names_no_duplicates():
    names = _load(NAMES_FILE)
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate names in pool: {dupes}"


def test_us_names_have_no_extreme_lengths():
    """SSID must be <= 32 bytes. '<Name>'s iPhone' adds 9 chars, so the
    longest name we can accept is 32 - 9 = 23 characters. Verify no
    entry blows past that; iOS in practice truncates but let's ship a
    clean pool."""
    max_name_len = 32 - len("'s iPhone")
    for name in _load(NAMES_FILE):
        assert len(name) <= max_name_len, \
            f"{name!r} is too long ({len(name)} > {max_name_len})"


# ---- Composed SSID properties ----

def _compose(name: str) -> str:
    return f"{name}'s iPhone"


def test_composed_ssid_matches_apple_pattern():
    """The composed string must look like a genuine Apple Personal
    Hotspot SSID: '<Name>'s iPhone', with an ASCII apostrophe."""
    pattern = re.compile(r"^[A-Za-z]+'s iPhone$")
    for name in _load(NAMES_FILE):
        ssid = _compose(name)
        assert pattern.match(ssid), f"unexpected SSID: {ssid!r}"


def test_composed_ssid_within_wifi_limits():
    """802.11 caps SSID at 32 bytes. Confirm every composed name fits."""
    for name in _load(NAMES_FILE):
        ssid = _compose(name)
        assert len(ssid.encode("utf-8")) <= 32, \
            f"{ssid!r} is {len(ssid.encode('utf-8'))} bytes"


# ---- End-to-end via installed shell picker ----

FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"


def _sh(script: str) -> str:
    return subprocess.run(
        ["/bin/sh", "-c", script],
        capture_output=True, text=True, check=True,
    ).stdout


def test_rand16_returns_16bit_decimal():
    """_rand16 must always print a decimal in 0..65535, one per line,
    even when od/hexdump are absent from PATH (which is the actual
    busybox-on-Mudi situation).
    """
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 20); do _rand16; done
    '''
    out = _sh(script).strip().splitlines()
    assert len(out) == 20
    for v in out:
        assert v.isdigit(), f"non-numeric _rand16 output: {v!r}"
        n = int(v)
        assert 0 <= n <= 65535, f"out of range: {n}"


def test_rand16_survives_without_od():
    """Regression for the 'Aaron/Aaron' bug: the previous implementation
    called `od -An -N2 -tu2 /dev/urandom | tr -d ' '`. Busybox on Mudi
    has no `od`, so $rnd was always empty and the picker returned
    index 1. Verify _rand16 still works with `od` scrubbed from PATH.
    """
    # A minimal PATH that excludes anywhere od might live.
    script = f'''
        PATH=/nonexistent
        # Keep a few essential builtins reachable — busybox typically
        # provides these as builtins even without PATH.
        . {FUNCTIONS_SH}
        for i in 1 2 3 4 5 6 7 8 9 10; do _rand16; done
    '''
    out = _sh(script).strip().splitlines()
    assert len(out) == 10
    # Not all values must differ (small chance of collision), but at
    # least a few must, otherwise the fallback is deterministic.
    assert len(set(out)) >= 3, \
        f"_rand16 is too deterministic without od: {out}"


def test_picker_does_not_always_return_first_line():
    """The core regression check. Even if _rand16 breaks and produces
    empty output, _pick_random_line must not deterministically return
    the first line of the file. The guard `case rnd in '') ...` handles
    that.
    """
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 30); do
            _pick_random_line {NAMES_FILE!s}
        done
    '''
    out = _sh(script).strip().splitlines()
    unique = set(out)
    # With 244 names and 30 draws, expect way more than one distinct.
    assert len(unique) >= 10, \
        f"picker produced only {len(unique)} unique names in 30 draws: {out}"


def test_shell_picker_returns_something_from_the_pool():
    """Sanity: every pick lands in the pool."""
    pool = set(_load(NAMES_FILE))
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 30); do
            _pick_random_line {NAMES_FILE!s}
        done
    '''
    out = _sh(script).strip().splitlines()
    for got in out:
        assert got in pool, f"picker returned {got!r} not in pool"

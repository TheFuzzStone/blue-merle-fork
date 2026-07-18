"""Tests for the paired SSID/hostname identity (RANDOMIZE_IDENTITY).

The hostname is composed from the same us-first-names pool as the SSID
("<Name>s-iPhone", mirroring how iOS sanitises "Emma's iPhone"), so the
two identifiers always corroborate. The old iphone-models.txt pool was
removed: real iPhones send the *device name* as their DHCP hostname,
never a model string like "iPhone-15-Pro".

We don't invoke RANDOMIZE_* here — they do `uci set/commit` which would
mutate the dev host's UCI. Instead we exercise the composition helpers
and the name picker through /bin/sh.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "files" / "lib" / "blue-merle" / "us-first-names.txt"
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"


def _load(p: Path) -> list[str]:
    out = []
    with open(p) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if line:
                out.append(line)
    return out


def _sh(script: str) -> str:
    return subprocess.run(
        ["/bin/sh", "-c", script],
        capture_output=True, text=True, check=True,
    ).stdout


# ---- Composition ----

def test_hostname_composition_mirrors_ios():
    """iOS turns the device name "Emma's iPhone" into "Emmas-iPhone"
    (apostrophe dropped, spaces become dashes)."""
    script = f'''
        . {FUNCTIONS_SH}
        _iphone_hostname_from_name Emma
        _iphone_hostname_from_name Anna
        _iphone_hostname_from_name James
    '''
    out = _sh(script).strip().splitlines()
    assert out == ["Emmas-iPhone", "Annas-iPhone", "Jamess-iPhone"], out


def test_composed_hostname_is_rfc_valid_for_whole_pool():
    """RFC 952/1123: letters/digits/hyphen, 1..63 chars — for every
    name in the pool once composed into "<Name>s-iPhone"."""
    pattern = re.compile(r"^[A-Za-z]+s-iPhone$")
    for name in _load(NAMES):
        hostname = f"{name}s-iPhone"
        assert pattern.match(hostname), f"bad composed hostname: {hostname!r}"
        assert len(hostname) <= 63, f"hostname too long: {hostname!r}"


# ---- Picker ----

def test_pick_iphone_name_returns_pool_entries():
    pool = set(_load(NAMES))
    script = f'''
        . {FUNCTIONS_SH}
        for i in $(seq 20); do
            BLUE_MERLE_US_NAMES={NAMES!s} _pick_iphone_name
        done
    '''
    out = _sh(script).strip().splitlines()
    assert len(out) == 20, out
    for got in out:
        assert got in pool, f"_pick_iphone_name returned {got!r} not in pool"


def test_pick_iphone_name_rejects_poisoned_pool():
    """Entries with spaces, apostrophes or digits must be rejected
    outright — they must never reach a hostname or SSID."""
    script = f'''
        . {FUNCTIONS_SH}
        bad=$(mktemp)
        printf '%s\\n' 'Two Words' "O'Brien" 'Anna1' > "$bad"
        BLUE_MERLE_US_NAMES="$bad" _pick_iphone_name || echo REJECTED
        rm -f "$bad"
    '''
    out = _sh(script).strip().splitlines()
    assert out == ["REJECTED"], out


def test_pick_iphone_name_fails_on_missing_pool():
    script = f'''
        . {FUNCTIONS_SH}
        BLUE_MERLE_US_NAMES=/nonexistent _pick_iphone_name || echo REJECTED
    '''
    out = _sh(script).strip().splitlines()
    assert out == ["REJECTED"], out


# ---- The old model pool is gone ----

def test_model_pool_removed_and_unreferenced():
    assert not (ROOT / "files" / "lib" / "blue-merle" / "iphone-models.txt").exists()
    src = FUNCTIONS_SH.read_text(encoding="utf-8")
    assert "iphone-models" not in src
    assert "BLUE_MERLE_IPHONE_MODELS" not in src
    # The Makefile must purge stale copies from the staged install dir
    # (an untracked leftover must never slip into the ipk).
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "rm -f $(1)/lib/blue-merle/iphone-models.txt" in makefile

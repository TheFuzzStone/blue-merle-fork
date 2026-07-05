"""Test the shell-embedded MAC generators by invoking them in a subshell.

Two generators are exercised:

* UNICAST_MAC_GEN — RFC 7844 style: unicast + locally-administered.
* APPLE_MAC_GEN   — prefix from /lib/blue-merle/apple-oui.txt + 3 random
                    octets, so the MAC looks like a genuine Apple device
                    (matches the iPhone/iPad hostname we advertise).

Requires /bin/sh and python3 on PATH — same runtime the Mudi has.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"
APPLE_OUI_TXT = ROOT / "files" / "lib" / "blue-merle" / "apple-oui.txt"


def _run(fn: str) -> str:
    """Source functions.sh and invoke `fn`, returning trimmed stdout."""
    env = os.environ.copy()
    # Point the helpers at the in-repo data files so we don't need to
    # touch /lib/blue-merle on the dev host.
    env["BLUE_MERLE_APPLE_OUI"] = str(APPLE_OUI_TXT)
    out = subprocess.run(
        ["/bin/sh", "-c", f". {FUNCTIONS_SH} && {fn}"],
        capture_output=True, text=True, check=True, env=env,
    )
    return out.stdout.strip()


def _gen_unicast() -> str:
    return _run("UNICAST_MAC_GEN")


def _gen_apple() -> str:
    return _run("APPLE_MAC_GEN")


def _first_octet(mac: str) -> int:
    return int(mac.split(":")[0], 16)


def _oui_of(mac: str) -> str:
    return ":".join(mac.split(":")[:3]).lower()


def _apple_ouis() -> set[str]:
    ouis = set()
    with open(APPLE_OUI_TXT) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if line:
                ouis.add(line.lower())
    return ouis


# ---- UNICAST_MAC_GEN (RFC 7844 locally-administered) ----

def test_unicast_format_is_colon_separated_hex():
    mac = _gen_unicast()
    parts = mac.split(":")
    assert len(parts) == 6, f"expected 6 octets, got {mac!r}"
    for p in parts:
        assert len(p) == 2 and all(c in "0123456789abcdef" for c in p), \
            f"bad octet {p!r} in {mac!r}"


def test_unicast_bit_always_zero():
    for _ in range(30):
        o = _first_octet(_gen_unicast())
        assert (o & 0x01) == 0, f"multicast bit set in first octet {o:#04x}"


def test_locally_administered_bit_always_one():
    """Regression test for A4: the historical mask only cleared the I/G
    bit but left U/L random, producing vendor-looking MACs ~50% of the
    time. RFC 7844 / IEEE 802.11 require U/L=1 for randomized MACs.
    """
    for _ in range(30):
        o = _first_octet(_gen_unicast())
        assert (o & 0x02) == 0x02, f"LAM bit not set in first octet {o:#04x}"


def test_unicast_macs_are_random():
    a, b = _gen_unicast(), _gen_unicast()
    assert a != b


# ---- APPLE_MAC_GEN (Apple OUI + 3 random octets) ----

def test_apple_format_is_valid_mac():
    mac = _gen_apple()
    parts = mac.split(":")
    assert len(parts) == 6, f"expected 6 octets, got {mac!r}"
    for p in parts:
        assert len(p) == 2 and all(c in "0123456789abcdef" for c in p), \
            f"bad octet {p!r} in {mac!r}"


def test_apple_mac_uses_only_known_ouis():
    known = _apple_ouis()
    assert known, "apple-oui.txt appears empty; test cannot proceed"
    for _ in range(50):
        mac = _gen_apple()
        assert _oui_of(mac) in known, \
            f"OUI of {mac} is not in apple-oui.txt (known: {sorted(known)[:3]}...)"


def test_apple_macs_are_random_in_tail():
    """Even if we happen to hit the same OUI twice in a row, the tail
    (last three octets) should differ."""
    a, b = _gen_apple(), _gen_apple()
    assert a != b, f"got the same MAC twice: {a}"


def test_apple_mac_unicast_bit_is_zero():
    """Real Apple OUIs are unicast, so bit 0 of the first octet must be 0.
    Regression guard against someone adding a multicast prefix by mistake.
    """
    for _ in range(30):
        o = _first_octet(_gen_apple())
        assert (o & 0x01) == 0, f"multicast bit set in first octet {o:#04x}"


def test_apple_mac_is_not_locally_administered():
    """A real vendor OUI has the U/L bit cleared. If a test-added OUI
    accidentally set it, the whole Apple-masquerade would be defeated.
    """
    for _ in range(30):
        o = _first_octet(_gen_apple())
        assert (o & 0x02) == 0, \
            f"LAM bit set on a supposed vendor OUI {o:#04x}"

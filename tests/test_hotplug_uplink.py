"""Uplink-MAC hotplug hook: queue position and the correct config key.

Two hardware findings from FW 4.3.26 (2026-07-25), both verified on a
live GL-E750:

1. Wrong key. The hook rotated only `glconfig.general.macclone_addr`,
   but the repeater's runtime MAC comes from `wireless.sta.macaddr`
   (netifd applies it at every ifup — verified). The GL `repeater`
   binary re-reads macclone_addr only when it re-creates the sta
   config (boot restore / network change), so per-ifdown rotations
   accumulated in a value nothing consumed until the next boot.
   Empirical: two rotations of macclone_addr, runtime MAC unchanged;
   setting wireless.sta.macaddr + ifdown/ifup moved the runtime MAC.

2. Queue race. netifd does NOT wait for /etc/hotplug.d/iface/ scripts;
   the alphabetical queue is shared with GL's 15/16-mwan3 + 20-firewall
   + 21-vpnpolicy, which take tens of seconds on the Mudi. Our hook's
   log line landed 28 s after the ifdown — long after the follow-up
   ifup had consumed the stale value. The hooks must sort before
   15-mwan3 (00-netstate and 01-mtk-acceleration are fast).
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"
HOOK_DIR = ROOT / "files" / "etc" / "hotplug.d" / "iface"
UPLINK_HOOK = HOOK_DIR / "03-blue-merle-uplink-mac"

FAKE_UCI = """#!/bin/sh
# Minimal uci stand-in: records `set` assignments to $UCI_SET_LOG.
if [ "$1" = "-q" ]; then shift; fi
case "$1" in
  get)
    case "$2" in
      blue-merle.main.stable_identity) echo "${FAKE_STABLE_IDENTITY:-0}" ;;
      wireless.sta.macaddr)
        if [ -n "${FAKE_STA_MACADDR:-}" ]; then
          echo "$FAKE_STA_MACADDR"
        else
          exit 1
        fi ;;
      *) exit 1 ;;
    esac ;;
  set)
    printf '%s\\n' "$2" >> "$UCI_SET_LOG" ;;
  commit)
    : ;;
esac
exit 0
"""


def _run_hook(sta_macaddr: str | None) -> str:
    """Run the uplink hook with stubbed uci/logger; return the recorded
    `uci set` assignments (one per line)."""
    # The hook sources /lib/blue-merle/functions.sh by absolute path;
    # point it at the repo copy instead (the logic under test is the
    # hook's own, not the path).
    hook_src = UPLINK_HOOK.read_text(encoding="utf-8").replace(
        "/lib/blue-merle/functions.sh", str(FUNCTIONS_SH)
    )
    with tempfile.TemporaryDirectory() as d:
        bindir = Path(d) / "bin"
        bindir.mkdir()
        uci = bindir / "uci"
        uci.write_text(FAKE_UCI, encoding="utf-8")
        logger = bindir / "logger"
        logger.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        for f in (uci, logger):
            f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        set_log = Path(d) / "uci-sets"
        env = dict(os.environ)
        env.update(
            {
                "PATH": f"{bindir}{os.pathsep}{env['PATH']}",
                "ACTION": "ifdown",
                "INTERFACE": "wwan",
                "DEVICE": "wlan-sta0",
                "UCI_SET_LOG": str(set_log),
                "BLUE_MERLE_APPLE_OUI": str(
                    ROOT / "files" / "lib" / "blue-merle" / "apple-oui.txt"
                ),
            }
        )
        if sta_macaddr is not None:
            env["FAKE_STA_MACADDR"] = sta_macaddr
        out = subprocess.run(
            ["/bin/sh", "-c", hook_src], env=env, capture_output=True, text=True,
        )
        assert out.returncode == 0, f"hook rc={out.returncode} stderr={out.stderr}"
        return set_log.read_text(encoding="utf-8") if set_log.exists() else ""


# ---- functional ----

def test_hook_rotates_both_stores_with_the_same_mac():
    sets = _run_hook(sta_macaddr="aa:bb:cc:dd:ee:ff")
    macclone = [
        line for line in sets.splitlines()
        if line.startswith("glconfig.general.macclone_addr=")
    ]
    sta = [
        line for line in sets.splitlines()
        if line.startswith("wireless.sta.macaddr=")
    ]
    assert macclone, f"no macclone_addr rotation in:\n{sets}"
    assert sta, f"no wireless.sta.macaddr rotation in:\n{sets}"
    assert macclone[0].split("=", 1)[1] == sta[0].split("=", 1)[1], (
        f"macclone and sta got different MACs:\n{sets}"
    )


def test_hook_skips_sta_rotation_when_no_repeater_configured():
    sets = _run_hook(sta_macaddr=None)
    assert "glconfig.general.macclone_addr=" in sets
    assert "wireless.sta.macaddr" not in sets


# ---- static ----

def test_hotplug_hooks_sort_before_mwan3_in_the_queue():
    names = sorted(p.name for p in HOOK_DIR.iterdir())
    assert names == [
        "02-blue-merle-bssid-on-ifdown",
        "03-blue-merle-uplink-mac",
    ], names
    for name in names:
        # Alphabetical order == execution order; 15-mwan3 is the first
        # slow GL script (tens of seconds on the Mudi).
        assert name < "15", name


def test_uplink_hook_documents_sta_macaddr_consumption():
    src = UPLINK_HOOK.read_text(encoding="utf-8")
    assert "wireless.sta.macaddr" in src
    assert 'wireless.sta.macaddr="$NEW_MAC"' in src

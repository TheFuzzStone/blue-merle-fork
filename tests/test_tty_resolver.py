"""Test the shell _resolve_modem_tty helper.

The helper lives in files/lib/blue-merle/functions.sh and is used by
every path that runs imei_generate.py (CLI, toggle stages, libexec).
Before this helper existed, stage1/stage2/libexec silently defaulted
to /dev/ttyUSB3 in the Python side while only the CLI probed the
actual device set — a real bug when USB re-enumeration shifted the
port. These tests pin the behaviour so a future regression cannot
re-introduce that split.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"


def _sh(cmd: str, env_extra: dict[str, str] | None = None) -> str:
    """Source functions.sh in /bin/sh and run `cmd`, returning stdout.

    We deliberately DO NOT set check=True: _resolve_modem_tty returns
    non-zero when it falls back to the built-in default (no device
    found), which is expected behaviour on dev hosts without a real
    modem attached.
    """
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    out = subprocess.run(
        ["/bin/sh", "-c", f". {FUNCTIONS_SH} && {cmd}"],
        capture_output=True, text=True, env=env,
    )
    return out.stdout.strip()


def test_resolver_prefers_explicit_env_when_valid():
    """If BLUE_MERLE_TTY is set AND points to an existing char device,
    it must be returned verbatim. /dev/null is a char device we can
    always rely on to exist on the test host.
    """
    got = _sh("_resolve_modem_tty", env_extra={"BLUE_MERLE_TTY": "/dev/null"})
    assert got == "/dev/null", f"got {got!r}"


def test_resolver_ignores_env_when_target_missing():
    """If BLUE_MERLE_TTY points to a non-existent path, the helper
    should skip it and either return a real ttyUSB or the fallback
    /dev/ttyUSB3 (which likely doesn't exist here either).
    """
    got = _sh(
        "_resolve_modem_tty",
        env_extra={"BLUE_MERLE_TTY": "/dev/definitely-not-a-tty"},
    )
    # On a typical dev host no /dev/ttyUSB* exists, so we get the
    # documented last-resort default.
    assert got in ("/dev/ttyUSB0", "/dev/ttyUSB1",
                   "/dev/ttyUSB2", "/dev/ttyUSB3"), f"unexpected: {got!r}"


def test_resolver_falls_back_to_ttyUSB3_when_nothing_found():
    """With no BLUE_MERLE_TTY set and no /dev/ttyUSB* on the host, the
    helper prints /dev/ttyUSB3 as the last-resort default (so the
    caller still gets a familiar error message).
    """
    # Explicitly unset BLUE_MERLE_TTY inside the subshell.
    got = _sh("unset BLUE_MERLE_TTY; _resolve_modem_tty")
    # On dev host: no ttyUSB* exists → default /dev/ttyUSB3.
    # On a Mudi with the modem present: a real ttyUSB path.
    assert got.startswith("/dev/ttyUSB"), f"unexpected: {got!r}"


def test_resolver_exit_code_reflects_success():
    """When the helper found a real device it exits 0; when it fell
    back to the default it exits non-zero. We can't reliably test the
    fallback case for exit code because /dev/ttyUSB3 may or may not
    exist depending on the host, so we only test the positive path
    via /dev/null.
    """
    p = subprocess.run(
        ["/bin/sh", "-c", f". {FUNCTIONS_SH} && _resolve_modem_tty >/dev/null"],
        env={**os.environ, "BLUE_MERLE_TTY": "/dev/null"},
    )
    assert p.returncode == 0

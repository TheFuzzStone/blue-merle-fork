"""READ_IMEI/READ_IMSI must return clean digits on real gl_modem output.

Hardware finding (2026-07-25, GL-E750 FW 4.3.26): gl_modem passes the
modem's CRLF line endings through, so `gl_modem AT AT+GSN` emits the
IMEI as "<15 digits>\\r". The old `grep -w` pipeline printed the whole
matching line, so READ_IMEI captured a trailing \\r (length 16, not 15).
Every downstream fail-closed gate then misfired on hardware:

- `_is_valid_imei_shape "$new_imei"` rejected every readback, so
  blue-merle-switch-stage2 and libexec prepare-sim-swap powered the
  device off after *successful* IMEI writes;
- read-identifiers emitted the fail-closed mask instead of the
  canonical one.

The fix is `grep -ow`: print only the matched digits, never the line.
Captured bytes are compared as bytes — text mode would translate the
\\r away and hide the regression.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"

# Faithful copy of gl_modem's observed output structure (CRLF endings):
#   "\r" / "<value>\r" / "\r" / "OK\r"
STUB = """#!/bin/sh
case "$*" in
  *GSN*)  printf '\\r\\n490154203237518\\r\\n\\r\\nOK\\r\\n' ;;
  *CIMI*) printf '\\r\\n310150123456789\\r\\n\\r\\nOK\\r\\n' ;;
  *)      printf '\\r\\n+CME ERROR: 10\\r\\n' ;;
esac
"""


def _run(cmd: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        stub = Path(d) / "gl_modem"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{d}{os.pathsep}{env['PATH']}"
        env["BM_READ_TRIES"] = "1"  # keep the failure-path test fast
        return subprocess.run(
            ["/bin/sh", "-c", f". {FUNCTIONS_SH} && {cmd}"],
            capture_output=True, env=env,  # bytes on purpose — see module docstring
        )


def test_read_imei_returns_exactly_15_digits_no_cr():
    out = _run("READ_IMEI")
    assert out.returncode == 0, f"rc={out.returncode} stderr={out.stderr!r}"
    assert out.stdout == b"490154203237518", f"stdout={out.stdout!r}"


def test_read_imei_output_passes_the_shape_gate():
    """The exact composition that failed closed on hardware."""
    out = _run('imei=$(READ_IMEI) && _is_valid_imei_shape "$imei"')
    assert out.returncode == 0, f"rc={out.returncode} stderr={out.stderr!r}"


def test_read_imsi_returns_clean_digits_and_masks_canonical():
    out = _run('imsi=$(READ_IMSI) && _mask_imsi "$imsi"')
    assert out.returncode == 0, f"rc={out.returncode} stderr={out.stderr!r}"
    assert out.stdout == b"31015******6789\n", f"stdout={out.stdout!r}"


def test_read_helpers_still_fail_closed_on_modem_error():
    """grep -o must not turn an error response into a value."""
    # A shell function shadows the PATH stub and answers +CME ERROR to
    # every query — an errored modem must yield empty output + non-zero.
    out = _run("gl_modem() { printf '\\r\\n+CME ERROR: 10\\r\\n'; }; READ_IMEI")
    assert out.returncode != 0, f"rc={out.returncode} stdout={out.stdout!r}"
    assert out.stdout == b"", f"stdout={out.stdout!r}"

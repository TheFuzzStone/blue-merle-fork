"""Canonical identifier mask forms.

One form per identifier class, defined once in functions.sh
(_mask_imei/_mask_imsi) and used by every shipped surface; the
self-contained diag tool carries its own copies. Historical drift
(first6+last3 in libexec, first6+last4 in the AGENTS.md example,
first4+last4 in diag) made the mask shape an accident rather than a
decision.

Canonical forms:
  IMEI (15 digits)      -> first6 + ****** + last3   (490154******518)
  IMSI (14/15 digits)   -> first5 + ****** + last4   (31015******6789)

The IMSI form deliberately reveals MCC+MNC — the carrier. That is a
conscious decision: the router's own admin UI shows the carrier anyway,
and the subscriber-identifying tail stays masked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_SH = ROOT / "files" / "lib" / "blue-merle" / "functions.sh"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _sh(cmd: str) -> str:
    out = subprocess.run(
        ["/bin/sh", "-c", f". {FUNCTIONS_SH} && {cmd}"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"{cmd}: rc={out.returncode} {out.stderr}"
    return out.stdout.strip()


# ---- functional: helpers emit exactly the canonical forms ----

def test_mask_imei_canonical():
    assert _sh("_mask_imei 490154203237518") == "490154******518"


def test_mask_imsi_canonical_15_and_14_digits():
    assert _sh("_mask_imsi 310150123456789") == "31015******6789"
    assert _sh("_mask_imsi 31015012345678") == "31015******5678"


def test_mask_helpers_fail_closed_on_bad_shapes():
    """Anything that is not a well-shaped identifier gets fully masked:
    a partial mask of a misread/garbage value could reveal more than
    the canonical form allows."""
    for cmd in (
        "_mask_imei 49015420323751",      # 14 digits
        "_mask_imei 4901542032375188",    # 16 digits
        "_mask_imei 49015420323751x",     # non-digit
        "_mask_imei ''",                  # empty
        "_mask_imsi 3101501234567",       # 13 digits
        "_mask_imsi 3101501234567890",    # 16 digits
        "_mask_imsi 31015012345678x",     # non-digit
    ):
        assert _sh(f"{cmd} || true") == "***************", cmd


# ---- static: one canonical expression, used everywhere ----

def test_mask_helpers_defined_once_in_functions_sh():
    src = _read("files/lib/blue-merle/functions.sh")
    assert src.count("_mask_imei ()") == 1
    assert src.count("_mask_imsi ()") == 1


def test_libexec_uses_shared_mask_helpers():
    src = _read("files/usr/libexec/blue-merle")
    assert '_mask_imei "$imei"' in src
    assert '_mask_imsi "$imsi"' in src
    assert '_mask_imei "$new_imei"' in src
    # No hand-rolled mask expressions outside the helper definitions.
    assert "cut -c1-6" not in src
    assert "cut -c1-5" not in src


def test_no_stray_literal_mask_expressions_in_shipped_files():
    """The literal `******` mask expression may appear only inside the
    _mask_imei/_mask_imsi definitions and the self-contained diag
    tool's own copies — nowhere else under files/."""
    allowed = {
        "files/lib/blue-merle/functions.sh",
    }
    for path in (ROOT / "files").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "******" not in text:
            continue
        rel = str(path.relative_to(ROOT))
        assert rel in allowed, f"stray mask expression in {rel}"


def test_agents_md_examples_use_canonical_forms():
    src = _read("AGENTS.md")
    # The old rule example showed first6+last4 — a third, wrong shape.
    assert "******1234" not in src
    assert "354567******345" in src  # IMEI first6+last3
    assert "31015******6789" in src  # IMSI first5+last4


def test_diag_mask_helpers_are_canonical():
    """diag is self-contained (not shipped in the ipk) and keeps its own
    helpers, but they must produce the same canonical forms."""
    src = _read("tools/blue-merle-diag.sh")
    imei_block = src.split("mask_imei() {", 1)[1].split("\n}", 1)[0]
    assert "cut -c1-6" in imei_block and "cut -c13-" in imei_block
    assert "cut -c1-4" not in imei_block
    imsi_block = src.split("mask_imsi() {", 1)[1].split("\n}", 1)[0]
    assert "cut -c1-5" in imsi_block
    assert "cut -c1-4" not in imsi_block
    # The old generic first4+last4 identifier masker is gone (mask_name's
    # own cut -c1-4 for hostnames/SSIDs is a different, documented design).
    assert "mask_id()" not in src

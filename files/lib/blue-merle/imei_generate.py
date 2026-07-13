#!/usr/bin/env python3
"""IMEI generation and provisioning for the Quectel EP06 modem in the
GL-E750 Mudi router.

The script exposes three modes:

* --random         Generate a fresh random IMEI.
* --deterministic  Derive an IMEI reproducibly from the current SIM's IMSI.
* --static IMEI    Set a user-provided IMEI (15 digits, Luhn-valid).

Design notes / non-obvious fixes vs. the historical version:

* Random-digit fill previously used ``random.sample`` (sampling *without*
  replacement) which both loses entropy and makes generated IMEIs
  statistically distinguishable from real ones (their random tail never
  contains repeated digits). We now use ``random.choices``.
* Serial reads now loop until the modem returns ``OK``/``ERROR`` or the
  timeout expires, rather than reading a single 64-byte chunk.
* IMSI regex accepts 14-15 digit values (ITU-T E.212 allows both).
* ``get_imei`` / ``get_imsi`` retry a few times before giving up.
* ``exit(1)`` on failure instead of ``exit(-1)`` (which POSIX turns into
  255 and confuses shell wrappers).
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import logging
import os
import random
import re
import string
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import serial


class Modes(Enum):
    DETERMINISTIC = 1
    RANDOM = 2
    STATIC = 3


# Example IMEI: 490154203237518
IMEI_BODY_LENGTH = 14  # digits before the Luhn check digit

def _load_tac_list(tty: Optional[str] = None) -> list[str]:
    """Return a strictly validated TAC selection.

    ``BLUE_MERLE_TAC`` selects one exact, previously captured TAC.
    ``BLUE_MERLE_TAC_LIST`` selects an explicit user-provided list.
    If neither is set, preserve the TAC currently reported by the modem.

    There is deliberately no manufacturer/model fallback database here:
    GSMA TAC attribution is licensed data and unverified TAC claims can
    make the device more distinctive or prevent registration.
    """
    tty = tty or DEFAULT_TTY
    exact_tac = os.environ.get("BLUE_MERLE_TAC", "")
    if re.fullmatch(r"[0-9]{8}", exact_tac):
        return [exact_tac]

    explicit_path = os.environ.get("BLUE_MERLE_TAC_LIST")
    if not explicit_path:
        current_imei = get_imei(tty)
        if re.fullmatch(rb"[0-9]{15}", current_imei):
            return [current_imei[:8].decode("ascii")]
        raise RuntimeError("Cannot read current modem TAC")

    path = Path(explicit_path)
    tacs: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if re.fullmatch(r"[0-9]{8}", line):
                tacs.append(line)
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"TAC list {path} is not readable: {exc}") from exc
    if tacs:
        log.debug("Loaded %d TACs from %s", len(tacs), path)
        return tacs
    raise RuntimeError(f"TAC list {path} contains no valid 8-digit TACs")

# Serial defaults. The TTY can be overridden by the BLUE_MERLE_TTY env
# variable so shell wrappers can point us at a different port when the
# modem enumerates elsewhere.
DEFAULT_TTY = os.environ.get("BLUE_MERLE_TTY", "/dev/ttyUSB3")
BAUDRATE = 9600
READ_TIMEOUT = 3.0        # seconds per serial.read() poll
COMMAND_TIMEOUT = 5.0     # total wall-clock budget per AT command
POST_EGMR_SETTLE = 1.0    # let the modem digest EGMR before we read GSN

log = logging.getLogger("blue-merle.imei")


def _read_at_response(ser: "serial.Serial", budget: float = COMMAND_TIMEOUT) -> bytes:
    """Read from the serial port until OK/ERROR is seen or `budget` expires."""
    buf = bytearray()
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        chunk = ser.read(64)
        if chunk:
            buf.extend(chunk)
            if b"OK" in buf or b"ERROR" in buf:
                break
        else:
            # Nothing new; short sleep to avoid busy-looping.
            time.sleep(0.05)
    return bytes(buf)


# Cross-process advisory lock on the modem TTY.
#
# serial.Serial(..., exclusive=True) issues ioctl(TIOCEXCL), a
# kernel-level advisory flag that only blocks *new* open() calls on
# the same tty. It does NOT block operations from a process that
# already had the fd open. fcntl.flock on the same fd adds a second
# layer: if another process is currently holding LOCK_EX, we get
# EWOULDBLOCK immediately instead of interleaving AT-command bytes.
#
# The kernel releases flock automatically when the fd is closed
# (including on process death), so zombie holders cannot leave an
# orphan lock — a real advantage over an on-disk lockfile.
_FLOCK_ATTEMPTS = 3
_FLOCK_INTERVAL = 1.0


def _open_serial(tty: str) -> "serial.Serial":
    """Open the modem TTY with both TIOCEXCL and a non-blocking flock.

    Raises serial.SerialException if the port cannot be opened after
    the configured number of retries — the caller's existing retry
    logic will treat that as a transient failure.
    """
    for attempt in range(1, _FLOCK_ATTEMPTS + 1):
        ser = serial.Serial(tty, BAUDRATE, timeout=READ_TIMEOUT, exclusive=True)
        try:
            fcntl.flock(ser.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return ser
        except (BlockingIOError, OSError) as exc:
            # Close the fd so TIOCEXCL is released too; retry.
            ser.close()
            eno = getattr(exc, "errno", None)
            if eno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                # Not a lock contention error — re-raise as SerialException
                # so callers' retry logic still triggers.
                raise serial.SerialException(
                    f"flock({tty}) failed: {exc}"
                ) from exc
            if attempt >= _FLOCK_ATTEMPTS:
                raise serial.SerialException(
                    f"{tty} is held by another process (tried "
                    f"{_FLOCK_ATTEMPTS} times)"
                ) from exc
            log.debug(
                "flock(%s) contended on attempt %d/%d; retrying in %.1fs",
                tty, attempt, _FLOCK_ATTEMPTS, _FLOCK_INTERVAL,
            )
            time.sleep(_FLOCK_INTERVAL)
    # Unreachable in practice; kept for type-checker peace of mind.
    raise serial.SerialException(f"could not open {tty}")


def get_imsi(tty: str = DEFAULT_TTY, retries: int = 3) -> bytes:
    """Return the current SIM's IMSI, or b'' if unavailable."""
    for attempt in range(1, retries + 1):
        log.debug("get_imsi attempt %d/%d on %s", attempt, retries, tty)
        try:
            with _open_serial(tty) as ser:
                ser.write(b"AT+CIMI\r")
                output = _read_at_response(ser)
        except serial.SerialException as exc:
            log.warning("Serial error while reading IMSI: %s", exc)
            time.sleep(1)
            continue
        log.debug("AT+CIMI raw output: %r", output)
        # IMSI is 14-15 digits per ITU-T E.212. Take the first match.
        candidates = re.findall(rb"[0-9]{14,15}", output)
        if candidates:
            return candidates[0]
        time.sleep(0.5)
    return b""


def get_imei(tty: str = DEFAULT_TTY, retries: int = 3) -> bytes:
    for attempt in range(1, retries + 1):
        log.debug("get_imei attempt %d/%d on %s", attempt, retries, tty)
        try:
            with _open_serial(tty) as ser:
                ser.write(b"AT+GSN\r")
                output = _read_at_response(ser)
        except serial.SerialException as exc:
            log.warning("Serial error while reading IMEI: %s", exc)
            time.sleep(1)
            continue
        log.debug("AT+GSN raw output: %r", output)
        candidates = re.findall(rb"[0-9]{15}", output)
        if candidates:
            return candidates[0]
        time.sleep(0.5)
    return b""


def set_imei(imei: str, tty: str = DEFAULT_TTY) -> bool:
    """Write `imei` (15-digit string) to the modem via AT+EGMR.

    Returns True iff the modem now reports the same IMEI back.
    """
    cmd = b'AT+EGMR=1,7,"' + imei.encode() + b'"\r'
    try:
        with _open_serial(tty) as ser:
            ser.write(cmd)
            output = _read_at_response(ser)
    except serial.SerialException as exc:
        log.error("Serial error while writing IMEI: %s", exc)
        return False

    log.debug("AT+EGMR raw output: %r", output)

    # Some Quectel firmwares need a beat to commit EGMR before AT+GSN reflects
    # the new value; without this we get spurious "IMEI not changed" reports.
    time.sleep(POST_EGMR_SETTLE)

    new_imei = get_imei(tty)
    if new_imei == imei.encode():
        log.info("IMEI has been successfully changed.")
        return True
    log.error(
        "IMEI change verification failed. Modem reports %r, wanted %r.",
        new_imei, imei,
    )
    return False


def _luhn_check_digit(body: str) -> int:
    """Standard Luhn check digit for a numeric body string."""
    total = 0
    # Standard Luhn: starting from the rightmost body digit, double every
    # second one. For an even-length body this is equivalent to doubling
    # the odd-indexed (left, 0-based) digits, but we implement it in the
    # canonical right-to-left form so it works for any length.
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def generate_imei(tac_list: Iterable[str], imsi_seed: Optional[bytes]) -> str:
    """Generate an IMEI in either RANDOM or DETERMINISTIC mode.

    Reads the module-global `mode` (set by main() before entry). The
    `global` keyword is intentionally NOT used here — Python only
    needs `global` to *assign*, not to read, and this function only
    reads. Keeping it out avoids the false impression that
    generate_imei mutates the mode.

    ``tac_list`` is an iterable of 8-digit TAC strings (Type Allocation
    Codes). One is chosen at random; the remaining 6 body digits are
    filled uniformly; a Luhn check digit is appended.
    """
    rng = random.Random()

    if mode == Modes.DETERMINISTIC:
        if not imsi_seed:
            raise RuntimeError(
                "Deterministic mode requires an IMSI, but none could be read."
            )
        # Hash the IMSI first so the seed space is uniformly distributed
        # regardless of IMSI structure (MCC/MNC clusters).
        digest = hashlib.sha256(imsi_seed).digest()
        rng.seed(int.from_bytes(digest, "big"))

    tac = rng.choice(list(tac_list))
    log.debug("TAC (first 8 digits): %s", tac)

    tail_length = IMEI_BODY_LENGTH - len(tac)
    # random.choices samples *with* replacement so each digit is uniform
    # and independent. The previous random.sample lost ~2.7 bits of entropy
    # per IMEI and, worse, produced tails that never contained repeated
    # digits — a statistical fingerprint of the tool itself.
    tail = "".join(rng.choices(string.digits, k=tail_length))
    body = tac + tail
    log.debug("IMEI without check digit: %s", body)

    imei = body + str(_luhn_check_digit(body))
    log.debug("Resulting IMEI: %s", imei)
    return imei


def validate_imei(imei: str) -> bool:
    """Return True iff `imei` is 15 characters and Luhn-valid.

    Historically this accepted 14-char input (missing check digit) which
    made the "static" path inconsistent with the generator's 15-char output.
    We now accept the standards-compliant 15-char form only.
    """
    if len(imei) != 15 or not imei.isdigit():
        log.error("NOT A VALID IMEI: %r — must be 15 digits", imei)
        return False
    body, expected = imei[:14], int(imei[14])
    got = _luhn_check_digit(body)
    if got != expected:
        log.error("NOT A VALID IMEI: %s — Luhn check %d != %d", imei, got, expected)
        return False
    log.info("%s is CORRECT", imei)
    return True


# ---- CLI entry point ----

verbose = False
mode: Optional[Modes] = None


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", help="Enables verbose output",
                    action="store_true")
    ap.add_argument("-g", "--generate-only",
                    help="Only generates an IMEI rather than setting it",
                    action="store_true")
    modes_grp = ap.add_mutually_exclusive_group(required=True)
    modes_grp.add_argument("-d", "--deterministic",
                           help="Switches IMEI generation to deterministic mode",
                           action="store_true")
    modes_grp.add_argument("-s", "--static",
                           help="Sets user-defined IMEI",
                           action="store")
    modes_grp.add_argument("-r", "--random",
                           help="Sets random IMEI",
                           action="store_true")
    return ap


def main() -> int:
    global mode, verbose

    args = _build_argparser().parse_args()
    verbose = args.verbose
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    imsi_seed: Optional[bytes] = None
    if args.deterministic:
        mode = Modes.DETERMINISTIC
        imsi_seed = get_imsi()
        if not imsi_seed:
            log.error("Cannot read IMSI — is the SIM inserted?")
            return 1
    elif args.random:
        mode = Modes.RANDOM
    elif args.static is not None:
        mode = Modes.STATIC

    if mode == Modes.STATIC:
        if not validate_imei(args.static):
            return 1
        # The static path historically called set_imei with a 14-char string;
        # we now require the full 15-char (Luhn-valid) IMEI, so no re-append.
        if not args.generate_only and not set_imei(args.static):
            return 1
        print(args.static)
        return 0

    tac_list = _load_tac_list()
    imei = generate_imei(tac_list, imsi_seed)
    log.info("Generated new IMEI: %s", imei)
    if not args.generate_only and not set_imei(imei):
        return 1
    print(imei)
    return 0


if __name__ == "__main__":
    sys.exit(main())
